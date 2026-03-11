"""Tests for the CLI command helpers module."""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from sniff.context import (
    CPUInfo,
    ContextWorkspaceInfo,
    ExecutionContext,
    GitInfo,
    GPUInfo,
    MemoryInfo,
)
from sniff.ci import CIBuildInfo, CIInfo, CIProvider
from sniff.detect import PlatformInfo
from sniff.conda import CondaEnvironment
from sniff.cli_commands import (
    run_doctor,
    run_env,
    run_version,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_platform(**overrides) -> PlatformInfo:
    defaults = dict(os="Linux", arch="x86_64")
    defaults.update(overrides)
    return PlatformInfo(**defaults)


def _make_cpu(**overrides) -> CPUInfo:
    defaults = dict(model="TestCPU", cores=8, threads=16, frequency_mhz=3600.0)
    defaults.update(overrides)
    return CPUInfo(**defaults)


def _make_memory(**overrides) -> MemoryInfo:
    defaults = dict(total_mb=16384, available_mb=8192, used_mb=8192)
    defaults.update(overrides)
    return MemoryInfo(**defaults)


def _make_gpu(**overrides) -> GPUInfo:
    defaults = dict(vendor="nvidia", model="RTX 4090", memory_mb=24576, driver_version="535.0")
    defaults.update(overrides)
    return GPUInfo(**defaults)


def _make_workspace(**overrides) -> ContextWorkspaceInfo:
    defaults = dict(
        root=Path("/tmp/project"),
        git_info=None,
        build_artifacts=[],
        config_files=[],
    )
    defaults.update(overrides)
    return ContextWorkspaceInfo(**defaults)


def _make_ci_info(is_ci: bool = False, **overrides) -> CIInfo:
    defaults = dict(
        is_ci=is_ci,
        provider=CIProvider(name="github_actions", display_name="GitHub Actions") if is_ci else None,
        build=CIBuildInfo(build_id="12345") if is_ci else CIBuildInfo(),
    )
    defaults.update(overrides)
    return CIInfo(**defaults)


def _make_conda(**overrides) -> CondaEnvironment:
    defaults = dict(name="myenv", prefix=Path("/opt/conda/envs/myenv"), is_active=True)
    defaults.update(overrides)
    return CondaEnvironment(**defaults)


def _make_context(**overrides) -> ExecutionContext:
    defaults = dict(
        platform=_make_platform(),
        conda_env=None,
        ci_info=_make_ci_info(),
        workspace=_make_workspace(),
        build_system=None,
        installed_packages={"numpy": "1.24.0", "pytest": "7.4.0"},
        system_libraries=[],
        cpu_info=_make_cpu(),
        gpu_info=[],
        memory_info=_make_memory(),
        env_vars={"PATH": "/usr/bin", "HOME": "/home/user"},
        command_line=["python", "-m", "myapp"],
        working_dir=Path("/tmp/project"),
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _make_test_console() -> tuple[Console, StringIO]:
    """Create a Console that writes plain text (no ANSI escapes) to a buffer."""
    buf = StringIO()
    con = Console(file=buf, no_color=True, highlight=False, width=200)
    return con, buf


def _capture_output(func, *args, **kwargs) -> str:
    """Call func while patching the styles module console, return the output."""
    test_console, buf = _make_test_console()
    with patch("sniff.cli.styles.console", test_console), \
         patch("sniff.cli_commands.console", test_console):
        func(*args, **kwargs)
    return buf.getvalue()


# ===========================================================================
# run_doctor
# ===========================================================================

class TestRunDoctor:
    def test_shows_platform_info(self):
        ctx = _make_context()
        out = _capture_output(run_doctor, ctx)
        assert "Platform Information" in out
        assert "Linux" in out
        assert "x86_64" in out

    def test_shows_python_version(self):
        ctx = _make_context()
        out = _capture_output(run_doctor, ctx)
        assert platform.python_version() in out
        assert "Python" in out

    def test_shows_hostname(self):
        ctx = _make_context()
        out = _capture_output(run_doctor, ctx)
        assert "Hostname" in out
        assert platform.node() in out

    def test_no_conda(self):
        ctx = _make_context(conda_env=None)
        out = _capture_output(run_doctor, ctx)
        assert "Conda Environment" not in out

    def test_with_conda(self):
        conda = _make_conda()
        ctx = _make_context(conda_env=conda)
        out = _capture_output(run_doctor, ctx)
        assert "Conda Environment" in out
        assert "myenv" in out
        assert "Prefix" in out

    def test_conda_shows_package_count(self):
        conda = _make_conda()
        ctx = _make_context(
            conda_env=conda,
            installed_packages={"a": "1", "b": "2", "c": "3"},
        )
        out = _capture_output(run_doctor, ctx)
        assert "Packages: 3" in out

    def test_no_ci(self):
        ctx = _make_context(ci_info=_make_ci_info(is_ci=False))
        out = _capture_output(run_doctor, ctx)
        assert "CI Environment" not in out

    def test_with_ci(self):
        ctx = _make_context(ci_info=_make_ci_info(is_ci=True))
        out = _capture_output(run_doctor, ctx)
        assert "CI Environment" in out
        assert "GitHub Actions" in out

    def test_ci_shows_build_id(self):
        ctx = _make_context(ci_info=_make_ci_info(is_ci=True))
        out = _capture_output(run_doctor, ctx)
        assert "Build ID" in out
        assert "12345" in out

    def test_hardware_cpu(self):
        ctx = _make_context(cpu_info=_make_cpu(model="AMD EPYC", cores=64))
        out = _capture_output(run_doctor, ctx)
        assert "Hardware" in out
        assert "AMD EPYC" in out
        assert "64 cores" in out

    def test_hardware_memory(self):
        ctx = _make_context(memory_info=_make_memory(total_mb=32768))
        out = _capture_output(run_doctor, ctx)
        assert "32768 MB" in out

    def test_no_gpu(self):
        ctx = _make_context(gpu_info=[])
        out = _capture_output(run_doctor, ctx)
        assert "GPU:" not in out

    def test_single_gpu(self):
        gpu = _make_gpu(vendor="nvidia", model="RTX 4090")
        ctx = _make_context(gpu_info=[gpu])
        out = _capture_output(run_doctor, ctx)
        assert "nvidia" in out
        assert "RTX 4090" in out

    def test_multiple_gpus(self):
        gpus = [
            _make_gpu(vendor="nvidia", model="A100"),
            _make_gpu(vendor="amd", model="MI300X"),
        ]
        ctx = _make_context(gpu_info=gpus)
        out = _capture_output(run_doctor, ctx)
        assert "A100" in out
        assert "MI300X" in out

    def test_packages_summary(self):
        ctx = _make_context(installed_packages={"a": "1", "b": "2"})
        out = _capture_output(run_doctor, ctx)
        assert "Packages" in out
        assert "2 installed" in out

    def test_no_packages(self):
        ctx = _make_context(installed_packages={})
        out = _capture_output(run_doctor, ctx)
        # Should not show packages section if empty
        assert "installed" not in out

    def test_platform_as_dict(self):
        """Handle platform stored as a dict (from from_dict)."""
        ctx = _make_context(platform={"os": "Linux", "arch": "x86_64"})
        out = _capture_output(run_doctor, ctx)
        # Should still render without error
        assert "Platform Information" in out

    def test_ci_info_none_provider(self):
        """CI info with is_ci=True but provider=None."""
        ci = CIInfo(is_ci=True, provider=None, build=CIBuildInfo())
        ctx = _make_context(ci_info=ci)
        out = _capture_output(run_doctor, ctx)
        assert "CI Environment" in out
        assert "Provider" not in out

    def test_ci_info_no_build_id(self):
        """CI info with is_ci=True but no build_id."""
        ci = CIInfo(
            is_ci=True,
            provider=CIProvider(name="gitlab_ci", display_name="GitLab CI"),
            build=CIBuildInfo(build_id=None),
        )
        ctx = _make_context(ci_info=ci)
        out = _capture_output(run_doctor, ctx)
        assert "GitLab CI" in out
        assert "Build ID" not in out

    def test_darwin_platform(self):
        ctx = _make_context(platform=_make_platform(os="Darwin", arch="arm64"))
        out = _capture_output(run_doctor, ctx)
        assert "Darwin" in out
        assert "arm64" in out

    def test_windows_platform(self):
        ctx = _make_context(platform=_make_platform(os="Windows", arch="x86_64"))
        out = _capture_output(run_doctor, ctx)
        assert "Windows" in out

    def test_cpu_no_frequency(self):
        ctx = _make_context(cpu_info=_make_cpu(frequency_mhz=None))
        out = _capture_output(run_doctor, ctx)
        assert "TestCPU" in out

    def test_zero_memory(self):
        ctx = _make_context(memory_info=_make_memory(total_mb=0))
        out = _capture_output(run_doctor, ctx)
        assert "0 MB" in out


# ===========================================================================
# run_version
# ===========================================================================

class TestRunVersion:
    def _capture(self, app_name, version, context) -> str:
        return _capture_output(run_version, app_name, version, context)

    def test_shows_app_name_and_version(self):
        ctx = _make_context()
        out = self._capture("myapp", "1.2.3", ctx)
        assert "myapp" in out
        assert "1.2.3" in out

    def test_shows_python_version(self):
        ctx = _make_context()
        out = self._capture("myapp", "1.0", ctx)
        assert platform.python_version() in out

    def test_shows_platform(self):
        ctx = _make_context()
        out = self._capture("myapp", "1.0", ctx)
        assert "Linux" in out
        assert "x86_64" in out

    def test_no_app_name(self):
        ctx = _make_context()
        out = self._capture(None, "1.0", ctx)
        # Should not show app line
        assert "version" not in out.split("\n")[0] or "None" not in out

    def test_no_version(self):
        ctx = _make_context()
        out = self._capture("myapp", None, ctx)
        # Still shows python and platform but not "myapp version None"
        assert "Python" in out

    def test_both_none(self):
        ctx = _make_context()
        out = self._capture(None, None, ctx)
        assert "Python" in out
        assert "Platform" in out

    def test_empty_strings(self):
        ctx = _make_context()
        out = self._capture("", "", ctx)
        assert "Python" in out

    def test_darwin_platform(self):
        ctx = _make_context(platform=_make_platform(os="Darwin", arch="arm64"))
        out = self._capture("tool", "2.0", ctx)
        assert "Darwin" in out
        assert "arm64" in out

    def test_platform_as_dict(self):
        ctx = _make_context(platform={"os": "Linux", "arch": "aarch64"})
        out = self._capture("tool", "1.0", ctx)
        # Should not crash; shows fallback
        assert "Platform" in out


# ===========================================================================
# run_env
# ===========================================================================

class TestRunEnv:
    def _capture(self, context) -> str:
        return _capture_output(run_env, context)

    def test_shows_env_vars_table(self):
        ctx = _make_context(env_vars={"HOME": "/home/user", "PATH": "/usr/bin"})
        out = self._capture(ctx)
        assert "Environment Variables" in out
        assert "HOME" in out
        assert "PATH" in out

    def test_env_vars_sorted(self):
        ctx = _make_context(env_vars={"ZEBRA": "z", "ALPHA": "a"})
        out = self._capture(ctx)
        alpha_pos = out.index("ALPHA")
        zebra_pos = out.index("ZEBRA")
        assert alpha_pos < zebra_pos

    def test_empty_env_vars(self):
        ctx = _make_context(env_vars={})
        out = self._capture(ctx)
        # Table title may word-wrap when the table is narrow (no rows)
        assert "Environment" in out
        assert "Variables" in out

    def test_shows_installed_packages(self):
        ctx = _make_context(installed_packages={"numpy": "1.24.0", "pytest": "7.4.0"})
        out = self._capture(ctx)
        assert "Installed Packages" in out
        assert "numpy" in out
        assert "1.24.0" in out

    def test_packages_sorted(self):
        ctx = _make_context(installed_packages={"zlib": "1.0", "attrs": "23.0"})
        out = self._capture(ctx)
        attrs_pos = out.index("attrs")
        zlib_pos = out.index("zlib")
        assert attrs_pos < zlib_pos

    def test_packages_limited_to_20(self):
        pkgs = {f"pkg-{i:03d}": f"{i}.0" for i in range(30)}
        ctx = _make_context(installed_packages=pkgs)
        out = self._capture(ctx)
        # First 20 sorted packages should appear
        assert "pkg-000" in out
        assert "pkg-019" in out
        # 21st onward should not appear
        assert "pkg-020" not in out

    def test_no_packages(self):
        ctx = _make_context(installed_packages={})
        out = self._capture(ctx)
        assert "Installed Packages" in out

    def test_env_var_values_displayed(self):
        ctx = _make_context(env_vars={"MY_VAR": "/some/path/value"})
        out = self._capture(ctx)
        assert "/some/path/value" in out

    def test_long_env_var(self):
        long_val = "x" * 500
        ctx = _make_context(env_vars={"LONG": long_val})
        out = self._capture(ctx)
        assert "LONG" in out

    def test_special_chars_in_env_var(self):
        ctx = _make_context(env_vars={"SPECIAL": "val=with=equals&and!bang"})
        out = self._capture(ctx)
        assert "SPECIAL" in out


# ===========================================================================
# Integration / edge cases
# ===========================================================================

class TestEdgeCases:
    def test_run_doctor_returns_none(self):
        ctx = _make_context()
        result = _capture_output(run_doctor, ctx)
        # run_doctor returns None (we just check it doesn't raise)
        test_console, buf = _make_test_console()
        with patch("sniff.cli.styles.console", test_console), \
             patch("sniff.cli_commands.console", test_console):
            assert run_doctor(ctx) is None

    def test_run_version_returns_none(self):
        ctx = _make_context()
        test_console, buf = _make_test_console()
        with patch("sniff.cli.styles.console", test_console), \
             patch("sniff.cli_commands.console", test_console):
            assert run_version("app", "1.0", ctx) is None

    def test_run_env_returns_none(self):
        ctx = _make_context()
        test_console, buf = _make_test_console()
        with patch("sniff.cli.styles.console", test_console), \
             patch("sniff.cli_commands.console", test_console):
            assert run_env(ctx) is None

    def test_doctor_full_context(self):
        """Test with all optional fields populated."""
        ctx = _make_context(
            conda_env=_make_conda(),
            ci_info=_make_ci_info(is_ci=True),
            gpu_info=[_make_gpu()],
            installed_packages={"pkg": "1.0"},
        )
        out = _capture_output(run_doctor, ctx)
        assert "Conda Environment" in out
        assert "CI Environment" in out
        assert "GPU" in out
        assert "Packages" in out
        assert "1 installed" in out

    def test_doctor_minimal_context(self):
        """Test with minimal context (no conda, no CI, no GPU, no packages)."""
        ctx = _make_context(
            conda_env=None,
            ci_info=_make_ci_info(is_ci=False),
            gpu_info=[],
            installed_packages={},
        )
        out = _capture_output(run_doctor, ctx)
        assert "Platform Information" in out
        assert "Hardware" in out
        assert "Conda Environment" not in out
        assert "CI Environment" not in out

    def test_conda_without_prefix(self):
        """CondaEnvironment-like object without prefix attribute."""
        mock_conda = MagicMock()
        mock_conda.name = "testenv"
        del mock_conda.prefix  # remove prefix attr
        ctx = _make_context(conda_env=mock_conda)
        out = _capture_output(run_doctor, ctx)
        assert "testenv" in out
        assert "Prefix" not in out

    def test_ci_provider_as_string(self):
        """Provider that is just a string (e.g. from deserialization)."""
        ci = MagicMock()
        ci.is_ci = True
        ci.provider = "SomeCI"
        ci.build = CIBuildInfo(build_id="99")
        ctx = _make_context(ci_info=ci)
        out = _capture_output(run_doctor, ctx)
        assert "CI Environment" in out
