"""Tests for library path resolution module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from sniff.detect import PlatformInfo
from sniff.libpath import LibraryPathInfo, LibraryPathResolver


# ---------------------------------------------------------------------------
# LibraryPathResolver construction
# ---------------------------------------------------------------------------


class TestLibraryPathResolverConstruction:
    def test_for_current_platform(self):
        resolver = LibraryPathResolver.for_current_platform()
        assert resolver.platform_info is not None
        assert resolver.env_var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "PATH")

    def test_for_linux_platform(self):
        resolver = LibraryPathResolver.for_platform("Linux")
        assert resolver.env_var == "LD_LIBRARY_PATH"
        assert resolver.platform_info.is_linux

    def test_for_macos_platform(self):
        resolver = LibraryPathResolver.for_platform("Darwin", arch="arm64")
        assert resolver.env_var == "DYLD_LIBRARY_PATH"
        assert resolver.platform_info.is_macos

    def test_for_windows_platform(self):
        resolver = LibraryPathResolver.for_platform("Windows")
        assert resolver.env_var == "PATH"
        assert resolver.platform_info.is_windows

    def test_explicit_platform_info(self):
        info = PlatformInfo(os="Linux", arch="aarch64")
        resolver = LibraryPathResolver(platform_info=info)
        assert resolver.env_var == "LD_LIBRARY_PATH"
        assert resolver.platform_info is info

    def test_unknown_os_defaults_to_ld_library_path(self):
        info = PlatformInfo(os="FreeBSD", arch="x86_64")
        resolver = LibraryPathResolver(platform_info=info)
        assert resolver.env_var == "LD_LIBRARY_PATH"


# ---------------------------------------------------------------------------
# Prepend / Append
# ---------------------------------------------------------------------------


class TestPrependAppend:
    def setup_method(self):
        self.resolver = LibraryPathResolver.for_platform("Linux")

    def test_prepend_single(self):
        self.resolver.prepend("/opt/lib")
        info = self.resolver.resolve()
        assert "/opt/lib" in info.paths

    def test_prepend_multiple(self):
        self.resolver.prepend("/opt/lib", "/usr/local/lib")
        info = self.resolver.resolve()
        assert info.paths[0] == "/opt/lib"
        assert info.paths[1] == "/usr/local/lib"

    def test_append_single(self):
        self.resolver.append("/fallback/lib")
        info = self.resolver.resolve()
        assert "/fallback/lib" in info.paths

    def test_prepend_before_append(self):
        self.resolver.prepend("/first")
        self.resolver.append("/last")
        info = self.resolver.resolve()
        first_idx = info.paths.index("/first")
        last_idx = info.paths.index("/last")
        assert first_idx < last_idx

    def test_chaining(self):
        info = (
            self.resolver
            .prepend("/opt/lib")
            .append("/fallback/lib")
            .resolve()
        )
        assert "/opt/lib" in info.paths
        assert "/fallback/lib" in info.paths

    def test_deduplication_across_prepend(self):
        self.resolver.prepend("/opt/lib")
        self.resolver.prepend("/opt/lib")
        info = self.resolver.resolve()
        assert info.paths.count("/opt/lib") == 1

    def test_deduplication_across_append(self):
        self.resolver.append("/opt/lib")
        self.resolver.append("/opt/lib")
        info = self.resolver.resolve()
        assert info.paths.count("/opt/lib") == 1

    def test_deduplication_prepend_vs_append(self):
        self.resolver.prepend("/opt/lib")
        self.resolver.append("/opt/lib")  # Should be skipped
        info = self.resolver.resolve()
        assert info.paths.count("/opt/lib") == 1

    def test_deduplication_append_vs_prepend(self):
        self.resolver.append("/opt/lib")
        self.resolver.prepend("/opt/lib")  # Should be skipped
        info = self.resolver.resolve()
        assert info.paths.count("/opt/lib") == 1


# ---------------------------------------------------------------------------
# Resolve with existing env
# ---------------------------------------------------------------------------


class TestResolveWithEnv:
    def test_merges_with_existing_env(self):
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/new/lib")

        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/existing/lib"}):
            info = resolver.resolve()

        assert info.paths[0] == "/new/lib"
        assert "/existing/lib" in info.paths

    def test_existing_between_prepend_and_append(self):
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/first")
        resolver.append("/last")

        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/middle"}):
            info = resolver.resolve()

        assert info.paths == ("/first", "/middle", "/last")

    def test_deduplicates_against_existing(self):
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/existing/lib")

        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/existing/lib:/other/lib"}):
            info = resolver.resolve()

        # /existing/lib should appear only once (from prepend, which takes priority)
        assert info.paths.count("/existing/lib") == 1
        assert info.paths[0] == "/existing/lib"  # prepend position wins

    def test_empty_env(self):
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/lib")

        with patch.dict(os.environ, {}, clear=True):
            info = resolver.resolve()

        assert info.paths == ("/opt/lib",)

    def test_empty_everything(self):
        resolver = LibraryPathResolver.for_platform("Linux")

        with patch.dict(os.environ, {}, clear=True):
            info = resolver.resolve()

        assert info.paths == ()

    def test_macos_uses_dyld(self):
        resolver = LibraryPathResolver.for_platform("Darwin")
        resolver.prepend("/opt/lib")

        with patch.dict(os.environ, {"DYLD_LIBRARY_PATH": "/existing"}, clear=True):
            info = resolver.resolve()

        assert info.env_var == "DYLD_LIBRARY_PATH"
        assert "/opt/lib" in info.paths
        assert "/existing" in info.paths


# ---------------------------------------------------------------------------
# LibraryPathInfo
# ---------------------------------------------------------------------------


class TestLibraryPathInfo:
    def test_as_string_linux(self):
        info = LibraryPathInfo(
            env_var="LD_LIBRARY_PATH",
            paths=("/opt/lib", "/usr/local/lib"),
            platform=PlatformInfo(os="Linux", arch="x86_64"),
        )
        assert info.as_string == "/opt/lib:/usr/local/lib"

    def test_as_string_windows(self):
        info = LibraryPathInfo(
            env_var="PATH",
            paths=("C:\\lib", "C:\\usr\\lib"),
            platform=PlatformInfo(os="Windows", arch="x86_64"),
        )
        assert info.as_string == "C:\\lib;C:\\usr\\lib"

    def test_contains(self):
        info = LibraryPathInfo(
            env_var="LD_LIBRARY_PATH",
            paths=("/opt/lib", "/usr/local/lib"),
            platform=PlatformInfo(os="Linux", arch="x86_64"),
        )
        assert info.contains("/opt/lib")
        assert not info.contains("/missing/lib")

    def test_contains_normalizes_path(self):
        info = LibraryPathInfo(
            env_var="LD_LIBRARY_PATH",
            paths=("/opt/lib",),
            platform=PlatformInfo(os="Linux", arch="x86_64"),
        )
        # Trailing slash should still match
        assert info.contains("/opt/lib/")

    def test_empty_paths(self):
        info = LibraryPathInfo(
            env_var="LD_LIBRARY_PATH",
            paths=(),
            platform=PlatformInfo(os="Linux", arch="x86_64"),
        )
        assert info.as_string == ""
        assert not info.contains("/any")


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_sets_env_var(self):
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/lib")

        with patch.dict(os.environ, {}, clear=True):
            info = resolver.apply()
            assert os.environ["LD_LIBRARY_PATH"] == "/opt/lib"
            assert info.env_var == "LD_LIBRARY_PATH"

    def test_apply_preserves_existing(self):
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/new/lib")

        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/existing/lib"}):
            resolver.apply()
            assert os.environ["LD_LIBRARY_PATH"] == "/new/lib:/existing/lib"

    def test_apply_empty_does_not_set(self):
        resolver = LibraryPathResolver.for_platform("Linux")

        with patch.dict(os.environ, {}, clear=True):
            resolver.apply()
            assert "LD_LIBRARY_PATH" not in os.environ


# ---------------------------------------------------------------------------
# to_env_var integration
# ---------------------------------------------------------------------------


class TestToEnvVar:
    def test_to_env_var(self):
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/lib")

        with patch.dict(os.environ, {}, clear=True):
            name, value = resolver.to_env_var()

        assert name == "LD_LIBRARY_PATH"
        assert value == "/opt/lib"

    def test_to_env_var_macos(self):
        resolver = LibraryPathResolver.for_platform("Darwin")
        resolver.prepend("/opt/lib")

        with patch.dict(os.environ, {}, clear=True):
            name, value = resolver.to_env_var()

        assert name == "DYLD_LIBRARY_PATH"
        assert value == "/opt/lib"

    def test_works_with_env_var_dataclass(self):
        """Verify the tuple integrates with sniff.shell.EnvVar."""
        from sniff.shell import EnvVar

        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/lib")

        with patch.dict(os.environ, {}, clear=True):
            name, value = resolver.to_env_var()

        env = EnvVar(name=name, value=value, prepend_path=True)
        assert env.name == "LD_LIBRARY_PATH"
        assert env.value == "/opt/lib"


# ---------------------------------------------------------------------------
# APXM integration scenario
# ---------------------------------------------------------------------------


class TestApxmIntegration:
    """End-to-end test showing how APXM would use LibraryPathResolver."""

    def test_apxm_conda_lib_setup(self):
        """Simulate setting up MLIR/LLVM library paths for APXM."""
        prefix = "/home/user/miniforge3/envs/apxm"
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend(
            f"{prefix}/lib",
            f"{prefix}/lib/cmake/mlir",
        )

        with patch.dict(os.environ, {}, clear=True):
            info = resolver.resolve()

        assert info.env_var == "LD_LIBRARY_PATH"
        assert f"{prefix}/lib" in info.paths
        assert f"{prefix}/lib/cmake/mlir" in info.paths
        assert info.paths[0] == f"{prefix}/lib"

    def test_apxm_macos_cross_platform(self):
        """Same setup but targeting macOS."""
        prefix = "/opt/homebrew/opt/llvm"
        resolver = LibraryPathResolver.for_platform("Darwin", arch="arm64")
        resolver.prepend(f"{prefix}/lib")

        with patch.dict(os.environ, {}, clear=True):
            info = resolver.resolve()

        assert info.env_var == "DYLD_LIBRARY_PATH"
        assert f"{prefix}/lib" in info.paths

    def test_linux_current_platform(self):
        """Verify for_current_platform works on this Linux machine."""
        resolver = LibraryPathResolver.for_current_platform()

        # On this Linux machine, should use LD_LIBRARY_PATH
        assert resolver.env_var == "LD_LIBRARY_PATH"
        assert resolver.platform_info.is_linux


# ---------------------------------------------------------------------------
# configure_builder integration
# ---------------------------------------------------------------------------


class TestConfigureBuilder:
    """Test LibraryPathResolver.configure_builder with both builder types."""

    def test_configure_env_builder(self):
        """configure_builder with sniff.env.EnvVarBuilder (has set_from_path)."""
        from sniff.env import EnvVarBuilder

        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/lib", "/usr/local/lib")

        builder = EnvVarBuilder()
        with patch.dict(os.environ, {}, clear=True):
            resolver.configure_builder(builder)

        snap = builder.build()
        value = snap.get("LD_LIBRARY_PATH")
        assert value is not None
        assert "/opt/lib" in value
        assert "/usr/local/lib" in value

    def test_configure_toolchain_builder(self):
        """configure_builder with sniff.toolchain.EnvVarBuilder (has prepend_var)."""
        from sniff.toolchain import EnvVarBuilder as TcBuilder

        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/lib")

        builder = TcBuilder()
        with patch.dict(os.environ, {}, clear=True):
            resolver.configure_builder(builder)

        config = builder.build()
        ld_vars = [v for v in config.env_vars if v.name == "LD_LIBRARY_PATH"]
        assert len(ld_vars) == 1
        assert ld_vars[0].prepend_path is True

    def test_configure_unsupported_builder(self):
        """configure_builder raises TypeError for unknown builder types."""
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/lib")

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(TypeError, match="Unsupported builder"):
                resolver.configure_builder(object())

    def test_configure_builder_empty_resolves_noop(self):
        """configure_builder with no paths does nothing."""
        from sniff.env import EnvVarBuilder

        resolver = LibraryPathResolver.for_platform("Linux")
        builder = EnvVarBuilder()

        with patch.dict(os.environ, {}, clear=True):
            resolver.configure_builder(builder)

        snap = builder.build()
        assert snap.get("LD_LIBRARY_PATH") is None

    def test_configure_macos_builder(self):
        """configure_builder sets DYLD_LIBRARY_PATH for macOS."""
        from sniff.env import EnvVarBuilder

        resolver = LibraryPathResolver.for_platform("Darwin")
        resolver.prepend("/opt/lib")

        builder = EnvVarBuilder()
        with patch.dict(os.environ, {}, clear=True):
            resolver.configure_builder(builder)

        snap = builder.build()
        assert snap.get("DYLD_LIBRARY_PATH") is not None
        assert snap.get("LD_LIBRARY_PATH") is None


# ---------------------------------------------------------------------------
# Cross-module: libpath + toolchain end-to-end
# ---------------------------------------------------------------------------


class TestLibpathToolchainIntegration:
    """End-to-end tests combining libpath with toolchain profiles."""

    def test_libpath_then_cmake_toolchain(self):
        """LibraryPathResolver and CMakeToolchain can both contribute to the same builder."""
        from pathlib import Path as P
        from sniff.toolchain import CMakeToolchain, EnvVarBuilder as TcBuilder

        prefix = "/opt/conda/envs/apxm"
        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/custom/runtime/lib")

        builder = TcBuilder(app_name="apxm")

        with patch.dict(os.environ, {}, clear=True):
            # First, libpath resolver contributes
            resolver.configure_builder(builder)
            # Then, CMakeToolchain contributes
            from unittest.mock import patch as mpatch
            with mpatch("sniff.toolchain.platform.system", return_value="Linux"):
                cmake = CMakeToolchain(prefix=P(prefix))
                cmake.configure(builder)

        config = builder.build()
        ld_vars = [v for v in config.env_vars if v.name == "LD_LIBRARY_PATH"]
        # Both the resolver's path and cmake's prefix/lib should be present
        ld_values = [v.value for v in ld_vars]
        assert "/custom/runtime/lib" in ld_values
        assert f"{prefix}/lib" in ld_values
