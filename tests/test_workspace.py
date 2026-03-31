"""Tests for workspace/monorepo detection."""

import json
from pathlib import Path

import pytest

from dekk.detection.workspace import (
    SubProject,
    WorkspaceDetector,
    WorkspaceInfo,
    WorkspaceKind,
)


@pytest.fixture
def detector():
    return WorkspaceDetector()


# --- Cargo workspace ---


class TestCargoWorkspace:
    def test_detect_cargo_workspace(self, tmp_path, detector):
        """Detect a Cargo workspace with members."""
        # Create workspace Cargo.toml
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n',
            encoding="utf-8",
        )

        # Create member crates
        for name in ("core", "cli"):
            crate_dir = tmp_path / "crates" / name
            crate_dir.mkdir(parents=True)
            (crate_dir / "Cargo.toml").write_text(
                f'[package]\nname = "{name}"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )

        results = detector.detect(tmp_path)
        assert len(results) == 1

        ws = results[0]
        assert ws.kind == WorkspaceKind.CARGO
        assert ws.root == tmp_path
        assert ws.project_count == 2
        assert set(ws.project_names) == {"core", "cli"}

    def test_detect_cargo_with_path_deps(self, tmp_path, detector):
        """Detect inter-crate dependencies via path."""
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n',
            encoding="utf-8",
        )

        core_dir = tmp_path / "crates" / "core"
        core_dir.mkdir(parents=True)
        (core_dir / "Cargo.toml").write_text(
            '[package]\nname = "core"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        cli_dir = tmp_path / "crates" / "cli"
        cli_dir.mkdir(parents=True)
        (cli_dir / "Cargo.toml").write_text(
            '[package]\nname = "cli"\nversion = "0.1.0"\n\n'
            '[dependencies]\ncore = { path = "../core" }\n',
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        ws = results[0]

        cli_project = next(p for p in ws.projects if p.name == "cli")
        assert "core" in cli_project.dependencies

    def test_cargo_build_order(self, tmp_path, detector):
        """Build order respects inter-crate deps."""
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n',
            encoding="utf-8",
        )

        for name, deps in [
            ("core", ""),
            ("mid", 'core = { path = "../core" }'),
            ("top", 'mid = { path = "../mid" }'),
        ]:
            d = tmp_path / "crates" / name
            d.mkdir(parents=True)
            deps_section = f"\n[dependencies]\n{deps}\n" if deps else ""
            (d / "Cargo.toml").write_text(
                f'[package]\nname = "{name}"\nversion = "0.1.0"\n{deps_section}',
                encoding="utf-8",
            )

        ws = detector.detect(tmp_path)[0]
        order = ws.build_order()
        assert order.index("core") < order.index("mid")
        assert order.index("mid") < order.index("top")

    def test_no_workspace_section(self, tmp_path, detector):
        """Non-workspace Cargo.toml should not detect."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "single"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        assert detector.detect(tmp_path) == []

    def test_cargo_shared_deps(self, tmp_path, detector):
        """Detect workspace-level shared dependencies."""
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n\n[workspace.dependencies]\nserde = "1.0"\n',
            encoding="utf-8",
        )

        d = tmp_path / "crates" / "a"
        d.mkdir(parents=True)
        (d / "Cargo.toml").write_text(
            '[package]\nname = "a"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        ws = detector.detect(tmp_path)[0]
        assert ws.shared_deps_file is not None


# --- pnpm workspace ---


class TestPnpmWorkspace:
    def test_detect_pnpm_workspace(self, tmp_path, detector):
        """Detect a pnpm workspace."""
        (tmp_path / "pnpm-workspace.yaml").write_text(
            "packages:\n  - 'packages/*'\n",
            encoding="utf-8",
        )

        pkg_dir = tmp_path / "packages" / "ui"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            json.dumps({"name": "@myapp/ui", "version": "1.0.0"}),
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        assert len(results) >= 1

        pnpm = next(r for r in results if r.kind == WorkspaceKind.PNPM)
        assert pnpm.project_count == 1
        assert pnpm.project_names == ("@myapp/ui",)

    def test_pnpm_multiple_globs(self, tmp_path, detector):
        """pnpm workspace with multiple glob patterns."""
        (tmp_path / "pnpm-workspace.yaml").write_text(
            "packages:\n  - 'packages/*'\n  - 'apps/*'\n",
            encoding="utf-8",
        )

        for group, name in [("packages", "lib"), ("apps", "web")]:
            d = tmp_path / group / name
            d.mkdir(parents=True)
            (d / "package.json").write_text(
                json.dumps({"name": name}),
                encoding="utf-8",
            )

        pnpm = next(r for r in detector.detect(tmp_path) if r.kind == WorkspaceKind.PNPM)
        assert pnpm.project_count == 2


# --- npm workspace ---


class TestNpmWorkspace:
    def test_detect_npm_workspace(self, tmp_path, detector):
        """Detect npm workspaces in package.json."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "root", "workspaces": ["packages/*"]}),
            encoding="utf-8",
        )

        pkg_dir = tmp_path / "packages" / "utils"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            json.dumps({"name": "@myapp/utils", "version": "2.0.0"}),
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        npm = next(r for r in results if r.kind == WorkspaceKind.NPM)
        assert npm.project_count == 1

    def test_npm_not_detected_when_pnpm_present(self, tmp_path, detector):
        """npm workspace is skipped if pnpm-workspace.yaml exists."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "root", "workspaces": ["packages/*"]}),
            encoding="utf-8",
        )
        (tmp_path / "pnpm-workspace.yaml").write_text(
            "packages:\n  - 'packages/*'\n",
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        kinds = {r.kind for r in results}
        assert WorkspaceKind.NPM not in kinds


# --- yarn workspace ---


class TestYarnWorkspace:
    def test_detect_yarn_workspace(self, tmp_path, detector):
        """Detect yarn workspaces via .yarnrc.yml."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "root", "workspaces": ["packages/*"]}),
            encoding="utf-8",
        )
        (tmp_path / ".yarnrc.yml").write_text("nodeLinker: node-modules\n", encoding="utf-8")

        pkg_dir = tmp_path / "packages" / "core"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            json.dumps({"name": "@myapp/core"}),
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        yarn = next(r for r in results if r.kind == WorkspaceKind.YARN)
        assert yarn.project_count == 1

    def test_detect_yarn_via_lock(self, tmp_path, detector):
        """Detect yarn workspaces via yarn.lock."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "root", "workspaces": ["packages/*"]}),
            encoding="utf-8",
        )
        (tmp_path / "yarn.lock").write_text("", encoding="utf-8")

        pkg_dir = tmp_path / "packages" / "core"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            json.dumps({"name": "@myapp/core"}),
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        yarn = next(r for r in results if r.kind == WorkspaceKind.YARN)
        assert yarn.project_count == 1


# --- Node workspace dependencies ---


class TestNodeWorkspaceDeps:
    def test_workspace_protocol_deps(self, tmp_path, detector):
        """Detect workspace: protocol dependencies."""
        (tmp_path / "pnpm-workspace.yaml").write_text(
            "packages:\n  - 'packages/*'\n",
            encoding="utf-8",
        )

        for name in ("shared", "app"):
            d = tmp_path / "packages" / name
            d.mkdir(parents=True)

        (tmp_path / "packages" / "shared" / "package.json").write_text(
            json.dumps({"name": "shared", "version": "1.0.0"}),
            encoding="utf-8",
        )
        (tmp_path / "packages" / "app" / "package.json").write_text(
            json.dumps(
                {
                    "name": "app",
                    "version": "1.0.0",
                    "dependencies": {"shared": "workspace:*"},
                }
            ),
            encoding="utf-8",
        )

        pnpm = next(r for r in detector.detect(tmp_path) if r.kind == WorkspaceKind.PNPM)
        app = next(p for p in pnpm.projects if p.name == "app")
        assert "shared" in app.dependencies


# --- uv workspace ---


class TestUvWorkspace:
    def test_detect_uv_workspace(self, tmp_path, detector):
        """Detect uv workspace in pyproject.toml."""
        (tmp_path / "pyproject.toml").write_bytes(
            b'[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )

        pkg_dir = tmp_path / "packages" / "mylib"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_bytes(b'[project]\nname = "mylib"\nversion = "0.1.0"\n')

        results = detector.detect(tmp_path)
        uv = next(r for r in results if r.kind == WorkspaceKind.UV)
        assert uv.project_count == 1
        assert uv.project_names == ("mylib",)


# --- Go workspace ---


class TestGoWorkspace:
    def test_detect_go_work(self, tmp_path, detector):
        """Detect go.work workspace."""
        (tmp_path / "go.work").write_text(
            "go 1.21\n\nuse (\n\t./api\n\t./cmd\n)\n",
            encoding="utf-8",
        )

        for mod in ("api", "cmd"):
            d = tmp_path / mod
            d.mkdir()
            (d / "go.mod").write_text(
                f"module example.com/{mod}\n\ngo 1.21\n",
                encoding="utf-8",
            )

        results = detector.detect(tmp_path)
        go = next(r for r in results if r.kind == WorkspaceKind.GO_WORK)
        assert go.project_count == 2
        assert set(go.project_names) == {"example.com/api", "example.com/cmd"}

    def test_go_work_single_use(self, tmp_path, detector):
        """Detect go.work with single-line use directive."""
        (tmp_path / "go.work").write_text(
            "go 1.21\n\nuse ./mymod\n",
            encoding="utf-8",
        )
        d = tmp_path / "mymod"
        d.mkdir()
        (d / "go.mod").write_text("module example.com/mymod\n\ngo 1.21\n", encoding="utf-8")

        results = detector.detect(tmp_path)
        go = next(r for r in results if r.kind == WorkspaceKind.GO_WORK)
        assert go.project_count == 1


# --- Turborepo ---


class TestTurborepo:
    def test_detect_turborepo(self, tmp_path, detector):
        """Detect Turborepo with turbo.json."""
        (tmp_path / "turbo.json").write_text(
            json.dumps({"pipeline": {"build": {"dependsOn": ["^build"]}}}),
            encoding="utf-8",
        )
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "root", "workspaces": ["packages/*"]}),
            encoding="utf-8",
        )

        pkg_dir = tmp_path / "packages" / "web"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            json.dumps({"name": "web"}),
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        turbo = next(r for r in results if r.kind == WorkspaceKind.TURBOREPO)
        assert turbo.project_count == 1


# --- Nx ---


class TestNx:
    def test_detect_nx(self, tmp_path, detector):
        """Detect Nx workspace."""
        (tmp_path / "nx.json").write_text(
            json.dumps({"workspaceLayout": {"appsDir": "apps", "libsDir": "libs"}}),
            encoding="utf-8",
        )

        app_dir = tmp_path / "apps" / "frontend"
        app_dir.mkdir(parents=True)
        (app_dir / "project.json").write_text(
            json.dumps({"name": "frontend"}),
            encoding="utf-8",
        )

        lib_dir = tmp_path / "libs" / "shared"
        lib_dir.mkdir(parents=True)
        (lib_dir / "package.json").write_text(
            json.dumps({"name": "@myorg/shared"}),
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        nx = next(r for r in results if r.kind == WorkspaceKind.NX)
        assert nx.project_count == 2


# --- Lerna ---


class TestLerna:
    def test_detect_lerna(self, tmp_path, detector):
        """Detect Lerna workspace."""
        (tmp_path / "lerna.json").write_text(
            json.dumps({"version": "independent", "packages": ["packages/*"]}),
            encoding="utf-8",
        )

        pkg_dir = tmp_path / "packages" / "core"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            json.dumps({"name": "@lerna/core"}),
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        lerna = next(r for r in results if r.kind == WorkspaceKind.LERNA)
        assert lerna.project_count == 1


# --- Bazel ---


class TestBazel:
    def test_detect_bazel(self, tmp_path, detector):
        """Detect Bazel workspace."""
        (tmp_path / "WORKSPACE.bazel").write_text("", encoding="utf-8")

        pkg_dir = tmp_path / "mylib"
        pkg_dir.mkdir()
        (pkg_dir / "BUILD.bazel").write_text("", encoding="utf-8")

        results = detector.detect(tmp_path)
        bazel = next(r for r in results if r.kind == WorkspaceKind.BAZEL)
        assert bazel.project_count == 1

    def test_detect_bzlmod(self, tmp_path, detector):
        """Detect Bazel with MODULE.bazel (bzlmod)."""
        (tmp_path / "MODULE.bazel").write_text("", encoding="utf-8")

        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "BUILD").write_text("", encoding="utf-8")

        results = detector.detect(tmp_path)
        bazel = next(r for r in results if r.kind == WorkspaceKind.BAZEL)
        assert bazel.project_count == 1


# --- Pants ---


class TestPants:
    def test_detect_pants(self, tmp_path, detector):
        """Detect Pants build system."""
        (tmp_path / "pants.toml").write_bytes(b'[GLOBAL]\npants_version = "2.18.0"\n')

        pkg_dir = tmp_path / "src" / "python"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "BUILD").write_text("", encoding="utf-8")

        # Pants looks one level deep for BUILD files from root
        # Our detector finds BUILD in immediate children
        results = detector.detect(tmp_path)
        pants = next(r for r in results if r.kind == WorkspaceKind.PANTS)
        assert pants.kind == WorkspaceKind.PANTS


# --- General behavior ---


class TestWorkspaceDetectorGeneral:
    def test_empty_directory(self, tmp_path, detector):
        """No workspace in empty directory."""
        assert detector.detect(tmp_path) == []

    def test_nonexistent_directory(self, tmp_path, detector):
        """Non-existent directory returns empty."""
        assert detector.detect(tmp_path / "does_not_exist") == []

    def test_detect_first(self, tmp_path, detector):
        """detect_first returns the first match."""
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n',
            encoding="utf-8",
        )
        d = tmp_path / "crates" / "a"
        d.mkdir(parents=True)
        (d / "Cargo.toml").write_text(
            '[package]\nname = "a"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        ws = detector.detect_first(tmp_path)
        assert ws is not None
        assert ws.kind == WorkspaceKind.CARGO

    def test_detect_first_empty(self, tmp_path, detector):
        """detect_first returns None for empty directory."""
        assert detector.detect_first(tmp_path) is None

    def test_multiple_workspaces(self, tmp_path, detector):
        """Detect multiple workspace types in one repo."""
        # Cargo workspace
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n',
            encoding="utf-8",
        )
        d = tmp_path / "crates" / "core"
        d.mkdir(parents=True)
        (d / "Cargo.toml").write_text(
            '[package]\nname = "core"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        # npm workspace
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "root", "workspaces": ["js/*"]}),
            encoding="utf-8",
        )
        js_dir = tmp_path / "js" / "ui"
        js_dir.mkdir(parents=True)
        (js_dir / "package.json").write_text(
            json.dumps({"name": "ui"}),
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        kinds = {r.kind for r in results}
        assert WorkspaceKind.CARGO in kinds
        assert WorkspaceKind.NPM in kinds

    def test_find_workspace_root(self, tmp_path, detector):
        """find_workspace_root walks up to find workspace."""
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n',
            encoding="utf-8",
        )
        d = tmp_path / "crates" / "mylib"
        d.mkdir(parents=True)
        (d / "Cargo.toml").write_text(
            '[package]\nname = "mylib"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        found = detector.find_workspace_root(d)
        assert found == tmp_path


# --- WorkspaceInfo methods ---


class TestWorkspaceInfoMethods:
    def test_dependency_graph(self):
        """Test dependency_graph filters to internal deps only."""
        ws = WorkspaceInfo(
            kind=WorkspaceKind.CARGO,
            root=Path("/tmp/test"),
            config_file=Path("/tmp/test/Cargo.toml"),
            projects=(
                SubProject(name="core", path=Path("/tmp/test/core"), kind="rust_crate"),
                SubProject(
                    name="cli",
                    path=Path("/tmp/test/cli"),
                    kind="rust_crate",
                    dependencies=("core", "serde"),  # serde is external
                ),
            ),
        )

        graph = ws.dependency_graph()
        assert graph["core"] == ()
        assert graph["cli"] == ("core",)  # serde filtered out

    def test_build_order_cycle(self):
        """Build order returns empty on cycle."""
        ws = WorkspaceInfo(
            kind=WorkspaceKind.CARGO,
            root=Path("/tmp/test"),
            config_file=Path("/tmp/test/Cargo.toml"),
            projects=(
                SubProject(name="a", path=Path("/tmp/a"), kind="x", dependencies=("b",)),
                SubProject(name="b", path=Path("/tmp/b"), kind="x", dependencies=("a",)),
            ),
        )
        assert ws.build_order() == []

    def test_build_order_independent(self):
        """Build order with no deps returns all projects."""
        ws = WorkspaceInfo(
            kind=WorkspaceKind.CARGO,
            root=Path("/tmp/test"),
            config_file=Path("/tmp/test/Cargo.toml"),
            projects=(
                SubProject(name="a", path=Path("/tmp/a"), kind="x"),
                SubProject(name="b", path=Path("/tmp/b"), kind="x"),
            ),
        )
        order = ws.build_order()
        assert set(order) == {"a", "b"}
