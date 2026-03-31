"""Conda runtime environment provider."""

from __future__ import annotations

import shutil
import subprocess
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from dekk.environment.providers.base import DekkEnv, DekkEnvSetupResult
from dekk.environment.types import EnvironmentKind
from dekk.execution.os import DekkOS, get_dekk_os
from dekk.execution.toolchain import CMakeToolchain, CondaToolchain, EnvVarBuilder

CONDA_FORGE_CHANNEL: Final = "conda-forge"
CONDA_COMMANDS: Final = ("mamba", "conda")
CONDA_METADATA_DIRNAME: Final = "conda-meta"
PATH_ENV_NAME: Final = "PATH"
HOME_ENV_NAME: Final = "HOME"
CMAKE_TOOL_NAME: Final = "cmake"


class CondaEnv(DekkEnv):
    """Conda-backed runtime environment."""

    def __init__(self, *, prefix: Path, file: str | None = None, name: str | None = None) -> None:
        super().__init__(kind=EnvironmentKind.CONDA, prefix=prefix, file=file, name=name)

    def exists(self) -> bool:
        return self.prefix.is_dir() and (self.prefix / CONDA_METADATA_DIRNAME).is_dir()

    def runtime_paths(self, os_strategy: DekkOS) -> tuple[Path, ...]:
        return os_strategy.conda_runtime_paths(self.prefix)

    def configure(
        self,
        builder: EnvVarBuilder,
        *,
        project_name: str,
        tools,
    ) -> None:
        CondaToolchain(self.prefix, project_name).configure(builder)
        if any(tool_name.lower() == CMAKE_TOOL_NAME for tool_name in tools):
            CMakeToolchain(self.prefix).configure(builder)

    def setup(self, *, project_root: Path, force: bool = False) -> DekkEnvSetupResult:
        conda_cmd = _find_conda_cmd()
        if not conda_cmd:
            return DekkEnvSetupResult(errors=["conda/mamba not found on PATH"])

        existing = self.exists()
        if existing and not force:
            return DekkEnvSetupResult(prefix=self.prefix)

        errors: list[str] = []
        if self.file:
            env_file_path = project_root / self.file
            if not env_file_path.is_file():
                return DekkEnvSetupResult(
                    errors=[f"Environment file not found: {env_file_path}"]
                )
            if existing:
                cmd = [conda_cmd, "env", "update", "-p", str(self.prefix), "-f", str(env_file_path)]
            else:
                cmd = [conda_cmd, "env", "create", "-p", str(self.prefix), "-f", str(env_file_path)]
            if force:
                cmd.append("--force")
        else:
            cmd = [conda_cmd, "create", "-p", str(self.prefix), "-c", CONDA_FORGE_CHANNEL, "-y"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                errors.append(f"{self.type_name} create failed: {stderr[:500]}")
                return DekkEnvSetupResult(errors=errors)
        except subprocess.TimeoutExpired:
            return DekkEnvSetupResult(errors=[f"{self.type_name} create timed out (10 minutes)"])
        except OSError as exc:
            return DekkEnvSetupResult(errors=[f"Failed to run {conda_cmd}: {exc}"])

        return DekkEnvSetupResult(prefix=self.prefix if self.exists() else None, created=True, errors=errors)

    def install_npm_packages(self, packages: Mapping[str, str]) -> tuple[list[str], list[str]]:
        """Install npm packages globally into this runtime environment."""
        os_strategy = get_dekk_os()
        npm_bin = _find_runtime_executable(self.prefix, os_strategy.npm_command_candidates(), os_strategy)
        if npm_bin is None:
            return [], [f"npm not found in {self.type_name} runtime paths — add nodejs to environment packages"]

        runtime_paths = os_strategy.conda_runtime_paths(self.prefix)
        runtime_path = os_strategy.path_separator.join(str(path) for path in runtime_paths)
        inherited_path = os.environ.get(PATH_ENV_NAME, "")
        env = {
            PATH_ENV_NAME: (
                f"{runtime_path}{os_strategy.path_separator}{inherited_path}"
                if inherited_path
                else runtime_path
            ),
            HOME_ENV_NAME: str(Path.home()),
        }
        installed: list[str] = []
        errors: list[str] = []

        for name, version in packages.items():
            pkg_spec = f"{name}@{version}" if version and version != "latest" else name
            cmd = [str(npm_bin), "install", "-g", pkg_spec]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                    env=env,
                )
                if result.returncode != 0:
                    errors.append(f"npm install {pkg_spec} failed: {result.stderr.strip()[:300]}")
                else:
                    installed.append(name)
            except subprocess.TimeoutExpired:
                errors.append(f"npm install {pkg_spec} timed out")
            except OSError as exc:
                errors.append(f"Failed to run npm: {exc}")

        return installed, errors


def _find_conda_cmd() -> str | None:
    for cmd in CONDA_COMMANDS:
        if shutil.which(cmd):
            return cmd
    return None


def _find_runtime_executable(prefix: Path, candidates: tuple[str, ...], os_strategy: DekkOS) -> Path | None:
    for runtime_dir in os_strategy.conda_runtime_paths(prefix):
        for candidate in candidates:
            executable = runtime_dir / candidate
            if executable.is_file():
                return executable
    return None


def create_conda_env(*, prefix: Path, file: str | None = None, name: str | None = None) -> CondaEnv:
    """Construct a `CondaEnv` from resolved spec values."""
    return CondaEnv(prefix=prefix, file=file, name=name)


__all__ = ["CondaEnv", "create_conda_env"]
