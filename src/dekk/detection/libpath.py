"""Library path resolution -- platform-aware LD_LIBRARY_PATH / DYLD_LIBRARY_PATH management.

Handles the platform-specific differences in shared library search paths:
- Linux: LD_LIBRARY_PATH
- macOS: DYLD_LIBRARY_PATH (+ DYLD_FALLBACK_LIBRARY_PATH)
- Windows: PATH (used for DLL lookup)

Pure detection and path building. apply() modifies os.environ but is the only
side-effecting method.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dekk.detection.detect import PlatformDetector, PlatformInfo


@dataclass(frozen=True)
class LibraryPathInfo:
    """Resolved library path state."""

    env_var: str  # "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", or "PATH"
    paths: tuple[str, ...]  # Ordered list of directories
    platform: PlatformInfo

    @property
    def as_string(self) -> str:
        """Join paths with the platform separator (always ':' on Unix, ';' on Windows)."""
        sep = ";" if self.platform.is_windows else ":"
        return sep.join(self.paths)

    def contains(self, path: str) -> bool:
        """Check if a directory is already in the library path."""
        normalized = str(Path(path))
        return any(str(Path(p)) == normalized for p in self.paths)


class LibraryPathResolver:
    """Platform-aware library path resolution and manipulation.

    Builds library path values without modifying the environment until
    apply() is explicitly called.

    Usage:
        resolver = LibraryPathResolver.for_current_platform()
        resolver.prepend("/opt/conda/lib")
        resolver.prepend("/usr/local/lib")
        info = resolver.resolve()
        resolver.apply()
    """

    # Map OS to the primary library path env var
    _PLATFORM_VARS: dict[str, str] = {
        "Linux": "LD_LIBRARY_PATH",
        "Darwin": "DYLD_LIBRARY_PATH",
        "Windows": "PATH",
    }

    def __init__(self, platform_info: PlatformInfo | None = None) -> None:
        """Initialize with optional platform info.

        Args:
            platform_info: Platform detection result. If None, detects automatically.
        """
        self._platform = platform_info or PlatformDetector().detect()
        self._env_var = self._PLATFORM_VARS.get(self._platform.os, "LD_LIBRARY_PATH")
        self._prepends: list[str] = []
        self._appends: list[str] = []

    @classmethod
    def for_current_platform(cls) -> LibraryPathResolver:
        """Create a resolver for the current platform."""
        return cls(PlatformDetector().detect())

    @classmethod
    def for_platform(cls, os_name: str, arch: str = "x86_64") -> LibraryPathResolver:
        """Create a resolver for a specific platform.

        Args:
            os_name: "Linux", "Darwin", or "Windows".
            arch: Architecture string.
        """
        info = PlatformInfo(os=os_name, arch=arch)
        return cls(info)

    @property
    def env_var(self) -> str:
        """The environment variable name for this platform."""
        return self._env_var

    @property
    def platform_info(self) -> PlatformInfo:
        """The platform info used by this resolver."""
        return self._platform

    def prepend(self, *paths: str) -> LibraryPathResolver:
        """Add directories to the front of the library path.

        Directories added first via prepend() appear first in the final path.
        Duplicates (against existing env, other prepends, or appends) are skipped.

        Args:
            *paths: Directory paths to prepend.

        Returns:
            Self for chaining.
        """
        for p in paths:
            normalized = str(Path(p))
            if normalized not in self._prepends and normalized not in self._appends:
                self._prepends.append(normalized)
        return self

    def append(self, *paths: str) -> LibraryPathResolver:
        """Add directories to the end of the library path.

        Duplicates (against existing env, other appends, or prepends) are skipped.

        Args:
            *paths: Directory paths to append.

        Returns:
            Self for chaining.
        """
        for p in paths:
            normalized = str(Path(p))
            if normalized not in self._appends and normalized not in self._prepends:
                self._appends.append(normalized)
        return self

    def resolve(self) -> LibraryPathInfo:
        """Resolve the final library path by combining prepends + current env + appends.

        Does NOT modify the environment.

        Returns:
            LibraryPathInfo with the computed path list.
        """
        sep = ";" if self._platform.is_windows else ":"
        current = os.environ.get(self._env_var, "")
        current_parts = [p for p in current.split(sep) if p] if current else []

        # Deduplicate: prepends first, then existing (minus duplicates), then appends
        seen: set[str] = set()
        result: list[str] = []

        for p in self._prepends:
            norm = str(Path(p))
            if norm not in seen:
                seen.add(norm)
                result.append(norm)

        for p in current_parts:
            norm = str(Path(p))
            if norm not in seen:
                seen.add(norm)
                result.append(norm)

        for p in self._appends:
            norm = str(Path(p))
            if norm not in seen:
                seen.add(norm)
                result.append(norm)

        return LibraryPathInfo(
            env_var=self._env_var,
            paths=tuple(result),
            platform=self._platform,
        )

    def apply(self) -> LibraryPathInfo:
        """Resolve and apply the library path to os.environ.

        Returns:
            The resolved LibraryPathInfo that was applied.
        """
        info = self.resolve()
        if info.paths:
            os.environ[self._env_var] = info.as_string
        return info

    def to_env_var(self) -> tuple[str, str]:
        """Return (env_var_name, value) tuple for shell.EnvVar or env.EnvVarBuilder.

        Usage with shell.EnvVar:
            from dekk.shell import EnvVar
            name, value = resolver.to_env_var()
            env = EnvVar(name=name, value=value, prepend_path=True)

        Usage with env.EnvVarBuilder:
            from dekk.execution.env import EnvVarBuilder
            builder = EnvVarBuilder()
            name, value = resolver.to_env_var()
            builder.set(name, value)
        """
        info = self.resolve()
        return (info.env_var, info.as_string)

    def configure_builder(self, builder: object) -> None:
        """Apply resolved library paths to an EnvVarBuilder.

        Works with both dekk.execution.env.EnvVarBuilder and dekk.execution.toolchain.EnvVarBuilder.

        Args:
            builder: An EnvVarBuilder instance (from dekk.execution.env or dekk.execution.toolchain).
        """
        name, value = self.to_env_var()
        if not value:
            return
        # dekk.execution.env.EnvVarBuilder uses set_from_path / set
        if hasattr(builder, "set_from_path"):
            info = self.resolve()
            builder.set_from_path(name, list(info.paths))
        # dekk.execution.toolchain.EnvVarBuilder uses prepend_var
        elif hasattr(builder, "prepend_var"):
            builder.prepend_var(name, value)
        else:
            raise TypeError(f"Unsupported builder type: {type(builder).__name__}")
