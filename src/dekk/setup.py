"""Project environment setup: conda env creation + npm package installation.

Reads .dekk.toml and provisions the complete environment:
  1. Creates conda env with declared packages (if [conda] present)
  2. Installs npm packages into the conda env (if [npm] present)
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

CONDA_FORGE_CHANNEL: Final = "conda-forge"
NPM_COMMAND: Final = "npm"
CONDA_COMMANDS: Final = ("mamba", "conda")


@dataclass
class SetupResult:
    """Summary of what was set up."""

    conda_created: bool = False
    conda_prefix: Path | None = None
    conda_packages: list[str] = field(default_factory=list)
    npm_installed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def _find_conda_cmd() -> str | None:
    """Find conda or mamba on PATH."""
    for cmd in CONDA_COMMANDS:
        if shutil.which(cmd):
            return cmd
    return None


def _conda_env_exists(conda_cmd: str, env_name: str) -> Path | None:
    """Check if a conda env exists, return its prefix or None."""
    from dekk.conda import CondaDetector

    return CondaDetector().find_prefix(env_name)


def setup_conda(
    env_name: str,
    packages: tuple[str, ...] = (),
    channel: str = CONDA_FORGE_CHANNEL,
    env_file: str | None = None,
    project_root: Path | None = None,
    force: bool = False,
) -> tuple[Path | None, bool, list[str]]:
    """Create or update a conda environment.

    Returns:
        (prefix, was_created, errors)
    """
    conda_cmd = _find_conda_cmd()
    if not conda_cmd:
        return None, False, ["conda/mamba not found on PATH"]

    existing = _conda_env_exists(conda_cmd, env_name)
    if existing and not force:
        return existing, False, []

    errors: list[str] = []

    if env_file and project_root:
        env_file_path = project_root / env_file
        if env_file_path.is_file():
            cmd = [conda_cmd, "env", "create", "-f", str(env_file_path), "-y"]
            if force and existing:
                cmd.append("--force")
        else:
            errors.append(f"Environment file not found: {env_file_path}")
            return None, False, errors
    else:
        cmd = [conda_cmd, "create", "-n", env_name, "-c", channel, "-y"]
        cmd.extend(packages)

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
            errors.append(f"conda create failed: {stderr[:500]}")
            return None, False, errors
    except subprocess.TimeoutExpired:
        errors.append("conda create timed out (10 minutes)")
        return None, False, errors
    except OSError as exc:
        errors.append(f"Failed to run {conda_cmd}: {exc}")
        return None, False, errors

    prefix = _conda_env_exists(conda_cmd, env_name)
    return prefix, True, errors


def setup_npm(
    conda_prefix: Path,
    packages: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Install npm packages globally into a conda environment.

    Args:
        conda_prefix: Conda env prefix (has bin/npm).
        packages: {name: version} dict.

    Returns:
        (installed_names, errors)
    """
    npm_bin = conda_prefix / "bin" / NPM_COMMAND
    if not npm_bin.is_file():
        return [], [f"npm not found at {npm_bin} — add nodejs to conda packages"]

    node_bin = conda_prefix / "bin" / "node"
    env = {
        "PATH": f"{conda_prefix / 'bin'}:{_system_path()}",
        "HOME": str(Path.home()),
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


def _system_path() -> str:
    """Get the system PATH without conda modifications."""
    import os

    return os.environ.get("PATH", "/usr/bin:/bin")


def run_setup(
    project_root: Path,
    force: bool = False,
) -> SetupResult:
    """Set up the complete project environment from .dekk.toml.

    1. Creates conda env with declared packages (if [conda])
    2. Installs npm packages into that env (if [npm])

    Args:
        project_root: Project root directory.
        force: Recreate conda env even if it exists.

    Returns:
        SetupResult with details of what was done.
    """
    from dekk.envspec import EnvironmentSpec

    spec_file = project_root / ".dekk.toml"
    spec = EnvironmentSpec.from_file(spec_file)
    result = SetupResult()

    # Step 1: Conda environment
    if spec.conda:
        prefix, created, errors = setup_conda(
            env_name=spec.conda.name,
            packages=spec.conda.packages,
            channel=spec.conda.channel,
            env_file=spec.conda.file,
            project_root=project_root,
            force=force,
        )
        result.conda_prefix = prefix
        result.conda_created = created
        result.conda_packages = list(spec.conda.packages)
        result.errors.extend(errors)

        # Step 2: Npm packages (requires conda env with nodejs)
        if prefix and spec.npm and spec.npm.packages:
            installed, npm_errors = setup_npm(prefix, spec.npm.packages)
            result.npm_installed = installed
            result.errors.extend(npm_errors)
        elif spec.npm and spec.npm.packages and not prefix:
            result.errors.append(
                "Cannot install npm packages: conda environment not available"
            )
    elif spec.npm and spec.npm.packages:
        result.errors.append(
            "Cannot install npm packages: no [conda] section with nodejs"
        )

    return result
