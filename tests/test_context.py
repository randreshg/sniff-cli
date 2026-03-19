"""Focused tests for execution context capture and comparison."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from sniff_cli.context import (
    CPUInfo,
    ContextDiff,
    ContextWorkspaceInfo,
    ExecutionContext,
    GitInfo,
    GPUInfo,
    MemoryInfo,
    SystemLibrary,
    _detect_amd_gpus,
    _detect_git_info,
    _detect_gpus,
    _detect_installed_packages,
    _detect_intel_gpus,
    _detect_memory_info,
    _detect_nvidia_gpus,
    _detect_workspace,
    _serialize_value,
)


@pytest.mark.parametrize(
    ("factory", "field_name", "new_value"),
    [
        (
            lambda: GitInfo("abc123", "main", False, None),
            "branch",
            "dev",
        ),
        (
            lambda: ContextWorkspaceInfo(Path("/tmp/project"), None, [], []),
            "root",
            Path("/other"),
        ),
        (
            lambda: CPUInfo("Intel", 8, 16, 3200.0),
            "cores",
            4,
        ),
        (
            lambda: GPUInfo("nvidia", "RTX 4090", 24576, "535"),
            "vendor",
            "amd",
        ),
        (
            lambda: MemoryInfo(16384, 8192, 8192),
            "total_mb",
            0,
        ),
        (
            lambda: SystemLibrary("ssl", "3.0", Path("/usr/lib/libssl.so")),
            "name",
            "crypto",
        ),
    ],
)
def test_supporting_dataclasses_are_frozen(factory, field_name, new_value):
    obj = factory()
    with pytest.raises((AttributeError, FrozenInstanceError)):
        setattr(obj, field_name, new_value)


def test_context_diff_summary_tracks_compatibility_drivers():
    diff = ContextDiff(
        platform_changed=True,
        conda_env_changed=False,
        package_changes={"numpy": ("1.26.0", "2.0.0")},
        env_var_changes={"PATH": ("/old", "/new")},
        hardware_changes=["CPU: Intel -> AMD"],
        git_changes={"branch": ("main", "feature")},
    )

    assert not diff.is_compatible()
    summary = diff.summary()
    assert "Platform: changed" in summary
    assert "Package changes: 1" in summary
    assert "~ numpy 1.26.0 -> 2.0.0" in summary
    assert "Environment variable changes: 1" in summary
    assert "Hardware changes: 1" in summary
    assert "Git changes: 1" in summary


def test_context_diff_without_changes_is_compatible():
    diff = ContextDiff(
        platform_changed=False,
        conda_env_changed=False,
        package_changes={},
        env_var_changes={},
        hardware_changes=[],
        git_changes={},
    )

    assert diff.is_compatible()
    assert diff.summary() == "No differences"


def test_detect_git_info_returns_none_without_git_dir(tmp_path):
    assert _detect_git_info(tmp_path) is None


@patch("sniff_cli.context.subprocess.run")
def test_detect_git_info_parses_git_state(mock_run, tmp_path):
    (tmp_path / ".git").mkdir()

    def side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0, stdout="")
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            result.stdout = "abc123def\n"
        elif cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            result.stdout = "main\n"
        elif cmd[:3] == ["git", "status", "--porcelain"]:
            result.stdout = " M file.py\n"
        elif cmd[:4] == ["git", "remote", "get-url", "origin"]:
            result.stdout = "https://github.com/example/repo.git\n"
        return result

    mock_run.side_effect = side_effect

    result = _detect_git_info(tmp_path)

    assert result == GitInfo(
        commit_sha="abc123def",
        branch="main",
        is_dirty=True,
        remote_url="https://github.com/example/repo.git",
    )


@patch("sniff_cli.context.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5))
def test_detect_git_info_handles_subprocess_failures(mock_run, tmp_path):
    (tmp_path / ".git").mkdir()
    assert _detect_git_info(tmp_path) is None


def test_detect_workspace_walks_to_project_root_and_collects_markers(tmp_path):
    root = tmp_path / "repo"
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (root / "Makefile").write_text("test:\n\tpytest\n")
    (root / "build").mkdir()
    (root / "dist").mkdir()

    workspace = _detect_workspace(nested)

    assert workspace.root == root
    assert workspace.git_info is None
    assert root / "build" in workspace.build_artifacts
    assert root / "dist" in workspace.build_artifacts
    assert root / "pyproject.toml" in workspace.config_files
    assert root / "Makefile" in workspace.config_files


def test_detect_cpu_info_returns_sane_values():
    result = _detect_memory_info()
    assert result.total_mb >= 0


@patch("sniff_cli.context.platform.processor", return_value="Fallback CPU")
@patch("sniff_cli.context.os.cpu_count", return_value=4)
def test_detect_cpu_info_falls_back_without_psutil(mock_cpu_count, mock_processor):
    with patch.dict("sys.modules", {"psutil": None}):
        with patch("sniff_cli.context.sys.platform", "unknown"):
            result = ExecutionContext.capture(
                include_env_vars=False,
                include_packages=False,
                include_hardware=False,
            ).cpu_info

    assert result.model == "unknown"
    assert result.cores == 0


@patch("shutil.which", return_value=None)
def test_detect_nvidia_gpus_returns_empty_without_tool(mock_which):
    assert _detect_nvidia_gpus() == []


@patch("sniff_cli.context.subprocess.run")
@patch("shutil.which", return_value="/usr/bin/nvidia-smi")
def test_detect_nvidia_gpus_parses_cli_output(mock_which, mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="NVIDIA GeForce RTX 4090, 24564, 535.129.03\n",
    )

    result = _detect_nvidia_gpus()

    assert result == [
        GPUInfo(
            vendor="nvidia",
            model="NVIDIA GeForce RTX 4090",
            memory_mb=24564,
            driver_version="535.129.03",
        )
    ]


@patch("sniff_cli.context.subprocess.run")
@patch("shutil.which", return_value="/usr/bin/rocm-smi")
def test_detect_amd_gpus_uses_fallback_output(mock_which, mock_run):
    mock_run.side_effect = [
        MagicMock(returncode=1, stdout=""),
        MagicMock(returncode=0, stdout="AMD Instinct MI300X\n"),
    ]

    result = _detect_amd_gpus()

    assert result == [
        GPUInfo(
            vendor="amd",
            model="AMD Instinct MI300X",
            memory_mb=None,
            driver_version=None,
        )
    ]


def test_detect_intel_gpus_reads_sysfs_layout(tmp_path):
    drm_root = tmp_path / "sys" / "class" / "drm"
    card = drm_root / "card0" / "device"
    card.mkdir(parents=True)
    (card / "vendor").write_text("0x8086")
    (card / "label").write_text("Intel Arc A770")
    real_path = Path

    with patch(
        "sniff_cli.context.Path",
        side_effect=lambda value: drm_root if value == "/sys/class/drm" else real_path(value),
    ):
        result = _detect_intel_gpus()

    assert result == [
        GPUInfo(
            vendor="intel",
            model="Intel Arc A770",
            memory_mb=None,
            driver_version=None,
        )
    ]


@patch(
    "sniff_cli.context._detect_nvidia_gpus",
    return_value=[GPUInfo("nvidia", "RTX", 8192, "535")],
)
@patch(
    "sniff_cli.context._detect_amd_gpus",
    return_value=[GPUInfo("amd", "MI300X", 192000, None)],
)
@patch(
    "sniff_cli.context._detect_intel_gpus",
    return_value=[GPUInfo("intel", "Arc", None, None)],
)
def test_detect_gpus_merges_all_vendor_detectors(mock_intel, mock_amd, mock_nvidia):
    result = _detect_gpus()
    assert [gpu.vendor for gpu in result] == ["nvidia", "amd", "intel"]


def test_detect_installed_packages_returns_string_versions():
    result = _detect_installed_packages()
    assert isinstance(result, dict)
    assert all(isinstance(name, str) and isinstance(version, str) for name, version in result.items())


def test_serialize_value_handles_nested_paths_dataclasses_and_datetimes():
    payload = {
        "root": Path("/tmp/project"),
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "cpu": CPUInfo("Intel", 8, 16, 3200.0),
        "items": (Path("/a"), Path("/b")),
    }

    result = _serialize_value(payload)

    assert result["root"] == "/tmp/project"
    assert result["timestamp"].startswith("2026-01-01")
    assert result["cpu"]["model"] == "Intel"
    assert result["items"] == ["/a", "/b"]


def _make_context(**overrides) -> ExecutionContext:
    from sniff_cli.ci import CIInfo
    from sniff_cli.detect import PlatformInfo

    defaults = dict(
        platform=PlatformInfo(os="Linux", arch="x86_64"),
        conda_env=None,
        ci_info=CIInfo(is_ci=False),
        workspace=ContextWorkspaceInfo(
            root=Path("/project"),
            git_info=GitInfo("abc123", "main", False, None),
            build_artifacts=[Path("/project/build")],
            config_files=[Path("/project/pyproject.toml")],
        ),
        build_system=None,
        installed_packages={"pytest": "8.4.0"},
        system_libraries=[SystemLibrary("ssl", "3.0", Path("/usr/lib/libssl.so"))],
        cpu_info=CPUInfo("Intel", 8, 16, 3200.0),
        gpu_info=[GPUInfo("nvidia", "RTX 4090", 24576, "535")],
        memory_info=MemoryInfo(16384, 8192, 8192),
        env_vars={"HOME": "/home/user"},
        command_line=["python", "tool.py"],
        working_dir=Path("/project"),
        timestamp=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def test_execution_context_capture_respects_optional_sections():
    from sniff_cli.ci import CIInfo
    from sniff_cli.detect import PlatformInfo

    workspace = ContextWorkspaceInfo(Path.cwd(), None, [], [])
    fake_platform = PlatformInfo(os="Linux", arch="x86_64")
    fake_ci = CIInfo(is_ci=False)

    with patch("sniff_cli.detect.PlatformDetector.detect", return_value=fake_platform), patch(
        "sniff_cli.conda.CondaDetector.find_active", return_value=None
    ), patch("sniff_cli.ci.CIDetector.detect", return_value=fake_ci), patch(
        "sniff_cli.context._detect_workspace", return_value=workspace
    ):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )

    assert ctx.env_vars == {}
    assert ctx.installed_packages == {}
    assert ctx.cpu_info == CPUInfo(model="unknown", cores=0, threads=0, frequency_mhz=None)
    assert ctx.gpu_info == []
    assert ctx.memory_info == MemoryInfo(total_mb=0, available_mb=0, used_mb=0)


def test_execution_context_capture_includes_requested_sections():
    from sniff_cli.ci import CIInfo
    from sniff_cli.detect import PlatformInfo

    fake_platform = PlatformInfo(os="Linux", arch="x86_64")
    fake_ci = CIInfo(is_ci=False)
    workspace = ContextWorkspaceInfo(Path.cwd(), None, [], [])
    cpu = CPUInfo("Intel", 8, 16, 3200.0)
    gpu = [GPUInfo("nvidia", "RTX", 8192, "535")]
    memory = MemoryInfo(16384, 8192, 8192)

    with patch("sniff_cli.detect.PlatformDetector.detect", return_value=fake_platform), patch(
        "sniff_cli.conda.CondaDetector.find_active", return_value=None
    ), patch("sniff_cli.ci.CIDetector.detect", return_value=fake_ci), patch(
        "sniff_cli.context._detect_workspace", return_value=workspace
    ), patch("sniff_cli.context._detect_installed_packages", return_value={"pytest": "8.4.0"}), patch(
        "sniff_cli.context._detect_cpu_info", return_value=cpu
    ), patch("sniff_cli.context._detect_gpus", return_value=gpu), patch(
        "sniff_cli.context._detect_memory_info", return_value=memory
    ):
        ctx = ExecutionContext.capture()

    assert "PATH" in ctx.env_vars
    assert ctx.installed_packages == {"pytest": "8.4.0"}
    assert ctx.cpu_info == cpu
    assert ctx.gpu_info == gpu
    assert ctx.memory_info == memory


def test_execution_context_roundtrip_to_dict_is_json_serializable():
    ctx = _make_context()

    result = ctx.to_dict()
    payload = json.loads(json.dumps(result))
    restored = ExecutionContext.from_dict(payload)

    assert restored.workspace.root == Path("/project")
    assert restored.workspace.git_info == GitInfo("abc123", "main", False, None)
    assert restored.system_libraries == [SystemLibrary("ssl", "3.0", Path("/usr/lib/libssl.so"))]
    assert restored.cpu_info.model == "Intel"
    assert restored.gpu_info[0].model == "RTX 4090"
    assert restored.timestamp.year == 2026


def test_execution_context_fingerprint_tracks_reproducibility_inputs_only():
    base = _make_context()
    env_changed = _make_context(env_vars={"HOME": "/other"})
    hardware_changed = _make_context(cpu_info=CPUInfo("AMD", 16, 32, 4200.0))
    package_changed = _make_context(installed_packages={"pytest": "9.0.0"})

    assert base.fingerprint() == env_changed.fingerprint()
    assert base.fingerprint() == hardware_changed.fingerprint()
    assert base.fingerprint() != package_changed.fingerprint()


def test_execution_context_diff_separates_compatibility_breakers_from_noise():
    base = _make_context()
    compatible = _make_context(
        env_vars={"HOME": "/different"},
        cpu_info=CPUInfo("AMD", 16, 32, 4200.0),
    )
    incompatible = _make_context(
        installed_packages={"pytest": "9.0.0"},
        workspace=ContextWorkspaceInfo(
            root=Path("/project"),
            git_info=GitInfo("def456", "feature", True, None),
            build_artifacts=[Path("/project/build")],
            config_files=[Path("/project/pyproject.toml")],
        ),
    )

    compatible_diff = base.diff(compatible)
    incompatible_diff = base.diff(incompatible)

    assert compatible_diff.is_compatible()
    assert compatible_diff.env_var_changes["HOME"] == ("/home/user", "/different")
    assert any(change.startswith("CPU:") for change in compatible_diff.hardware_changes)

    assert not incompatible_diff.is_compatible()
    assert incompatible_diff.package_changes["pytest"] == ("8.4.0", "9.0.0")
    assert incompatible_diff.git_changes["commit_sha"] == ("abc123", "def456")
    assert incompatible_diff.git_changes["branch"] == ("main", "feature")
    assert incompatible_diff.git_changes["is_dirty"] == (False, True)

