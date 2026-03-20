"""Run a Python script with automatic venv bootstrap from pyproject.toml."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .dekk_os import get_dekk_os

VERSION_PREFIX_PATTERN = re.compile(r"^[\^~><!=]+")


def _find_pyproject(start: Path) -> Path | None:
    """Walk up from start looking for pyproject.toml."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def _find_dekk_toml(start: Path) -> Path | None:
    """Walk up from start looking for .dekk.toml."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        candidate = parent / ".dekk.toml"
        if candidate.is_file():
            return candidate
    return None


def _parse_poetry_deps(deps: dict[str, Any]) -> list[str]:
    """Parse [tool.poetry.dependencies] into pip install specs."""
    specs = []
    for name, constraint in deps.items():
        if name.lower() == "python":
            continue
        if isinstance(constraint, str):
            # Strip leading ^, ~, etc. to produce a >= spec
            version = VERSION_PREFIX_PATTERN.sub("", constraint)
            if version:
                specs.append(f"{name}>={version}")
            else:
                specs.append(name)
        elif isinstance(constraint, dict):
            if "git" in constraint:
                url = constraint["git"]
                branch = constraint.get("branch", constraint.get("tag", "main"))
                specs.append(f"{name} @ git+{url}@{branch}")
            elif "extras" in constraint:
                extras = ",".join(constraint["extras"])
                version = constraint.get("version", "")
                version = VERSION_PREFIX_PATTERN.sub("", version)
                base = f"{name}[{extras}]"
                if version:
                    specs.append(f"{base}>={version}")
                else:
                    specs.append(base)
            elif "version" in constraint:
                version = VERSION_PREFIX_PATTERN.sub("", constraint["version"])
                if version:
                    specs.append(f"{name}>={version}")
                else:
                    specs.append(name)
            else:
                specs.append(name)
        else:
            specs.append(name)
    return specs


def _parse_pep621_deps(deps: list[Any]) -> list[str]:
    """Parse [project.dependencies] list (PEP 621 format) into pip install specs."""
    # PEP 621 deps are already pip-compatible strings
    return [str(d) for d in deps]


def _venv_executable(venv_path: Path, name: str) -> Path:
    """Return a tool path inside a virtual environment on the current platform."""
    dekk_os = get_dekk_os()
    if name == "python":
        return dekk_os.venv_python(venv_path)
    if name == "pip":
        return dekk_os.venv_pip(venv_path)
    return dekk_os.venv_bin_dir(venv_path) / name


def _bootstrap_venv(pyproject_path: Path, venv_path: Path) -> None:
    """Create and populate a venv from pyproject.toml."""
    print("Setting up Python environment...", file=sys.stderr)

    project_dir = pyproject_path.parent

    # Try Poetry first
    poetry = _which("poetry")
    if poetry:
        env = os.environ.copy()
        env["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"
        result = subprocess.run(
            [poetry, "install", "--no-root"],
            cwd=str(project_dir),
            env=env,
        )
        if result.returncode == 0 and _venv_executable(venv_path, "python").is_file():
            print("Done.", file=sys.stderr)
            return

    # Fallback: create venv with stdlib + pip install deps
    python = sys.executable or "python3"
    subprocess.run(
        [python, "-m", "venv", str(venv_path)],
        check=True,
    )

    # Parse dependencies from pyproject.toml
    from dekk._compat import load_toml

    data = load_toml(pyproject_path)
    if data is None:
        print("Done.", file=sys.stderr)
        return

    deps: list[str] = []

    # Try [tool.poetry.dependencies]
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies")
    if poetry_deps and isinstance(poetry_deps, dict):
        deps = _parse_poetry_deps(poetry_deps)

    # Try [project.dependencies] (PEP 621)
    if not deps:
        pep621_deps = data.get("project", {}).get("dependencies")
        if pep621_deps and isinstance(pep621_deps, list):
            deps = _parse_pep621_deps(pep621_deps)

    if deps:
        pip = str(_venv_executable(venv_path, "pip"))
        subprocess.run(
            [pip, "install", *deps],
            check=False,
        )

    print("Done.", file=sys.stderr)


def _which(name: str) -> str | None:
    """Find an executable on PATH."""
    import shutil

    return shutil.which(name)


def _activate_dekk_env(dekk_toml_path: Path, script_dir: Path) -> None:
    """Load .dekk.toml env vars and paths into os.environ."""
    from dekk._compat import load_toml

    data = load_toml(dekk_toml_path)
    if data is None:
        return

    project_root = dekk_toml_path.parent

    # Expand env vars
    env_section = data.get("env", {})
    if isinstance(env_section, dict):
        for key, value in env_section.items():
            value = value.replace("{project}", str(project_root))
            value = value.replace("{home}", str(Path.home()))
            os.environ[key] = value

    # Expand paths — "prepend" and "bin" keys prepend to PATH
    paths_section = data.get("paths", {})
    if isinstance(paths_section, dict):
        for key, value in paths_section.items():
            if isinstance(value, str):
                value = [value]
            expanded = []
            for p in value:
                p = p.replace("{project}", str(project_root))
                p = p.replace("{home}", str(Path.home()))
                expanded.append(p)
            joined = os.pathsep.join(expanded)
            # "prepend" and "bin" are aliases for PATH
            target_var = "PATH" if key.lower() in ("prepend", "bin", "path") else key
            existing = os.environ.get(target_var, "")
            if existing:
                os.environ[target_var] = joined + os.pathsep + existing
            else:
                os.environ[target_var] = joined


def run_script(script_path: str, args: list[str]) -> None:
    """Run a Python script with an auto-bootstrapped venv.

    Finds pyproject.toml near the script, ensures a .venv/ exists beside it,
    and exec's the script with the venv's Python.
    """
    script = Path(script_path).resolve()
    if not script.is_file():
        print(f"dekk: script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    # Find pyproject.toml
    pyproject = _find_pyproject(script.parent)
    if pyproject is None:
        print(
            f"dekk: no pyproject.toml found for {script_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    venv_path = pyproject.parent / ".venv"
    venv_python = _venv_executable(venv_path, "python")

    # Bootstrap if venv missing or broken
    if not venv_python.is_file():
        _bootstrap_venv(pyproject, venv_path)

    # Optionally activate .dekk.toml environment
    dekk_toml = _find_dekk_toml(script.parent)
    if dekk_toml is not None:
        _activate_dekk_env(dekk_toml, script.parent)

    # Exec the script with the venv Python
    os.execvp(str(venv_python), [str(venv_python), str(script), *args])
