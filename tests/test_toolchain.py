"""Tests for toolchain profiles and EnvVarBuilder."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from sniff_cli.shell import ActivationConfig, ActivationScriptBuilder, EnvVar, ShellKind
from sniff_cli.toolchain import (
    CMakeToolchain,
    CondaToolchain,
    EnvVarBuilder,
    ToolchainProfile,
)


# ---------------------------------------------------------------------------
# EnvVarBuilder
# ---------------------------------------------------------------------------


class TestEnvVarBuilder:
    def test_empty_builder(self):
        builder = EnvVarBuilder()
        config = builder.build()
        assert config.env_vars == ()
        assert config.path_prepends == ()
        assert config.app_name == ""
        assert config.banner is None

    def test_app_name(self):
        builder = EnvVarBuilder(app_name="apxm")
        config = builder.build()
        assert config.app_name == "apxm"

    def test_set_var(self):
        builder = EnvVarBuilder()
        builder.set_var("FOO", "/some/path")
        config = builder.build()
        assert len(config.env_vars) == 1
        assert config.env_vars[0] == EnvVar(name="FOO", value="/some/path")
        assert config.env_vars[0].prepend_path is False

    def test_prepend_var(self):
        builder = EnvVarBuilder()
        builder.prepend_var("LD_LIBRARY_PATH", "/opt/lib")
        config = builder.build()
        assert len(config.env_vars) == 1
        assert config.env_vars[0] == EnvVar(
            name="LD_LIBRARY_PATH", value="/opt/lib", prepend_path=True
        )

    def test_prepend_path(self):
        builder = EnvVarBuilder()
        builder.prepend_path("/opt/conda/bin")
        builder.prepend_path(Path("/usr/local/bin"))
        config = builder.build()
        assert config.path_prepends == ("/opt/conda/bin", "/usr/local/bin")

    def test_set_banner(self):
        builder = EnvVarBuilder()
        builder.set_banner("Toolchain activated")
        config = builder.build()
        assert config.banner == "Toolchain activated"

    def test_build_produces_frozen_config(self):
        builder = EnvVarBuilder(app_name="test")
        builder.set_var("X", "1")
        config = builder.build()
        assert isinstance(config, ActivationConfig)
        with pytest.raises(AttributeError):
            config.app_name = "changed"  # type: ignore[misc]

    def test_to_env_dict(self):
        builder = EnvVarBuilder()
        builder.set_var("MLIR_DIR", "/opt/mlir")
        builder.set_var("LLVM_DIR", "/opt/llvm")
        builder.prepend_path("/opt/bin")
        d = builder.to_env_dict()
        assert d["MLIR_DIR"] == "/opt/mlir"
        assert d["LLVM_DIR"] == "/opt/llvm"
        assert d["PATH"] == "/opt/bin"

    def test_to_env_dict_multiple_paths(self):
        builder = EnvVarBuilder()
        builder.prepend_path("/a")
        builder.prepend_path("/b")
        d = builder.to_env_dict()
        assert d["PATH"] == os.pathsep.join(("/a", "/b"))

    def test_to_env_dict_uses_os_pathsep(self, monkeypatch: pytest.MonkeyPatch):
        builder = EnvVarBuilder()
        builder.prepend_var("PYTHONPATH", "C:/first")
        builder.prepend_var("PYTHONPATH", "C:/second")
        builder.prepend_path("C:/bin")
        monkeypatch.setattr("sniff_cli.toolchain.os.pathsep", ";")
        d = builder.to_env_dict()
        assert d["PYTHONPATH"] == "C:/first;C:/second"
        assert d["PATH"] == "C:/bin"

    def test_to_env_dict_no_path(self):
        builder = EnvVarBuilder()
        builder.set_var("X", "1")
        d = builder.to_env_dict()
        assert "PATH" not in d

    def test_multiple_profiles(self):
        """Builder accumulates vars from multiple configure calls."""
        builder = EnvVarBuilder(app_name="test")
        builder.set_var("A", "1")
        builder.set_var("B", "2")
        builder.prepend_path("/first")
        builder.set_var("C", "3")
        builder.prepend_path("/second")
        config = builder.build()
        assert len(config.env_vars) == 3
        assert config.path_prepends == ("/first", "/second")


# ---------------------------------------------------------------------------
# CMakeToolchain
# ---------------------------------------------------------------------------


class TestCMakeToolchain:
    def setup_method(self):
        self.prefix = Path("/opt/conda/envs/apxm")
        self.tc = CMakeToolchain(prefix=self.prefix)

    def test_frozen(self):
        with pytest.raises(AttributeError):
            self.tc.prefix = Path("/other")  # type: ignore[misc]

    def test_properties(self):
        assert self.tc.mlir_dir == self.prefix / "lib" / "cmake" / "mlir"
        assert self.tc.llvm_dir == self.prefix / "lib" / "cmake" / "llvm"
        assert self.tc.lib_dir == self.prefix / "lib"
        assert self.tc.bin_dir == self.prefix / "bin"

    @patch("sniff_cli.toolchain.platform.system", return_value="Windows")
    def test_properties_windows(self, _mock):
        prefix = Path("C:/miniforge/envs/apxm")
        tc = CMakeToolchain(prefix=prefix)
        assert tc.mlir_dir == prefix / "Library" / "lib" / "cmake" / "mlir"
        assert tc.llvm_dir == prefix / "Library" / "lib" / "cmake" / "llvm"
        assert tc.lib_dir == prefix / "Library" / "lib"
        assert tc.bin_dirs == (
            prefix,
            prefix / "Library" / "mingw-w64" / "bin",
            prefix / "Library" / "usr" / "bin",
            prefix / "Library" / "bin",
            prefix / "Scripts",
            prefix / "bin",
        )

    @patch("sniff_cli.toolchain.platform.system", return_value="Linux")
    def test_configure_linux(self, _mock):
        builder = EnvVarBuilder(app_name="apxm")
        self.tc.configure(builder)
        config = builder.build()

        var_names = [v.name for v in config.env_vars]
        assert "MLIR_DIR" in var_names
        assert "LLVM_DIR" in var_names
        assert "MLIR_PREFIX" in var_names
        assert "LLVM_PREFIX" in var_names
        assert "LD_LIBRARY_PATH" in var_names
        assert "DYLD_LIBRARY_PATH" not in var_names

        mlir_var = next(v for v in config.env_vars if v.name == "MLIR_DIR")
        assert mlir_var.value == str(self.prefix / "lib" / "cmake" / "mlir")
        assert mlir_var.prepend_path is False

        ld_var = next(v for v in config.env_vars if v.name == "LD_LIBRARY_PATH")
        assert ld_var.value == str(self.prefix / "lib")
        assert ld_var.prepend_path is True

        assert str(self.prefix / "bin") in config.path_prepends

    @patch("sniff_cli.toolchain.platform.system", return_value="Darwin")
    def test_configure_macos(self, _mock):
        builder = EnvVarBuilder()
        self.tc.configure(builder)
        config = builder.build()

        var_names = [v.name for v in config.env_vars]
        assert "DYLD_LIBRARY_PATH" in var_names
        assert "LD_LIBRARY_PATH" not in var_names

    @patch("sniff_cli.toolchain.platform.system", return_value="Windows")
    def test_configure_windows(self, _mock):
        prefix = Path("C:/miniforge/envs/apxm")
        tc = CMakeToolchain(prefix=prefix)
        builder = EnvVarBuilder()
        tc.configure(builder)
        config = builder.build()

        var_names = [v.name for v in config.env_vars]
        assert "MLIR_DIR" in var_names
        assert "LLVM_DIR" in var_names
        assert "LD_LIBRARY_PATH" not in var_names
        assert "DYLD_LIBRARY_PATH" not in var_names
        assert str(prefix) in config.path_prepends
        assert str(prefix / "Library" / "mingw-w64" / "bin") in config.path_prepends
        assert str(prefix / "Library" / "usr" / "bin") in config.path_prepends
        assert str(prefix / "Library" / "bin") in config.path_prepends
        assert str(prefix / "Scripts") in config.path_prepends
        assert str(prefix / "bin") in config.path_prepends

    @patch("sniff_cli.toolchain.platform.system", return_value="Linux")
    def test_extra_lib_dirs(self, _mock):
        tc = CMakeToolchain(
            prefix=self.prefix,
            extra_lib_dirs=("/opt/release/lib", "/opt/release"),
        )
        builder = EnvVarBuilder()
        tc.configure(builder)
        config = builder.build()

        ld_vars = [v for v in config.env_vars if v.name == "LD_LIBRARY_PATH"]
        # extra_lib_dirs come first, then the prefix lib
        assert len(ld_vars) == 3
        assert ld_vars[0].value == "/opt/release/lib"
        assert ld_vars[1].value == "/opt/release"
        assert ld_vars[2].value == str(self.prefix / "lib")

    def test_generates_valid_activation_script(self):
        """End-to-end: CMakeToolchain -> EnvVarBuilder -> ActivationScriptBuilder."""
        builder = EnvVarBuilder(app_name="apxm")
        self.tc.configure(builder)
        config = builder.build()

        script = ActivationScriptBuilder().build(config, ShellKind.BASH)
        assert "export MLIR_DIR=" in script
        assert "export LLVM_DIR=" in script
        assert str(self.prefix / "bin") in script


# ---------------------------------------------------------------------------
# CondaToolchain
# ---------------------------------------------------------------------------


class TestCondaToolchain:
    def setup_method(self):
        self.prefix = Path("/home/user/miniforge3/envs/apxm")
        self.tc = CondaToolchain(prefix=self.prefix, env_name="apxm")

    def test_frozen(self):
        with pytest.raises(AttributeError):
            self.tc.prefix = Path("/other")  # type: ignore[misc]

    def test_configure(self):
        builder = EnvVarBuilder()
        self.tc.configure(builder)
        config = builder.build()

        var_names = [v.name for v in config.env_vars]
        assert "CONDA_PREFIX" in var_names
        assert "CONDA_DEFAULT_ENV" in var_names

        prefix_var = next(v for v in config.env_vars if v.name == "CONDA_PREFIX")
        assert prefix_var.value == str(self.prefix)

        env_var = next(v for v in config.env_vars if v.name == "CONDA_DEFAULT_ENV")
        assert env_var.value == "apxm"

        assert str(self.prefix / "bin") in config.path_prepends

    def test_configure_without_env_name(self):
        tc = CondaToolchain(prefix=self.prefix)
        builder = EnvVarBuilder()
        tc.configure(builder)
        config = builder.build()

        var_names = [v.name for v in config.env_vars]
        assert "CONDA_PREFIX" in var_names
        assert "CONDA_DEFAULT_ENV" not in var_names

    @patch("sniff_cli.toolchain.platform.system", return_value="Windows")
    def test_configure_windows(self, _mock):
        prefix = Path("C:/miniforge/envs/apxm")
        tc = CondaToolchain(prefix=prefix, env_name="apxm")
        builder = EnvVarBuilder()
        tc.configure(builder)
        config = builder.build()

        assert str(prefix) in config.path_prepends
        assert str(prefix / "Library" / "mingw-w64" / "bin") in config.path_prepends
        assert str(prefix / "Library" / "usr" / "bin") in config.path_prepends
        assert str(prefix / "Library" / "bin") in config.path_prepends
        assert str(prefix / "Scripts") in config.path_prepends
        assert str(prefix / "bin") in config.path_prepends


# ---------------------------------------------------------------------------
# ToolchainProfile protocol
# ---------------------------------------------------------------------------


class TestToolchainProfileProtocol:
    def test_cmake_is_toolchain_profile(self):
        tc = CMakeToolchain(prefix=Path("/opt"))
        assert isinstance(tc, ToolchainProfile)

    def test_conda_is_toolchain_profile(self):
        tc = CondaToolchain(prefix=Path("/opt"))
        assert isinstance(tc, ToolchainProfile)

    def test_custom_toolchain_profile(self):
        """Any class with configure(builder) satisfies the protocol."""

        class CustomToolchain:
            def configure(self, builder: EnvVarBuilder) -> None:
                builder.set_var("CUSTOM", "yes")

        tc = CustomToolchain()
        assert isinstance(tc, ToolchainProfile)

        builder = EnvVarBuilder()
        tc.configure(builder)
        config = builder.build()
        assert config.env_vars[0].name == "CUSTOM"


# ---------------------------------------------------------------------------
# Integration: APXM replacement for setup_mlir_environment
# ---------------------------------------------------------------------------


class TestApxmIntegration:
    """Demonstrate replacing setup_mlir_environment with toolchain profiles."""

    @patch("sniff_cli.toolchain.platform.system", return_value="Linux")
    def test_replaces_setup_mlir_environment(self, _mock):
        """The toolchain module should produce equivalent env vars to
        the old setup_mlir_environment() function."""
        prefix = Path("/home/user/miniforge3/envs/apxm")
        target_dir = Path("/home/user/projects/apxm/target")

        conda = CondaToolchain(prefix=prefix, env_name="apxm")
        cmake = CMakeToolchain(
            prefix=prefix,
            extra_lib_dirs=(
                str(target_dir / "release" / "lib"),
                str(target_dir / "release"),
            ),
        )

        builder = EnvVarBuilder(app_name="apxm")
        builder.set_banner("APXM MLIR/LLVM toolchain activated")
        conda.configure(builder)
        cmake.configure(builder)

        config = builder.build()

        # Verify all vars from the old setup_mlir_environment are present
        var_map = {v.name: v for v in config.env_vars}
        assert var_map["CONDA_PREFIX"].value == str(prefix)
        assert var_map["MLIR_DIR"].value == str(prefix / "lib" / "cmake" / "mlir")
        assert var_map["LLVM_DIR"].value == str(prefix / "lib" / "cmake" / "llvm")

        # Library path includes extra dirs + prefix/lib
        ld_vars = [v for v in config.env_vars if v.name == "LD_LIBRARY_PATH"]
        ld_values = [v.value for v in ld_vars]
        assert str(target_dir / "release" / "lib") in ld_values
        assert str(target_dir / "release") in ld_values
        assert str(prefix / "lib") in ld_values

        # PATH includes conda bin and cmake bin
        assert str(prefix / "bin") in config.path_prepends

        # Banner
        assert config.banner == "APXM MLIR/LLVM toolchain activated"

    def test_all_shells_produce_valid_scripts(self):
        """Verify the config works with all supported shells."""
        prefix = Path("/opt/conda/envs/apxm")
        cmake = CMakeToolchain(prefix=prefix)
        builder = EnvVarBuilder(app_name="apxm")
        cmake.configure(builder)
        config = builder.build()

        script_builder = ActivationScriptBuilder()
        for shell in (ShellKind.BASH, ShellKind.ZSH, ShellKind.FISH,
                      ShellKind.TCSH, ShellKind.POWERSHELL):
            script = script_builder.build(config, shell)
            assert str(prefix) in script
            assert len(script) > 20

    def test_to_env_dict_for_subprocess(self):
        """Verify to_env_dict produces a dict suitable for subprocess calls."""
        prefix = Path("/opt/conda/envs/apxm")
        conda = CondaToolchain(prefix=prefix, env_name="apxm")
        cmake = CMakeToolchain(prefix=prefix)

        builder = EnvVarBuilder()
        conda.configure(builder)
        cmake.configure(builder)

        d = builder.to_env_dict()
        assert d["CONDA_PREFIX"] == str(prefix)
        assert d["MLIR_DIR"] == str(prefix / "lib" / "cmake" / "mlir")
        assert d["LLVM_DIR"] == str(prefix / "lib" / "cmake" / "llvm")
        assert str(prefix / "bin") in d["PATH"]

    @patch("sniff_cli.toolchain.platform.system", return_value="Windows")
    @patch("sniff_cli.toolchain.os.pathsep", ";")
    def test_to_env_dict_uses_windows_separator(self, _platform_mock):
        prefix = Path("C:/miniforge/envs/apxm")
        builder = EnvVarBuilder()
        CondaToolchain(prefix=prefix, env_name="apxm").configure(builder)

        d = builder.to_env_dict()
        assert ";" in d["PATH"]
        assert str(prefix / "Library" / "bin") in d["PATH"]
        assert str(prefix / "Scripts") in d["PATH"]
        assert str(prefix / "bin") in d["PATH"]


# ---------------------------------------------------------------------------
# Real conda prefix example
# ---------------------------------------------------------------------------


class TestRealCondaPrefix:
    """Test with a realistic conda prefix structure.

    Uses tmp_path to create a realistic directory layout.
    """

    def test_cmake_toolchain_with_real_layout(self, tmp_path):
        """Simulate a real conda environment with MLIR/LLVM installed."""
        prefix = tmp_path / "envs" / "apxm"

        # Create realistic directory structure
        (prefix / "bin").mkdir(parents=True)
        (prefix / "lib" / "cmake" / "mlir").mkdir(parents=True)
        (prefix / "lib" / "cmake" / "llvm").mkdir(parents=True)
        (prefix / "lib").mkdir(exist_ok=True)

        tc = CMakeToolchain(prefix=prefix)

        # Verify paths resolve to real directories
        assert tc.mlir_dir.exists()
        assert tc.llvm_dir.exists()
        assert tc.lib_dir.exists()
        assert tc.bin_dir.exists()

        builder = EnvVarBuilder(app_name="apxm")
        tc.configure(builder)
        config = builder.build()

        # All paths should be absolute
        for var in config.env_vars:
            if var.name in ("MLIR_DIR", "LLVM_DIR", "MLIR_PREFIX", "LLVM_PREFIX"):
                assert Path(var.value).is_absolute()

    def test_conda_toolchain_with_real_layout(self, tmp_path):
        """Simulate a real conda environment prefix."""
        prefix = tmp_path / "miniforge3" / "envs" / "apxm"
        (prefix / "bin").mkdir(parents=True)

        tc = CondaToolchain(prefix=prefix, env_name="apxm")
        builder = EnvVarBuilder()
        tc.configure(builder)
        config = builder.build()

        var_map = {v.name: v for v in config.env_vars}
        assert Path(var_map["CONDA_PREFIX"].value).exists()
