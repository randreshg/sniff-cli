"""Version manager detection -- pyenv, nvm, rbenv, rustup, etc.

Detects tool version managers and their managed installations.
Pure detection -- no side effects beyond reading filesystem and environment.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ManagedVersion:
    """A version installed by a version manager."""

    version: str
    path: Path
    is_active: bool = False


@dataclass(frozen=True)
class VersionManagerInfo:
    """Detected version manager information."""

    name: str  # "pyenv", "nvm", "rbenv", "rustup", etc.
    command: str  # binary name
    root: Path  # manager root directory (e.g., ~/.pyenv)
    active_version: str | None = None
    installed_versions: tuple[ManagedVersion, ...] = ()

    @property
    def is_available(self) -> bool:
        return self.root.exists()

    @property
    def version_count(self) -> int:
        return len(self.installed_versions)


class VersionManagerDetector:
    """Detect tool version managers and their managed installations.

    Supports: pyenv, nvm/fnm, rbenv, rustup, goenv, sdkman, asdf, mise/rtx.
    """

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def detect_all(self) -> list[VersionManagerInfo]:
        """Detect all version managers present on the system.

        Returns:
            List of VersionManagerInfo for each detected manager. Never raises.
        """
        detectors = [
            self._detect_pyenv,
            self._detect_nvm,
            self._detect_fnm,
            self._detect_rbenv,
            self._detect_rustup,
            self._detect_goenv,
            self._detect_sdkman,
            self._detect_asdf,
            self._detect_mise,
        ]

        results: list[VersionManagerInfo] = []
        for detector in detectors:
            try:
                info = detector()
                if info is not None:
                    results.append(info)
            except Exception:
                continue
        return results

    def detect(self, name: str) -> VersionManagerInfo | None:
        """Detect a specific version manager by name.

        Args:
            name: Manager name (e.g., "pyenv", "rustup").

        Returns:
            VersionManagerInfo if found, None otherwise.
        """
        dispatch = {
            "pyenv": self._detect_pyenv,
            "nvm": self._detect_nvm,
            "fnm": self._detect_fnm,
            "rbenv": self._detect_rbenv,
            "rustup": self._detect_rustup,
            "goenv": self._detect_goenv,
            "sdkman": self._detect_sdkman,
            "asdf": self._detect_asdf,
            "mise": self._detect_mise,
        }
        detector = dispatch.get(name)
        if detector is None:
            return None
        try:
            return detector()
        except Exception:
            return None

    # -- pyenv --

    def _detect_pyenv(self) -> VersionManagerInfo | None:
        pyenv_root = Path(os.environ.get("PYENV_ROOT", Path.home() / ".pyenv"))
        if not pyenv_root.is_dir():
            return None

        versions_dir = pyenv_root / "versions"
        installed = self._scan_version_dirs(versions_dir)

        active = os.environ.get("PYENV_VERSION")
        if not active:
            active = self._run_capture("pyenv", "version-name")

        if active:
            installed = tuple(
                ManagedVersion(v.version, v.path, is_active=(v.version == active))
                for v in installed
            )

        return VersionManagerInfo(
            name="pyenv",
            command="pyenv",
            root=pyenv_root,
            active_version=active,
            installed_versions=installed,
        )

    # -- nvm --

    def _detect_nvm(self) -> VersionManagerInfo | None:
        nvm_dir = Path(os.environ.get("NVM_DIR", Path.home() / ".nvm"))
        if not nvm_dir.is_dir():
            return None

        versions_dir = nvm_dir / "versions" / "node"
        installed: list[ManagedVersion] = []
        if versions_dir.is_dir():
            for d in sorted(versions_dir.iterdir()):
                if d.is_dir() and d.name.startswith("v"):
                    ver = d.name.lstrip("v")
                    installed.append(ManagedVersion(ver, d))

        active = os.environ.get("NVM_BIN")
        active_ver = None
        if active:
            # NVM_BIN is like /home/user/.nvm/versions/node/v18.17.0/bin
            parts = Path(active).parts
            for p in parts:
                if p.startswith("v") and "." in p:
                    active_ver = p.lstrip("v")
                    break

        if active_ver:
            installed = [
                ManagedVersion(v.version, v.path, is_active=(v.version == active_ver))
                for v in installed
            ]

        return VersionManagerInfo(
            name="nvm",
            command="nvm",
            root=nvm_dir,
            active_version=active_ver,
            installed_versions=tuple(installed),
        )

    # -- fnm --

    def _detect_fnm(self) -> VersionManagerInfo | None:
        if not shutil.which("fnm"):
            return None

        fnm_dir = Path(os.environ.get("FNM_DIR", Path.home() / ".fnm"))
        if not fnm_dir.is_dir():
            # Try XDG location
            xdg = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
            fnm_dir = Path(xdg) / "fnm"
            if not fnm_dir.is_dir():
                return None

        versions_dir = fnm_dir / "node-versions"
        installed: list[ManagedVersion] = []
        if versions_dir.is_dir():
            for d in sorted(versions_dir.iterdir()):
                if d.is_dir() and d.name.startswith("v"):
                    ver = d.name.lstrip("v")
                    installed.append(ManagedVersion(ver, d))

        active = self._run_capture("fnm", "current")

        if active:
            active = active.lstrip("v")
            installed = [
                ManagedVersion(v.version, v.path, is_active=(v.version == active))
                for v in installed
            ]

        return VersionManagerInfo(
            name="fnm",
            command="fnm",
            root=fnm_dir,
            active_version=active,
            installed_versions=tuple(installed),
        )

    # -- rbenv --

    def _detect_rbenv(self) -> VersionManagerInfo | None:
        rbenv_root = Path(os.environ.get("RBENV_ROOT", Path.home() / ".rbenv"))
        if not rbenv_root.is_dir():
            return None

        versions_dir = rbenv_root / "versions"
        installed = self._scan_version_dirs(versions_dir)

        active = os.environ.get("RBENV_VERSION")
        if not active:
            active = self._run_capture("rbenv", "version-name")

        if active:
            installed = tuple(
                ManagedVersion(v.version, v.path, is_active=(v.version == active))
                for v in installed
            )

        return VersionManagerInfo(
            name="rbenv",
            command="rbenv",
            root=rbenv_root,
            active_version=active,
            installed_versions=installed,
        )

    # -- rustup --

    def _detect_rustup(self) -> VersionManagerInfo | None:
        rustup_home = Path(os.environ.get("RUSTUP_HOME", Path.home() / ".rustup"))
        if not rustup_home.is_dir():
            return None

        toolchains_dir = rustup_home / "toolchains"
        installed: list[ManagedVersion] = []
        if toolchains_dir.is_dir():
            for d in sorted(toolchains_dir.iterdir()):
                if d.is_dir():
                    installed.append(ManagedVersion(d.name, d))

        # Active toolchain from env or default file
        active = os.environ.get("RUSTUP_TOOLCHAIN")
        if not active:
            default_file = rustup_home / "settings.toml"
            if default_file.exists():
                try:
                    text = default_file.read_text(encoding="utf-8")
                    m = re.search(r'default_toolchain\s*=\s*"([^"]+)"', text)
                    if m:
                        active = m.group(1)
                except OSError:
                    pass

        if active:
            installed = [
                ManagedVersion(v.version, v.path, is_active=v.version.startswith(active))
                for v in installed
            ]

        return VersionManagerInfo(
            name="rustup",
            command="rustup",
            root=rustup_home,
            active_version=active,
            installed_versions=tuple(installed),
        )

    # -- goenv --

    def _detect_goenv(self) -> VersionManagerInfo | None:
        goenv_root = Path(os.environ.get("GOENV_ROOT", Path.home() / ".goenv"))
        if not goenv_root.is_dir():
            return None

        versions_dir = goenv_root / "versions"
        installed = self._scan_version_dirs(versions_dir)

        active = os.environ.get("GOENV_VERSION")
        if not active:
            active = self._run_capture("goenv", "version-name")

        if active:
            installed = tuple(
                ManagedVersion(v.version, v.path, is_active=(v.version == active))
                for v in installed
            )

        return VersionManagerInfo(
            name="goenv",
            command="goenv",
            root=goenv_root,
            active_version=active,
            installed_versions=installed,
        )

    # -- sdkman --

    def _detect_sdkman(self) -> VersionManagerInfo | None:
        sdkman_dir = Path(os.environ.get("SDKMAN_DIR", Path.home() / ".sdkman"))
        if not sdkman_dir.is_dir():
            return None

        candidates_dir = sdkman_dir / "candidates"
        installed: list[ManagedVersion] = []
        if candidates_dir.is_dir():
            for candidate in sorted(candidates_dir.iterdir()):
                if not candidate.is_dir():
                    continue
                for ver_dir in sorted(candidate.iterdir()):
                    if ver_dir.is_dir() and ver_dir.name != "current":
                        is_active = (candidate / "current").is_symlink() and (
                            (candidate / "current").resolve() == ver_dir.resolve()
                        )
                        installed.append(ManagedVersion(
                            f"{candidate.name}/{ver_dir.name}",
                            ver_dir,
                            is_active=is_active,
                        ))

        return VersionManagerInfo(
            name="sdkman",
            command="sdk",
            root=sdkman_dir,
            installed_versions=tuple(installed),
        )

    # -- asdf --

    def _detect_asdf(self) -> VersionManagerInfo | None:
        asdf_dir = Path(os.environ.get("ASDF_DATA_DIR", Path.home() / ".asdf"))
        if not asdf_dir.is_dir():
            return None

        installs_dir = asdf_dir / "installs"
        installed: list[ManagedVersion] = []
        if installs_dir.is_dir():
            for plugin in sorted(installs_dir.iterdir()):
                if not plugin.is_dir():
                    continue
                for ver_dir in sorted(plugin.iterdir()):
                    if ver_dir.is_dir():
                        installed.append(ManagedVersion(
                            f"{plugin.name}/{ver_dir.name}",
                            ver_dir,
                        ))

        return VersionManagerInfo(
            name="asdf",
            command="asdf",
            root=asdf_dir,
            installed_versions=tuple(installed),
        )

    # -- mise (formerly rtx) --

    def _detect_mise(self) -> VersionManagerInfo | None:
        if not shutil.which("mise"):
            return None

        xdg = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        mise_dir = Path(xdg) / "mise"
        if not mise_dir.is_dir():
            # Try legacy rtx location
            mise_dir = Path(xdg) / "rtx"
            if not mise_dir.is_dir():
                return None

        installs_dir = mise_dir / "installs"
        installed: list[ManagedVersion] = []
        if installs_dir.is_dir():
            for plugin in sorted(installs_dir.iterdir()):
                if not plugin.is_dir():
                    continue
                for ver_dir in sorted(plugin.iterdir()):
                    if ver_dir.is_dir():
                        installed.append(ManagedVersion(
                            f"{plugin.name}/{ver_dir.name}",
                            ver_dir,
                        ))

        return VersionManagerInfo(
            name="mise",
            command="mise",
            root=mise_dir,
            installed_versions=tuple(installed),
        )

    # -- utilities --

    def _scan_version_dirs(self, versions_dir: Path) -> tuple[ManagedVersion, ...]:
        """Scan a directory of version subdirectories."""
        if not versions_dir.is_dir():
            return ()
        results: list[ManagedVersion] = []
        for d in sorted(versions_dir.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                results.append(ManagedVersion(d.name, d))
        return tuple(results)

    def _run_capture(self, command: str, *args: str) -> str | None:
        """Run a command and capture its stdout. Returns None on failure."""
        if not shutil.which(command):
            return None
        try:
            result = subprocess.run(
                [command, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            output = result.stdout.strip()
            return output if output else None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
