"""Path detection and resolution -- project roots, tool paths, OS-aware user directories.

Detects project root directories by walking up from a starting point and
looking for marker files. Resolves tool binary paths. Provides OS-aware
user directory conventions (XDG on Linux, ~/Library on macOS, AppData on Windows).

Pure detection -- no side effects, no file writes, no env var mutations.
"""

from __future__ import annotations

import enum
import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


class PathCategory(enum.Enum):
    """Category of a resolved path."""

    PROJECT_ROOT = "project_root"
    CONFIG = "config"
    BUILD = "build"
    SOURCE = "source"
    TOOL = "tool"
    LIBRARY = "library"
    DATA = "data"
    CACHE = "cache"
    STATE = "state"


@dataclass(frozen=True)
class ResolvedPath:
    """A resolved filesystem path with metadata."""

    path: Path
    category: PathCategory
    exists: bool = False
    label: str = ""


@dataclass(frozen=True)
class ToolPath:
    """A resolved tool binary path."""

    name: str
    path: Path | None = None
    version: str | None = None

    @property
    def found(self) -> bool:
        """True if the tool was found on PATH."""
        return self.path is not None


@dataclass(frozen=True)
class LibraryPath:
    """A resolved library/include path."""

    name: str
    lib_dir: Path | None = None
    include_dir: Path | None = None

    @property
    def found(self) -> bool:
        """True if at least the lib directory was found."""
        return self.lib_dir is not None


@dataclass(frozen=True)
class ProjectPaths:
    """OS-aware user directory conventions."""

    data_dir: Path
    config_dir: Path
    cache_dir: Path
    state_dir: Path


# Default markers used to identify a project root.
DEFAULT_ROOT_MARKERS: tuple[str, ...] = (
    ".git",
    "Cargo.toml",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Makefile",
    "CMakeLists.txt",
    "BUILD.bazel",
    "WORKSPACE",
    "MODULE.bazel",
)

# Common build output directories.
_BUILD_DIRS: tuple[str, ...] = (
    "target",
    "build",
    "dist",
    "_build",
    "out",
    ".build",
)

# Common source directories.
_SOURCE_DIRS: tuple[str, ...] = (
    "src",
    "lib",
    "crates",
    "packages",
    "apps",
    "cmd",
    "pkg",
    "internal",
)

# Common config directories.
_CONFIG_DIRS: tuple[str, ...] = (
    ".sniff",
    ".apxm",
    ".config",
    ".vscode",
    ".idea",
)


class PathManager:
    """Detect and resolve project paths.

    All methods follow the sniff never-raises contract: errors are
    swallowed and result in None or empty values.
    """

    def find_project_root(
        self,
        start: Path | None = None,
        markers: Sequence[str] | None = None,
    ) -> Path | None:
        """Walk up from *start* to find the nearest project root.

        A directory is considered a project root if it contains any of the
        *markers* (files or directories).

        Args:
            start: Starting directory. Defaults to cwd.
            markers: File/directory names to look for. Defaults to common
                     project markers (.git, Cargo.toml, pyproject.toml, ...).

        Returns:
            Path to the project root, or None if not found. Never raises.
        """
        try:
            current = (start or Path.cwd()).resolve()
        except (OSError, ValueError):
            return None

        marker_names = tuple(markers) if markers else DEFAULT_ROOT_MARKERS

        try:
            while True:
                for marker in marker_names:
                    if (current / marker).exists():
                        return current
                parent = current.parent
                if parent == current:
                    break
                current = parent
        except (OSError, PermissionError):
            pass

        return None

    def detect(self, root: Path | None = None) -> tuple[ResolvedPath, ...]:
        """Detect notable paths within a project.

        Scans *root* for common build, source, and config directories and
        returns them as categorised :class:`ResolvedPath` entries.

        Args:
            root: Project root directory. If None, attempts to find one
                  via :meth:`find_project_root`.

        Returns:
            Tuple of ResolvedPath entries. Never raises.
        """
        if root is None:
            root = self.find_project_root()
        if root is None:
            return ()

        try:
            root = root.resolve()
            if not root.is_dir():
                return ()
        except (OSError, PermissionError):
            return ()

        results: list[ResolvedPath] = []

        # Project root itself
        results.append(ResolvedPath(
            path=root,
            category=PathCategory.PROJECT_ROOT,
            exists=True,
            label="project root",
        ))

        # Config directories
        for name in _CONFIG_DIRS:
            p = root / name
            try:
                exists = p.is_dir()
            except (OSError, PermissionError):
                exists = False
            if exists:
                results.append(ResolvedPath(
                    path=p,
                    category=PathCategory.CONFIG,
                    exists=True,
                    label=name,
                ))

        # Build directories
        for name in _BUILD_DIRS:
            p = root / name
            try:
                exists = p.is_dir()
            except (OSError, PermissionError):
                exists = False
            if exists:
                results.append(ResolvedPath(
                    path=p,
                    category=PathCategory.BUILD,
                    exists=True,
                    label=name,
                ))

        # Source directories
        for name in _SOURCE_DIRS:
            p = root / name
            try:
                exists = p.is_dir()
            except (OSError, PermissionError):
                exists = False
            if exists:
                results.append(ResolvedPath(
                    path=p,
                    category=PathCategory.SOURCE,
                    exists=True,
                    label=name,
                ))

        return tuple(results)

    def user_dirs(self, app_name: str) -> ProjectPaths:
        """Return OS-aware user directories for *app_name*.

        Follows platform conventions:
        - Linux: XDG Base Directory Specification
        - macOS: ~/Library hierarchy
        - Windows: APPDATA / LOCALAPPDATA

        Args:
            app_name: Application name (e.g., "apxm", "sniff").

        Returns:
            ProjectPaths with resolved directories. Never raises.
        """
        system = platform.system()

        try:
            home = Path.home()
        except RuntimeError:
            home = Path("/tmp")

        if system == "Darwin":
            return ProjectPaths(
                data_dir=home / "Library" / "Application Support" / app_name,
                config_dir=home / "Library" / "Preferences" / app_name,
                cache_dir=home / "Library" / "Caches" / app_name,
                state_dir=home / "Library" / "Application Support" / app_name,
            )

        if system == "Windows":
            appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
            return ProjectPaths(
                data_dir=appdata / app_name,
                config_dir=appdata / app_name,
                cache_dir=local / app_name / "cache",
                state_dir=local / app_name,
            )

        # Linux / other -- XDG
        data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        cache_home = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
        state_home = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state"))

        return ProjectPaths(
            data_dir=data_home / app_name,
            config_dir=config_home / app_name,
            cache_dir=cache_home / app_name,
            state_dir=state_home / app_name,
        )

    def resolve_tool(self, name: str) -> ToolPath:
        """Resolve a tool binary on PATH.

        Args:
            name: Tool name (e.g., "cargo", "cmake", "python3").

        Returns:
            ToolPath with the resolved path, or path=None if not found.
            Never raises.
        """
        try:
            found = shutil.which(name)
        except (OSError, ValueError):
            found = None

        return ToolPath(
            name=name,
            path=Path(found) if found else None,
        )

    def resolve_tools(self, names: Sequence[str]) -> tuple[ToolPath, ...]:
        """Resolve multiple tool binaries on PATH.

        Args:
            names: Tool names to resolve.

        Returns:
            Tuple of ToolPath results (one per name, same order). Never raises.
        """
        return tuple(self.resolve_tool(n) for n in names)

    def resolve_library(
        self,
        name: str,
        search_paths: Sequence[Path] | None = None,
    ) -> LibraryPath:
        """Resolve a library's lib and include directories.

        Searches standard system paths and any additional *search_paths*.

        Args:
            name: Library name (e.g., "llvm", "openssl").
            search_paths: Additional directories to search.

        Returns:
            LibraryPath with resolved directories. Never raises.
        """
        candidates: list[Path] = []

        if search_paths:
            candidates.extend(search_paths)

        # Standard system library paths
        system = platform.system()
        if system == "Linux":
            candidates.extend([
                Path("/usr/lib"),
                Path("/usr/lib64"),
                Path("/usr/local/lib"),
                Path("/usr/local/lib64"),
            ])
        elif system == "Darwin":
            candidates.extend([
                Path("/usr/local/lib"),
                Path("/opt/homebrew/lib"),
                Path("/usr/lib"),
            ])

        lib_dir: Path | None = None
        include_dir: Path | None = None

        for base in candidates:
            try:
                # Check for lib directory or library files
                lib_candidate = base / name
                if lib_candidate.is_dir():
                    lib_dir = lib_candidate
                    break
                # Check for libNAME pattern in the directory
                if base.is_dir():
                    for child in base.iterdir():
                        if child.name.startswith(f"lib{name}"):
                            lib_dir = base
                            break
                    if lib_dir is not None:
                        break
            except (OSError, PermissionError):
                continue

        # Try to find include directory
        include_candidates: list[Path] = []
        if search_paths:
            for sp in search_paths:
                include_candidates.append(sp.parent / "include" if sp.name == "lib" else sp / "include")
        if system == "Linux":
            include_candidates.extend([
                Path("/usr/include"),
                Path("/usr/local/include"),
            ])
        elif system == "Darwin":
            include_candidates.extend([
                Path("/usr/local/include"),
                Path("/opt/homebrew/include"),
                Path("/usr/include"),
            ])

        for base in include_candidates:
            try:
                inc_candidate = base / name
                if inc_candidate.is_dir():
                    include_dir = inc_candidate
                    break
            except (OSError, PermissionError):
                continue

        return LibraryPath(
            name=name,
            lib_dir=lib_dir,
            include_dir=include_dir,
        )
