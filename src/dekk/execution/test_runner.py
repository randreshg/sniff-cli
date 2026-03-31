"""Project test command resolution and execution."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dekk.detection.build import BuildSystem, BuildSystemDetector
from dekk.cli.errors import NotFoundError, RuntimeError
from dekk.environment.spec import find_envspec

PYTHON_SYSTEMS: Final = {
    BuildSystem.POETRY,
    BuildSystem.PDM,
    BuildSystem.HATCH,
    BuildSystem.FLIT,
    BuildSystem.SETUPTOOLS,
    BuildSystem.MATURIN,
    BuildSystem.UV,
}

PYTHON_MODULE_FLAG: Final = "-m"
PYTEST_MODULE: Final = "pytest"
TEST_ACTION: Final = "test"
TEST_LABEL_SUFFIX: Final = " test"
BUILD_DIR_NAME: Final = "build"
NPM_ARG_SEPARATOR: Final = "--"
TEST_SCRIPT_NOT_FOUND: Final = "No test script found in package configuration"
MAKE_TEST_TARGET_NOT_FOUND: Final = "No 'test' target found in Makefile"
DIRECT_RUN_HINT: Final = "run the desired command directly"
DOCTOR_HINT: Final = "Run 'dekk doctor' to diagnose the environment"


@dataclass(frozen=True)
class TestPlan:
    """Resolved test command for a project."""

    cmd: tuple[str, ...]
    cwd: Path
    label: str


def resolve_test_plan(root: Path | None = None, extra_args: Sequence[str] = ()) -> TestPlan:
    """Resolve the most sensible test command for the current project."""
    root = (root or Path.cwd()).resolve()

    build = BuildSystemDetector().detect_first(root)
    if build is None:
        raise NotFoundError(
            f"No supported project type detected in {root}",
            hint="Create a supported project config or run your test tool directly",
        )

    args = tuple(extra_args)

    if build.system in PYTHON_SYSTEMS:
        return TestPlan(
            cmd=(sys.executable, PYTHON_MODULE_FLAG, PYTEST_MODULE, *args),
            cwd=root,
            label=PYTEST_MODULE,
        )

    if build.system == BuildSystem.CARGO:
        return TestPlan(
            cmd=("cargo", TEST_ACTION, *args), cwd=root, label=f"cargo{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.GO:
        return TestPlan(
            cmd=("go", TEST_ACTION, "./...", *args), cwd=root, label=f"go{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.MAVEN:
        return TestPlan(
            cmd=("mvn", TEST_ACTION, *args), cwd=root, label=f"maven{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.GRADLE:
        gradlew = root / "gradlew"
        if gradlew.exists():
            return TestPlan(
                cmd=(str(gradlew), TEST_ACTION, *args),
                cwd=root,
                label=f"gradle{TEST_LABEL_SUFFIX}",
            )
        return TestPlan(
            cmd=("gradle", TEST_ACTION, *args), cwd=root, label=f"gradle{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.MIX:
        return TestPlan(cmd=("mix", TEST_ACTION, *args), cwd=root, label=f"mix{TEST_LABEL_SUFFIX}")

    if build.system == BuildSystem.STACK:
        return TestPlan(
            cmd=("stack", TEST_ACTION, *args), cwd=root, label=f"stack{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.CABAL:
        return TestPlan(
            cmd=("cabal", TEST_ACTION, *args), cwd=root, label=f"cabal{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.ZIG:
        return TestPlan(
            cmd=("zig", "build", TEST_ACTION, *args), cwd=root, label=f"zig{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.DUNE:
        return TestPlan(
            cmd=("dune", TEST_ACTION, *args), cwd=root, label=f"dune{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.BAZEL:
        return TestPlan(
            cmd=("bazel", TEST_ACTION, "//...", *args), cwd=root, label=f"bazel{TEST_LABEL_SUFFIX}"
        )

    if build.system == BuildSystem.BUCK2:
        return TestPlan(
            cmd=("buck2", TEST_ACTION, "//...", *args), cwd=root, label=f"buck2{TEST_LABEL_SUFFIX}"
        )

    if build.system in {BuildSystem.NPM, BuildSystem.PNPM, BuildSystem.YARN, BuildSystem.BUN}:
        script_names = set(build.target_names)
        if TEST_ACTION not in script_names:
            raise NotFoundError(
                TEST_SCRIPT_NOT_FOUND,
                hint=f"Add a '{TEST_ACTION}' script or {DIRECT_RUN_HINT}",
            )
        tool = build.system.value
        if build.system == BuildSystem.NPM:
            npm_args = (NPM_ARG_SEPARATOR, *args) if args else ()
            cmd = ("npm", TEST_ACTION, *npm_args)
        elif build.system == BuildSystem.PNPM:
            cmd = ("pnpm", TEST_ACTION, *args)
        elif build.system == BuildSystem.YARN:
            cmd = ("yarn", TEST_ACTION, *args)
        else:
            cmd = ("bun", TEST_ACTION, *args)
        return TestPlan(cmd=cmd, cwd=root, label=f"{tool}{TEST_LABEL_SUFFIX}")

    if build.system == BuildSystem.MAKE:
        script_names = set(build.target_names)
        if TEST_ACTION not in script_names:
            raise NotFoundError(
                MAKE_TEST_TARGET_NOT_FOUND,
                hint=f"Add a {TEST_ACTION} target or {DIRECT_RUN_HINT}",
            )
        return TestPlan(
            cmd=("make", TEST_ACTION, *args), cwd=root, label=f"make{TEST_LABEL_SUFFIX}"
        )

    if build.system in {BuildSystem.CMAKE, BuildSystem.MESON, BuildSystem.NINJA}:
        build_dir = root / BUILD_DIR_NAME
        if build.system == BuildSystem.MESON:
            return TestPlan(
                cmd=("meson", TEST_ACTION, "-C", str(build_dir), *args),
                cwd=root,
                label=f"meson{TEST_LABEL_SUFFIX}",
            )
        return TestPlan(cmd=("ctest", "--test-dir", str(build_dir), *args), cwd=root, label="ctest")

    raise NotFoundError(
        f"No test strategy implemented for {build.system.value}",
        hint="Run the project-specific test tool directly",
    )


def run_test_plan(plan: TestPlan) -> int:
    """Execute a resolved test plan and return its exit code."""
    executable = shutil.which(plan.cmd[0]) if not Path(plan.cmd[0]).exists() else plan.cmd[0]
    if not executable:
        raise NotFoundError(
            f"Test runner not found: {plan.cmd[0]}",
            hint=f"Install {plan.cmd[0]} or use the project's native test command",
        )

    env = os.environ.copy()
    spec_file = find_envspec(plan.cwd)
    if spec_file is not None:
        from dekk.environment.activation import EnvironmentActivator
        from dekk.cli.errors import DependencyError

        result = EnvironmentActivator.from_path(plan.cwd).activate()
        if result.missing_tools:
            raise DependencyError(
                "Missing required tools: " + ", ".join(result.missing_tools),
                hint=DOCTOR_HINT,
            )
        env.update(result.env_vars)

    proc = subprocess.run(plan.cmd, cwd=plan.cwd, env=env)
    if proc.returncode < 0:
        raise RuntimeError(f"Test command exited abnormally: {proc.returncode}")
    return proc.returncode
