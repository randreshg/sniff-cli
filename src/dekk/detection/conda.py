"""Conda environment detection."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Common conda installation paths (relative to $HOME, except /opt/conda).
# Used as fallback when conda/mamba is not on PATH.
COMMON_INSTALL_PATHS: tuple[str, ...] = (
    "miniforge3",
    "mambaforge",
    "miniconda3",
    "anaconda3",
)


@dataclass(frozen=True)
class CondaEnvironment:
    """Conda environment information."""

    name: str
    prefix: Path
    is_active: bool = False
    python_version: str | None = None


@dataclass(frozen=True)
class CondaValidation:
    """Result of validating a conda environment."""

    env_name: str
    found: bool
    prefix: Path | None = None
    is_active: bool = False
    missing_packages: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """True when the environment exists and has all required packages."""
        return self.found and len(self.missing_packages) == 0 and len(self.errors) == 0


class CondaDetector:
    """Detect conda/mamba environments."""

    def __init__(self, timeout: float = 10.0):
        """
        Initialize conda detector.

        Args:
            timeout: Timeout for conda commands.
        """
        self.timeout = timeout

    def find_active(self) -> CondaEnvironment | None:
        """
        Find the currently active conda environment.

        Returns:
            CondaEnvironment if one is active, None otherwise.
        """
        conda_prefix = os.environ.get("CONDA_PREFIX")
        conda_name = os.environ.get("CONDA_DEFAULT_ENV")

        if not conda_prefix:
            return None

        prefix = Path(conda_prefix)
        name = conda_name or prefix.name

        # Try to get Python version
        python_version = self._get_python_version(prefix)

        return CondaEnvironment(
            name=name, prefix=prefix, is_active=True, python_version=python_version
        )

    def find_environment(self, name: str) -> CondaEnvironment | None:
        """
        Find a conda environment by name.

        Args:
            name: Environment name to search for.

        Returns:
            CondaEnvironment if found, None otherwise.
        """
        # Check if conda is available
        import shutil

        conda_cmd = shutil.which("conda") or shutil.which("mamba")
        if not conda_cmd:
            return None

        try:
            # Get list of environments
            result = subprocess.run(
                [conda_cmd, "env", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )

            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)
            envs = data.get("envs", [])

            # Find matching environment
            for env_path in envs:
                env_path = Path(env_path)
                if env_path.name == name:
                    # Check if this is the active environment
                    active_prefix = os.environ.get("CONDA_PREFIX")
                    is_active = str(env_path) == active_prefix

                    python_version = self._get_python_version(env_path)

                    return CondaEnvironment(
                        name=name,
                        prefix=env_path,
                        is_active=is_active,
                        python_version=python_version,
                    )

            return None

        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return None

    def find_prefix(self, env_name: str, *, probe_common: bool = True) -> Path | None:
        """Find a conda environment prefix by name.

        Searches in order:
        1. Currently active environment (if its name matches *env_name*).
        2. ``conda env list --json`` / ``mamba env list --json``.
        3. Common installation paths under ``$HOME`` and ``/opt/conda``
           (only when *probe_common* is True).

        Args:
            env_name: Environment name to look for.
            probe_common: When True, probe well-known filesystem paths as a
                fallback when conda/mamba is not on PATH.

        Returns:
            Path to the environment prefix, or None if not found.
        """
        # 1. Active environment
        active = self.find_active()
        if active is not None and active.name == env_name:
            return active.prefix

        # 2. Query conda/mamba
        env = self.find_environment(env_name)
        if env is not None:
            return env.prefix

        # 3. Probe common paths
        if probe_common:
            for candidate in self._common_prefix_candidates(env_name):
                try:
                    if candidate.is_dir():
                        return candidate
                except OSError:
                    continue

        return None

    def validate(
        self,
        env_name: str,
        *,
        required_packages: list[str] | None = None,
    ) -> CondaValidation:
        """Validate that a conda environment exists and contains required packages.

        Args:
            env_name: Environment name to validate.
            required_packages: Package names that must be installed in the
                environment (checked via ``conda list --json``).

        Returns:
            A CondaValidation result.
        """
        prefix = self.find_prefix(env_name)
        if prefix is None:
            return CondaValidation(
                env_name=env_name,
                found=False,
                errors=(f"Environment '{env_name}' not found",),
            )

        active = self.find_active()
        is_active = active is not None and active.prefix == prefix

        if not required_packages:
            return CondaValidation(
                env_name=env_name,
                found=True,
                prefix=prefix,
                is_active=is_active,
            )

        # Check installed packages
        missing = self._check_packages(prefix, required_packages)

        return CondaValidation(
            env_name=env_name,
            found=True,
            prefix=prefix,
            is_active=is_active,
            missing_packages=tuple(missing),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _common_prefix_candidates(env_name: str) -> list[Path]:
        """Build a list of candidate paths for *env_name* under common install locations."""
        home = Path.home()
        candidates = [home / base / "envs" / env_name for base in COMMON_INSTALL_PATHS]
        candidates.append(Path("/opt/conda/envs") / env_name)
        return candidates

    def _check_packages(self, prefix: Path, packages: list[str]) -> list[str]:
        """Return names from *packages* that are NOT installed in *prefix*."""
        import shutil

        conda_cmd = shutil.which("conda") or shutil.which("mamba")
        if not conda_cmd:
            # Cannot verify -- assume all missing
            return list(packages)

        try:
            result = subprocess.run(
                [conda_cmd, "list", "--prefix", str(prefix), "--json"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            if result.returncode != 0:
                return list(packages)

            installed = {pkg["name"] for pkg in json.loads(result.stdout)}
            return [p for p in packages if p not in installed]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, KeyError):
            return list(packages)

    def _get_python_version(self, prefix: Path) -> str | None:
        """Get Python version in a conda environment."""
        # Try to find python executable
        if os.name == "nt":  # Windows
            python_path = prefix / "python.exe"
        else:  # Unix
            python_path = prefix / "bin" / "python"

        if not python_path.exists():
            return None

        try:
            result = subprocess.run(
                [str(python_path), "--version"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )

            output = result.stdout + result.stderr
            # Parse "Python X.Y.Z"
            import re

            match = re.search(r"Python\s+(\d+\.\d+\.\d+)", output)
            if match:
                return match.group(1)

            return None

        except (subprocess.TimeoutExpired, OSError):
            return None
