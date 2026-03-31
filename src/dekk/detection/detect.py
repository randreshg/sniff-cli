"""Platform detection - OS, architecture, distro, WSL, containers."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformInfo:
    """Platform detection results."""

    os: str  # "Linux", "Darwin", "Windows"
    arch: str  # "x86_64", "aarch64", "arm64"
    distro: str | None = None  # "ubuntu", "fedora", etc. (Linux only)
    distro_version: str | None = None  # "22.04", "39", etc.
    is_wsl: bool = False
    is_container: bool = False
    pkg_manager: str | None = None  # "apt", "dnf", "brew", etc.

    @property
    def is_linux(self) -> bool:
        """True if running on Linux."""
        return self.os == "Linux"

    @property
    def is_macos(self) -> bool:
        """True if running on macOS."""
        return self.os == "Darwin"

    @property
    def is_windows(self) -> bool:
        """True if running on Windows."""
        return self.os == "Windows"


class PlatformDetector:
    """Detect current platform information."""

    def detect(self) -> PlatformInfo:
        """
        Detect platform information.

        Always succeeds (never raises).

        Returns:
            PlatformInfo with detected platform details.
        """
        os_name = platform.system()
        arch = self._detect_arch()
        distro = None
        distro_version = None
        is_wsl = False
        is_container = False
        pkg_manager = None

        if os_name == "Linux":
            distro, distro_version = self._detect_linux_distro()
            is_wsl = self._detect_wsl()
            is_container = self._detect_container()
            pkg_manager = self._detect_linux_pkg_manager(distro)
        elif os_name == "Darwin":
            pkg_manager = self._detect_macos_pkg_manager()
        elif os_name == "Windows":
            pkg_manager = self._detect_windows_pkg_manager()

        return PlatformInfo(
            os=os_name,
            arch=arch,
            distro=distro,
            distro_version=distro_version,
            is_wsl=is_wsl,
            is_container=is_container,
            pkg_manager=pkg_manager,
        )

    def _detect_arch(self) -> str:
        """Detect and normalize architecture."""
        machine = platform.machine().lower()
        # Normalize common variations
        if machine in ("x86_64", "amd64"):
            return "x86_64"
        elif machine in ("aarch64", "arm64"):
            return "aarch64"
        return machine

    def _detect_linux_distro(self) -> tuple[str | None, str | None]:
        """Detect Linux distribution and version."""
        try:
            # Try Python 3.10+ freedesktop_os_release
            import platform as p

            os_release = p.freedesktop_os_release()
            return os_release.get("ID"), os_release.get("VERSION_ID")
        except (AttributeError, OSError):
            pass

        # Fallback: parse /etc/os-release manually
        os_release_path = Path("/etc/os-release")
        if os_release_path.exists():
            try:
                with open(os_release_path) as f:
                    data = {}
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            key, value = line.split("=", 1)
                            data[key] = value.strip('"')
                return data.get("ID"), data.get("VERSION_ID")
            except OSError:
                pass

        return None, None

    def _detect_wsl(self) -> bool:
        """Detect if running in Windows Subsystem for Linux."""
        proc_version = Path("/proc/version")
        if proc_version.exists():
            try:
                with open(proc_version) as f:
                    content = f.read().lower()
                    return "microsoft" in content or "wsl" in content
            except OSError:
                pass
        return False

    def _detect_container(self) -> bool:
        """Detect if running in a container."""
        # Check for Docker
        if Path("/.dockerenv").exists():
            return True

        # Check for Podman
        if Path("/run/.containerenv").exists():
            return True

        # Check cgroup (works for most containers)
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            try:
                with open(cgroup) as f:
                    content = f.read().lower()
                    return any(
                        keyword in content for keyword in ["docker", "kubepods", "lxc", "podman"]
                    )
            except OSError:
                pass

        return False

    def _detect_linux_pkg_manager(self, distro: str | None) -> str | None:
        """Detect Linux package manager based on distro."""
        # Map distros to common package managers
        distro_map = {
            "ubuntu": "apt",
            "debian": "apt",
            "fedora": "dnf",
            "centos": "dnf",
            "rhel": "dnf",
            "rocky": "dnf",
            "alma": "dnf",
            "arch": "pacman",
            "manjaro": "pacman",
        }

        if distro and distro in distro_map:
            return distro_map[distro]

        # Fallback: check for package manager binaries
        import shutil

        for pm in ["apt", "dnf", "yum", "pacman", "zypper", "apk"]:
            if shutil.which(pm):
                return pm

        return None

    def _detect_macos_pkg_manager(self) -> str | None:
        """Detect macOS package manager."""
        import shutil

        if shutil.which("brew"):
            return "brew"
        elif shutil.which("port"):
            return "port"
        return None

    def _detect_windows_pkg_manager(self) -> str | None:
        """Detect Windows package manager."""
        import shutil

        if shutil.which("winget"):
            return "winget"
        elif shutil.which("choco"):
            return "choco"
        elif shutil.which("scoop"):
            return "scoop"
        return None
