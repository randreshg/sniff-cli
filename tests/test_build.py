"""Tests for build system detection."""

import json
from pathlib import Path

import pytest

from dekk.build import (
    BuildSystem,
    BuildSystemDetector,
    BuildSystemInfo,
    BuildTarget,
)


@pytest.fixture
def detector():
    return BuildSystemDetector()


# --- Cargo ---


class TestCargo:
    def test_detect_cargo_workspace(self, tmp_path, detector):
        """Detect a Cargo workspace."""
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n\n[workspace.dependencies]\nserde = "1.0"\n',
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        cargo = next(r for r in results if r.system == BuildSystem.CARGO)
        assert cargo.is_workspace
        assert cargo.config_file == tmp_path / "Cargo.toml"

    def test_detect_cargo_binary(self, tmp_path, detector):
        """Detect a Cargo binary project via src/main.rs."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "myapp"\nversion = "0.1.0"\nedition = "2021"\n',
            encoding="utf-8",
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}", encoding="utf-8")

        cargo = detector.detect_first(tmp_path)
        assert cargo is not None
        assert cargo.system == BuildSystem.CARGO
        assert cargo.version == "2021"
        assert not cargo.is_workspace

        bins = cargo.targets_of_kind("binary")
        assert len(bins) == 1
        assert bins[0].name == "myapp"

    def test_detect_cargo_library(self, tmp_path, detector):
        """Detect a Cargo library project via src/lib.rs."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "mylib"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "lib.rs").write_text("pub fn hello() {}", encoding="utf-8")

        cargo = detector.detect_first(tmp_path)
        assert cargo is not None
        libs = cargo.targets_of_kind("library")
        assert len(libs) == 1
        assert libs[0].name == "mylib"

    def test_detect_cargo_explicit_bins(self, tmp_path, detector):
        """Detect explicit [[bin]] targets in Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "multi"\nversion = "0.1.0"\n\n'
            '[[bin]]\nname = "server"\npath = "src/server.rs"\n\n'
            '[[bin]]\nname = "client"\npath = "src/client.rs"\n',
            encoding="utf-8",
        )

        cargo = detector.detect_first(tmp_path)
        assert cargo is not None
        bins = cargo.targets_of_kind("binary")
        assert len(bins) == 2
        assert {b.name for b in bins} == {"server", "client"}


# --- CMake ---


class TestCMake:
    def test_detect_cmake(self, tmp_path, detector):
        """Detect CMake build system."""
        (tmp_path / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\n"
            "project(myproject)\n"
            "add_executable(myapp src/main.cpp)\n"
            "add_library(mylib src/lib.cpp)\n",
            encoding="utf-8",
        )

        cmake = detector.detect_first(tmp_path)
        assert cmake is not None
        assert cmake.system == BuildSystem.CMAKE
        assert cmake.version == "3.20"
        assert cmake.target_count == 2
        assert "myapp" in cmake.target_names
        assert "mylib" in cmake.target_names

    def test_cmake_targets_kinds(self, tmp_path, detector):
        """CMake executables and libraries have correct kinds."""
        (tmp_path / "CMakeLists.txt").write_text(
            "add_executable(app main.c)\nadd_library(util util.c)\n",
            encoding="utf-8",
        )

        cmake = detector.detect_first(tmp_path)
        assert cmake is not None
        assert cmake.targets_of_kind("binary")[0].name == "app"
        assert cmake.targets_of_kind("library")[0].name == "util"


# --- Make ---


class TestMake:
    def test_detect_makefile(self, tmp_path, detector):
        """Detect Makefile."""
        (tmp_path / "Makefile").write_text(
            "all: build\n\nbuild:\n\tgcc main.c\n\ntest:\n\t./run_tests\n\nclean:\n\trm -f a.out\n",
            encoding="utf-8",
        )

        make = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.MAKE)
        assert make.config_file == tmp_path / "Makefile"
        assert "all" in make.target_names
        assert "build" in make.target_names
        assert "test" in make.target_names
        assert "clean" in make.target_names

    def test_detect_gnumakefile(self, tmp_path, detector):
        """GNUmakefile is preferred."""
        (tmp_path / "GNUmakefile").write_text("all:\n\techo hi\n", encoding="utf-8")
        (tmp_path / "Makefile").write_text("all:\n\techo hi\n", encoding="utf-8")

        make = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.MAKE)
        assert make.config_file == tmp_path / "GNUmakefile"


# --- Meson ---


class TestMeson:
    def test_detect_meson(self, tmp_path, detector):
        """Detect Meson build system."""
        (tmp_path / "meson.build").write_text(
            "project('myproject', 'c', version: '1.2.3')\n"
            "executable('myapp', 'main.c')\n"
            "library('mylib', 'lib.c')\n"
            "shared_library('myshared', 'shared.c')\n",
            encoding="utf-8",
        )

        meson = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.MESON)
        assert meson.version == "1.2.3"
        assert meson.target_count == 3


# --- Node.js build systems ---


class TestNodeBuildSystems:
    def test_detect_npm(self, tmp_path, detector):
        """Detect npm as build system."""
        (tmp_path / "package.json").write_text(
            json.dumps(
                {
                    "name": "myapp",
                    "version": "1.0.0",
                    "scripts": {"build": "tsc", "test": "jest", "start": "node ."},
                }
            ),
            encoding="utf-8",
        )

        npm = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.NPM)
        assert npm.version == "1.0.0"
        assert {"build", "test", "start"} == set(npm.target_names)

    def test_npm_not_detected_with_pnpm(self, tmp_path, detector):
        """npm is skipped when pnpm is present."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "myapp", "scripts": {"build": "tsc"}}),
            encoding="utf-8",
        )
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'pkg/*'\n", encoding="utf-8")

        systems = {r.system for r in detector.detect(tmp_path)}
        assert BuildSystem.NPM not in systems
        assert BuildSystem.PNPM in systems

    def test_detect_pnpm(self, tmp_path, detector):
        """Detect pnpm as build system."""
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'pkg/*'\n", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"build": "turbo build"}}),
            encoding="utf-8",
        )

        pnpm = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.PNPM)
        assert pnpm.is_workspace
        assert "build" in pnpm.target_names

    def test_detect_yarn(self, tmp_path, detector):
        """Detect yarn as build system."""
        (tmp_path / ".yarnrc.yml").write_text("nodeLinker: node-modules\n", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            json.dumps(
                {
                    "name": "myapp",
                    "workspaces": ["packages/*"],
                    "scripts": {"build": "tsc"},
                }
            ),
            encoding="utf-8",
        )

        yarn = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.YARN)
        assert yarn.is_workspace

    def test_detect_bun(self, tmp_path, detector):
        """Detect bun as build system."""
        (tmp_path / "bun.lockb").write_bytes(b"")
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"dev": "bun run src/index.ts"}}),
            encoding="utf-8",
        )

        bun = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.BUN)
        assert "dev" in bun.target_names


# --- Python build systems ---


class TestPythonBuildSystems:
    def test_detect_poetry(self, tmp_path, detector):
        """Detect Poetry as build system."""
        (tmp_path / "pyproject.toml").write_bytes(
            b'[tool.poetry]\nname = "myapp"\nversion = "0.1.0"\n\n'
            b"[project]\nscripts = {}\n\n"
            b'[build-system]\nrequires = ["poetry-core"]\n'
            b'build-backend = "poetry.core.masonry.api"\n'
        )

        poetry = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.POETRY)
        assert poetry.version == "0.1.0"

    def test_detect_hatch(self, tmp_path, detector):
        """Detect Hatch/Hatchling as build system."""
        (tmp_path / "pyproject.toml").write_bytes(
            b'[build-system]\nrequires = ["hatchling"]\n'
            b'build-backend = "hatchling.build"\n\n'
            b'[project]\nname = "myapp"\nversion = "0.2.0"\n'
            b'[project.scripts]\nmycli = "myapp:main"\n\n'
            b"[tool.hatch]\n"
        )

        hatch = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.HATCH)
        assert hatch.version == "0.2.0"
        assert "mycli" in hatch.target_names

    def test_detect_flit(self, tmp_path, detector):
        """Detect Flit as build system."""
        (tmp_path / "pyproject.toml").write_bytes(
            b'[build-system]\nrequires = ["flit_core"]\n'
            b'build-backend = "flit_core.buildapi"\n\n'
            b'[project]\nname = "mylib"\nversion = "1.0.0"\n'
        )

        flit = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.FLIT)
        assert flit.version == "1.0.0"

    def test_detect_setuptools_setup_py(self, tmp_path, detector):
        """Detect setuptools via setup.py."""
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='myapp')\n",
            encoding="utf-8",
        )

        st = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.SETUPTOOLS)
        assert st.config_file == tmp_path / "setup.py"

    def test_detect_setuptools_setup_cfg(self, tmp_path, detector):
        """Detect setuptools via setup.cfg (no setup.py)."""
        (tmp_path / "setup.cfg").write_text(
            "[metadata]\nname = myapp\n",
            encoding="utf-8",
        )

        st = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.SETUPTOOLS)
        assert st.config_file == tmp_path / "setup.cfg"

    def test_detect_maturin(self, tmp_path, detector):
        """Detect Maturin as build system."""
        (tmp_path / "pyproject.toml").write_bytes(
            b'[build-system]\nrequires = ["maturin"]\n'
            b'build-backend = "maturin"\n\n'
            b'[project]\nname = "mypyo3"\nversion = "0.1.0"\n\n'
            b'[tool.maturin]\nfeatures = ["pyo3/extension-module"]\n'
        )

        maturin = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.MATURIN)
        assert maturin.version == "0.1.0"

    def test_detect_uv(self, tmp_path, detector):
        """Detect uv as build system."""
        (tmp_path / "pyproject.toml").write_bytes(
            b'[project]\nname = "myapp"\nversion = "0.3.0"\n\n'
            b'[tool.uv]\ndev-dependencies = ["pytest"]\n'
        )

        uv = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.UV)
        assert uv.version == "0.3.0"

    def test_detect_uv_workspace(self, tmp_path, detector):
        """Detect uv workspace."""
        (tmp_path / "pyproject.toml").write_bytes(
            b'[project]\nname = "root"\n\n[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )

        uv = next(r for r in detector.detect(tmp_path) if r.system == BuildSystem.UV)
        assert uv.is_workspace


# --- Go ---


class TestGo:
    def test_detect_go(self, tmp_path, detector):
        """Detect Go module."""
        (tmp_path / "go.mod").write_text(
            "module example.com/myapp\n\ngo 1.22\n",
            encoding="utf-8",
        )
        (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")

        go = detector.detect_first(tmp_path)
        assert go is not None
        assert go.system == BuildSystem.GO
        assert go.version == "1.22"
        assert go.target_count >= 1

    def test_detect_go_cmd_layout(self, tmp_path, detector):
        """Detect Go project with cmd/ layout."""
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n", encoding="utf-8")
        cmd_dir = tmp_path / "cmd"
        for name in ("server", "worker"):
            d = cmd_dir / name
            d.mkdir(parents=True)
            (d / "main.go").write_text("package main\n", encoding="utf-8")

        go = detector.detect_first(tmp_path)
        assert go is not None
        bins = go.targets_of_kind("binary")
        assert {b.name for b in bins} == {"server", "worker"}

    def test_detect_go_workspace(self, tmp_path, detector):
        """Detect Go workspace via go.work."""
        (tmp_path / "go.mod").write_text("module root\n\ngo 1.21\n", encoding="utf-8")
        (tmp_path / "go.work").write_text("go 1.21\n\nuse ./api\n", encoding="utf-8")

        go = detector.detect_first(tmp_path)
        assert go is not None
        assert go.is_workspace


# --- JVM ---


class TestJVM:
    def test_detect_maven(self, tmp_path, detector):
        """Detect Maven build system."""
        (tmp_path / "pom.xml").write_text(
            "<project></project>",
            encoding="utf-8",
        )

        maven = detector.detect_first(tmp_path)
        assert maven is not None
        assert maven.system == BuildSystem.MAVEN

    def test_detect_gradle(self, tmp_path, detector):
        """Detect Gradle build system."""
        (tmp_path / "build.gradle.kts").write_text("plugins {}\n", encoding="utf-8")

        gradle = detector.detect_first(tmp_path)
        assert gradle is not None
        assert gradle.system == BuildSystem.GRADLE

    def test_detect_gradle_workspace(self, tmp_path, detector):
        """Detect Gradle multi-project build."""
        (tmp_path / "build.gradle").write_text("", encoding="utf-8")
        (tmp_path / "settings.gradle").write_text("include ':app'\n", encoding="utf-8")

        gradle = detector.detect_first(tmp_path)
        assert gradle is not None
        assert gradle.is_workspace


# --- Other build systems ---


class TestOtherBuildSystems:
    def test_detect_bazel(self, tmp_path, detector):
        """Detect Bazel build system."""
        (tmp_path / "WORKSPACE.bazel").write_text("", encoding="utf-8")

        bazel = detector.detect_first(tmp_path)
        assert bazel is not None
        assert bazel.system == BuildSystem.BAZEL
        assert bazel.is_workspace

    def test_detect_buck2(self, tmp_path, detector):
        """Detect Buck2 build system."""
        (tmp_path / ".buckconfig").write_text("[project]\n", encoding="utf-8")

        buck = detector.detect_first(tmp_path)
        assert buck is not None
        assert buck.system == BuildSystem.BUCK2

    def test_detect_mix(self, tmp_path, detector):
        """Detect Elixir Mix."""
        (tmp_path / "mix.exs").write_text("defmodule MyApp do end\n", encoding="utf-8")

        mix = detector.detect_first(tmp_path)
        assert mix is not None
        assert mix.system == BuildSystem.MIX

    def test_detect_stack(self, tmp_path, detector):
        """Detect Haskell Stack."""
        (tmp_path / "stack.yaml").write_text("resolver: lts-21.0\n", encoding="utf-8")

        stack = detector.detect_first(tmp_path)
        assert stack is not None
        assert stack.system == BuildSystem.STACK

    def test_detect_cabal(self, tmp_path, detector):
        """Detect Haskell Cabal."""
        (tmp_path / "myapp.cabal").write_text("name: myapp\n", encoding="utf-8")

        cabal = detector.detect_first(tmp_path)
        assert cabal is not None
        assert cabal.system == BuildSystem.CABAL

    def test_detect_zig(self, tmp_path, detector):
        """Detect Zig build system."""
        (tmp_path / "build.zig").write_text('const std = @import("std");\n', encoding="utf-8")

        zig = detector.detect_first(tmp_path)
        assert zig is not None
        assert zig.system == BuildSystem.ZIG

    def test_detect_dune(self, tmp_path, detector):
        """Detect OCaml Dune build system."""
        (tmp_path / "dune-project").write_text("(lang dune 3.0)\n", encoding="utf-8")

        dune = detector.detect_first(tmp_path)
        assert dune is not None
        assert dune.system == BuildSystem.DUNE

    def test_detect_ninja(self, tmp_path, detector):
        """Detect Ninja build system."""
        (tmp_path / "build.ninja").write_text(
            "rule cc\n  command = gcc $in -o $out\n", encoding="utf-8"
        )

        ninja = detector.detect_first(tmp_path)
        assert ninja is not None
        assert ninja.system == BuildSystem.NINJA


# --- General behavior ---


class TestBuildSystemDetectorGeneral:
    def test_empty_directory(self, tmp_path, detector):
        """No build system in empty directory."""
        assert detector.detect(tmp_path) == []

    def test_nonexistent_directory(self, tmp_path, detector):
        """Non-existent directory returns empty."""
        assert detector.detect(tmp_path / "nope") == []

    def test_detect_first_none(self, tmp_path, detector):
        """detect_first returns None for empty directory."""
        assert detector.detect_first(tmp_path) is None

    def test_multiple_build_systems(self, tmp_path, detector):
        """Detect multiple build systems in one project."""
        # Cargo + CMake (common for Rust + C FFI)
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "ffi"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        (tmp_path / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.15)\nadd_library(native native.c)\n",
            encoding="utf-8",
        )

        results = detector.detect(tmp_path)
        systems = {r.system for r in results}
        assert BuildSystem.CARGO in systems
        assert BuildSystem.CMAKE in systems


# --- BuildSystemInfo methods ---


class TestBuildSystemInfoMethods:
    def test_target_count(self):
        info = BuildSystemInfo(
            system=BuildSystem.CMAKE,
            root=Path("/tmp/test"),
            config_file=Path("/tmp/test/CMakeLists.txt"),
            targets=(
                BuildTarget(name="app", kind="binary"),
                BuildTarget(name="lib", kind="library"),
            ),
        )
        assert info.target_count == 2

    def test_target_names(self):
        info = BuildSystemInfo(
            system=BuildSystem.CARGO,
            root=Path("/tmp/test"),
            config_file=Path("/tmp/test/Cargo.toml"),
            targets=(
                BuildTarget(name="server", kind="binary"),
                BuildTarget(name="client", kind="binary"),
                BuildTarget(name="core", kind="library"),
            ),
        )
        assert info.target_names == ("server", "client", "core")

    def test_targets_of_kind(self):
        info = BuildSystemInfo(
            system=BuildSystem.CARGO,
            root=Path("/tmp/test"),
            config_file=Path("/tmp/test/Cargo.toml"),
            targets=(
                BuildTarget(name="server", kind="binary"),
                BuildTarget(name="client", kind="binary"),
                BuildTarget(name="core", kind="library"),
            ),
        )
        bins = info.targets_of_kind("binary")
        assert len(bins) == 2
        assert info.targets_of_kind("library")[0].name == "core"
        assert info.targets_of_kind("test") == ()

    def test_frozen_dataclass(self):
        target = BuildTarget(name="app", kind="binary")
        with pytest.raises(AttributeError):
            target.name = "other"  # type: ignore[misc]

        info = BuildSystemInfo(
            system=BuildSystem.MAKE,
            root=Path("/tmp"),
            config_file=Path("/tmp/Makefile"),
        )
        with pytest.raises(AttributeError):
            info.system = BuildSystem.CMAKE  # type: ignore[misc]
