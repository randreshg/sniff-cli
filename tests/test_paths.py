"""Tests for path detection and resolution."""

from pathlib import Path

import pytest

from sniff.paths import (
    LibraryPath,
    PathCategory,
    PathManager,
    ProjectPaths,
    ResolvedPath,
    ToolPath,
)


# ---------------------------------------------------------------------------
# Dataclass construction and immutability
# ---------------------------------------------------------------------------


class TestPathCategory:
    def test_enum_values(self):
        """All expected categories exist."""
        assert PathCategory.PROJECT_ROOT.value == "project_root"
        assert PathCategory.CONFIG.value == "config"
        assert PathCategory.BUILD.value == "build"
        assert PathCategory.SOURCE.value == "source"
        assert PathCategory.TOOL.value == "tool"
        assert PathCategory.LIBRARY.value == "library"
        assert PathCategory.DATA.value == "data"
        assert PathCategory.CACHE.value == "cache"
        assert PathCategory.STATE.value == "state"


class TestResolvedPath:
    def test_construct(self):
        rp = ResolvedPath(
            path=Path("/tmp/proj"),
            category=PathCategory.PROJECT_ROOT,
            exists=True,
            label="project root",
        )
        assert rp.path == Path("/tmp/proj")
        assert rp.category == PathCategory.PROJECT_ROOT
        assert rp.exists is True
        assert rp.label == "project root"

    def test_frozen(self):
        rp = ResolvedPath(path=Path("/tmp"), category=PathCategory.BUILD)
        with pytest.raises(AttributeError):
            rp.path = Path("/other")  # type: ignore[misc]

    def test_defaults(self):
        rp = ResolvedPath(path=Path("/tmp"), category=PathCategory.SOURCE)
        assert rp.exists is False
        assert rp.label == ""


class TestToolPath:
    def test_found(self):
        tp = ToolPath(name="cargo", path=Path("/usr/bin/cargo"))
        assert tp.found is True

    def test_not_found(self):
        tp = ToolPath(name="nonexistent")
        assert tp.found is False
        assert tp.path is None

    def test_frozen(self):
        tp = ToolPath(name="cargo")
        with pytest.raises(AttributeError):
            tp.name = "other"  # type: ignore[misc]


class TestLibraryPath:
    def test_found(self):
        lp = LibraryPath(name="llvm", lib_dir=Path("/usr/lib/llvm"))
        assert lp.found is True

    def test_not_found(self):
        lp = LibraryPath(name="nonexistent")
        assert lp.found is False

    def test_frozen(self):
        lp = LibraryPath(name="llvm")
        with pytest.raises(AttributeError):
            lp.name = "other"  # type: ignore[misc]

    def test_with_include(self):
        lp = LibraryPath(
            name="openssl",
            lib_dir=Path("/usr/lib"),
            include_dir=Path("/usr/include/openssl"),
        )
        assert lp.found is True
        assert lp.include_dir == Path("/usr/include/openssl")


class TestProjectPaths:
    def test_construct(self):
        pp = ProjectPaths(
            data_dir=Path("/data"),
            config_dir=Path("/config"),
            cache_dir=Path("/cache"),
            state_dir=Path("/state"),
        )
        assert pp.data_dir == Path("/data")
        assert pp.config_dir == Path("/config")
        assert pp.cache_dir == Path("/cache")
        assert pp.state_dir == Path("/state")

    def test_frozen(self):
        pp = ProjectPaths(
            data_dir=Path("/d"),
            config_dir=Path("/c"),
            cache_dir=Path("/ca"),
            state_dir=Path("/s"),
        )
        with pytest.raises(AttributeError):
            pp.data_dir = Path("/other")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PathManager.find_project_root
# ---------------------------------------------------------------------------


@pytest.fixture
def manager():
    return PathManager()


class TestFindProjectRoot:
    def test_finds_git_root(self, tmp_path, manager):
        """Detects .git directory as project root."""
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)

        root = manager.find_project_root(start=sub)
        assert root == tmp_path

    def test_finds_cargo_toml(self, tmp_path, manager):
        """Detects Cargo.toml as project root."""
        (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
        sub = tmp_path / "crates" / "core"
        sub.mkdir(parents=True)

        root = manager.find_project_root(start=sub)
        assert root == tmp_path

    def test_finds_pyproject_toml(self, tmp_path, manager):
        """Detects pyproject.toml as project root."""
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        sub = tmp_path / "src" / "pkg"
        sub.mkdir(parents=True)

        root = manager.find_project_root(start=sub)
        assert root == tmp_path

    def test_custom_markers(self, tmp_path, manager):
        """Supports custom marker files/directories."""
        (tmp_path / "MY_PROJECT_ROOT").write_text("", encoding="utf-8")
        sub = tmp_path / "deep" / "nested"
        sub.mkdir(parents=True)

        root = manager.find_project_root(start=sub, markers=["MY_PROJECT_ROOT"])
        assert root == tmp_path

    def test_multiple_markers(self, tmp_path, manager):
        """Stops at nearest match with multiple markers."""
        (tmp_path / "Cargo.toml").write_text("", encoding="utf-8")
        inner = tmp_path / "inner"
        inner.mkdir()
        (inner / "pyproject.toml").write_text("", encoding="utf-8")
        deep = inner / "src"
        deep.mkdir()

        root = manager.find_project_root(start=deep)
        assert root == inner

    def test_returns_none_when_no_markers(self, tmp_path, manager):
        """Returns None when no markers found."""
        sub = tmp_path / "empty"
        sub.mkdir()

        root = manager.find_project_root(
            start=sub,
            markers=["DOES_NOT_EXIST_MARKER_FILE"],
        )
        assert root is None

    def test_nonexistent_start(self, manager):
        """Returns None for non-existent start path."""
        root = manager.find_project_root(
            start=Path("/does/not/exist/at/all"),
            markers=["something"],
        )
        assert root is None

    def test_start_is_root_itself(self, tmp_path, manager):
        """Returns root when start directory IS the project root."""
        (tmp_path / ".git").mkdir()

        root = manager.find_project_root(start=tmp_path)
        assert root == tmp_path

    def test_never_raises(self, manager):
        """find_project_root never raises, always returns Path or None."""
        result = manager.find_project_root(start=Path("/nonexistent"))
        assert result is None


# ---------------------------------------------------------------------------
# PathManager.detect
# ---------------------------------------------------------------------------


class TestDetect:
    def test_detects_project_root(self, tmp_path, manager):
        """detect() includes the project root itself."""
        (tmp_path / ".git").mkdir()

        results = manager.detect(root=tmp_path)
        roots = [r for r in results if r.category == PathCategory.PROJECT_ROOT]
        assert len(roots) == 1
        assert roots[0].exists is True

    def test_detects_source_dirs(self, tmp_path, manager):
        """detect() finds common source directories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "lib").mkdir()

        results = manager.detect(root=tmp_path)
        source_labels = {r.label for r in results if r.category == PathCategory.SOURCE}
        assert "src" in source_labels
        assert "lib" in source_labels

    def test_detects_build_dirs(self, tmp_path, manager):
        """detect() finds common build output directories."""
        (tmp_path / "target").mkdir()
        (tmp_path / "build").mkdir()
        (tmp_path / "dist").mkdir()

        results = manager.detect(root=tmp_path)
        build_labels = {r.label for r in results if r.category == PathCategory.BUILD}
        assert "target" in build_labels
        assert "build" in build_labels
        assert "dist" in build_labels

    def test_detects_config_dirs(self, tmp_path, manager):
        """detect() finds config directories."""
        (tmp_path / ".vscode").mkdir()
        (tmp_path / ".config").mkdir()

        results = manager.detect(root=tmp_path)
        config_labels = {r.label for r in results if r.category == PathCategory.CONFIG}
        assert ".vscode" in config_labels
        assert ".config" in config_labels

    def test_empty_directory(self, tmp_path, manager):
        """detect() on empty dir returns only the root."""
        results = manager.detect(root=tmp_path)
        assert len(results) == 1
        assert results[0].category == PathCategory.PROJECT_ROOT

    def test_nonexistent_root(self, manager):
        """detect() returns empty tuple for non-existent root."""
        results = manager.detect(root=Path("/does/not/exist/ever"))
        assert results == ()

    def test_none_root_uses_find(self, tmp_path, manager, monkeypatch):
        """detect(root=None) tries to find_project_root."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)

        results = manager.detect(root=None)
        roots = [r for r in results if r.category == PathCategory.PROJECT_ROOT]
        assert len(roots) == 1

    def test_all_results_are_frozen(self, tmp_path, manager):
        """All returned ResolvedPath instances are frozen."""
        (tmp_path / "src").mkdir()
        results = manager.detect(root=tmp_path)
        for rp in results:
            with pytest.raises(AttributeError):
                rp.label = "modified"  # type: ignore[misc]

    def test_returns_tuple(self, tmp_path, manager):
        """detect() returns a tuple, not a list."""
        results = manager.detect(root=tmp_path)
        assert isinstance(results, tuple)


# ---------------------------------------------------------------------------
# PathManager.user_dirs
# ---------------------------------------------------------------------------


class TestUserDirs:
    def test_returns_project_paths(self, manager):
        """user_dirs returns a ProjectPaths instance."""
        dirs = manager.user_dirs("myapp")
        assert isinstance(dirs, ProjectPaths)

    def test_app_name_in_paths(self, manager):
        """App name appears in all directory paths."""
        dirs = manager.user_dirs("testapp")
        assert "testapp" in str(dirs.data_dir)
        assert "testapp" in str(dirs.config_dir)
        assert "testapp" in str(dirs.cache_dir)
        assert "testapp" in str(dirs.state_dir)

    def test_frozen(self, manager):
        """ProjectPaths is immutable."""
        dirs = manager.user_dirs("myapp")
        with pytest.raises(AttributeError):
            dirs.data_dir = Path("/other")  # type: ignore[misc]

    def test_xdg_override(self, manager, monkeypatch, tmp_path):
        """XDG environment variables are respected on Linux."""
        monkeypatch.setattr("sniff.paths.platform.system", lambda: "Linux")

        xdg_data = tmp_path / "data"
        xdg_config = tmp_path / "config"
        xdg_cache = tmp_path / "cache"
        xdg_state = tmp_path / "state"

        monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
        monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))
        monkeypatch.setenv("XDG_STATE_HOME", str(xdg_state))

        dirs = manager.user_dirs("testapp")
        assert dirs.data_dir == xdg_data / "testapp"
        assert dirs.config_dir == xdg_config / "testapp"
        assert dirs.cache_dir == xdg_cache / "testapp"
        assert dirs.state_dir == xdg_state / "testapp"

    def test_macos_dirs(self, manager, monkeypatch):
        """macOS uses ~/Library hierarchy."""
        monkeypatch.setattr("sniff.paths.platform.system", lambda: "Darwin")

        dirs = manager.user_dirs("testapp")
        assert "Library" in str(dirs.data_dir)
        assert "Library" in str(dirs.config_dir)
        assert "Library" in str(dirs.cache_dir)

    def test_windows_dirs(self, manager, monkeypatch, tmp_path):
        """Windows uses APPDATA / LOCALAPPDATA."""
        monkeypatch.setattr("sniff.paths.platform.system", lambda: "Windows")
        monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

        dirs = manager.user_dirs("testapp")
        assert "AppData" in str(dirs.data_dir)
        assert "testapp" in str(dirs.data_dir)

    def test_never_raises(self, manager):
        """user_dirs never raises."""
        dirs = manager.user_dirs("")
        assert isinstance(dirs, ProjectPaths)


# ---------------------------------------------------------------------------
# PathManager.resolve_tool / resolve_tools
# ---------------------------------------------------------------------------


class TestResolveTool:
    def test_resolve_known_tool(self, manager):
        """Resolves a tool known to be on PATH (python3 or python)."""
        tp = manager.resolve_tool("python3")
        if not tp.found:
            tp = manager.resolve_tool("python")
        assert tp.found is True
        assert tp.path is not None

    def test_resolve_unknown_tool(self, manager):
        """Returns ToolPath with path=None for unknown tool."""
        tp = manager.resolve_tool("__nonexistent_tool_xyz__")
        assert tp.found is False
        assert tp.path is None
        assert tp.name == "__nonexistent_tool_xyz__"

    def test_resolve_tools_multiple(self, manager):
        """resolve_tools returns a tuple of ToolPath in order."""
        results = manager.resolve_tools(["python3", "__noexist__"])
        assert isinstance(results, tuple)
        assert len(results) == 2
        assert results[0].name == "python3"
        assert results[1].name == "__noexist__"
        assert results[1].found is False

    def test_resolve_tools_empty(self, manager):
        """resolve_tools with empty list returns empty tuple."""
        results = manager.resolve_tools([])
        assert results == ()

    def test_tool_path_frozen(self, manager):
        """Returned ToolPath is frozen."""
        tp = manager.resolve_tool("python3")
        with pytest.raises(AttributeError):
            tp.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PathManager.resolve_library
# ---------------------------------------------------------------------------


class TestResolveLibrary:
    def test_resolve_nonexistent_library(self, manager):
        """Returns LibraryPath with None dirs for unknown library."""
        lp = manager.resolve_library("__nonexistent_lib_xyz__")
        assert lp.found is False
        assert lp.name == "__nonexistent_lib_xyz__"

    def test_resolve_with_custom_search_path(self, tmp_path, manager):
        """Finds library in custom search path."""
        lib_dir = tmp_path / "mylib"
        lib_dir.mkdir()

        lp = manager.resolve_library("mylib", search_paths=[tmp_path])
        assert lp.found is True
        assert lp.lib_dir == lib_dir

    def test_resolve_with_lib_prefix(self, tmp_path, manager):
        """Finds library by libNAME file pattern."""
        (tmp_path / "libfoo.so").write_text("", encoding="utf-8")

        lp = manager.resolve_library("foo", search_paths=[tmp_path])
        assert lp.found is True
        assert lp.lib_dir == tmp_path

    def test_resolve_include_dir(self, tmp_path, manager):
        """Finds include directory alongside lib directory."""
        lib = tmp_path / "lib"
        lib.mkdir()
        (lib / "libbar.so").write_text("", encoding="utf-8")

        inc = tmp_path / "include" / "bar"
        inc.mkdir(parents=True)

        lp = manager.resolve_library("bar", search_paths=[lib])
        assert lp.found is True
        assert lp.include_dir == inc

    def test_frozen(self, manager):
        """Returned LibraryPath is frozen."""
        lp = manager.resolve_library("anything")
        with pytest.raises(AttributeError):
            lp.name = "other"  # type: ignore[misc]

    def test_never_raises(self, manager):
        """resolve_library never raises."""
        lp = manager.resolve_library("")
        assert isinstance(lp, LibraryPath)


# ---------------------------------------------------------------------------
# Import from sniff top-level
# ---------------------------------------------------------------------------


class TestImports:
    def test_import_from_sniff(self):
        """All path types are importable from the top-level package."""
        from sniff import (
            LibraryPath,
            PathCategory,
            PathManager,
            ProjectPaths,
            ResolvedPath,
            ToolPath,
        )

        assert PathManager is not None
        assert PathCategory is not None
        assert ResolvedPath is not None
        assert ToolPath is not None
        assert LibraryPath is not None
        assert ProjectPaths is not None

    def test_in_all(self):
        """New types are listed in sniff.__all__."""
        import sniff

        for name in ("PathManager", "PathCategory", "ResolvedPath",
                     "ToolPath", "LibraryPath", "ProjectPaths"):
            assert name in sniff.__all__
