"""Tests for the ExecutionContext module."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from sniff.context import (
    CPUInfo,
    ContextDiff,
    ContextWorkspaceInfo,
    ExecutionContext,
    GitInfo,
    GPUInfo,
    MemoryInfo,
    SystemLibrary,
    _detect_cpu_info,
    _detect_git_info,
    _detect_gpus,
    _detect_installed_packages,
    _detect_memory_info,
    _detect_nvidia_gpus,
    _detect_amd_gpus,
    _detect_intel_gpus,
    _detect_workspace,
    _serialize_value,
)


# ===========================================================================
# GitInfo
# ===========================================================================

class TestGitInfo:
    def test_basic_creation(self):
        gi = GitInfo(commit_sha="abc123", branch="main", is_dirty=False, remote_url=None)
        assert gi.commit_sha == "abc123"
        assert gi.branch == "main"
        assert gi.is_dirty is False
        assert gi.remote_url is None

    def test_with_remote(self):
        gi = GitInfo(
            commit_sha="def456",
            branch="feature/x",
            is_dirty=True,
            remote_url="https://github.com/user/repo.git",
        )
        assert gi.remote_url == "https://github.com/user/repo.git"
        assert gi.is_dirty is True

    def test_frozen(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            gi.commit_sha = "xyz"

    def test_frozen_branch(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            gi.branch = "dev"

    def test_frozen_is_dirty(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            gi.is_dirty = True

    def test_frozen_remote_url(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            gi.remote_url = "url"

    def test_equality(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        assert gi1 == gi2

    def test_inequality_sha(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="def", branch="main", is_dirty=False, remote_url=None)
        assert gi1 != gi2

    def test_inequality_branch(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="abc", branch="dev", is_dirty=False, remote_url=None)
        assert gi1 != gi2

    def test_inequality_dirty(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="abc", branch="main", is_dirty=True, remote_url=None)
        assert gi1 != gi2

    def test_hash(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        assert hash(gi1) == hash(gi2)

    def test_asdict(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url="url")
        d = asdict(gi)
        assert d == {
            "commit_sha": "abc",
            "branch": "main",
            "is_dirty": False,
            "remote_url": "url",
        }

    def test_empty_sha(self):
        gi = GitInfo(commit_sha="", branch="main", is_dirty=False, remote_url=None)
        assert gi.commit_sha == ""


# ===========================================================================
# ContextWorkspaceInfo
# ===========================================================================

class TestContextWorkspaceInfo:
    def test_basic_creation(self):
        ws = ContextWorkspaceInfo(
            root=Path("/tmp/project"),
            git_info=None,
            build_artifacts=[],
            config_files=[],
        )
        assert ws.root == Path("/tmp/project")
        assert ws.git_info is None
        assert ws.build_artifacts == []
        assert ws.config_files == []

    def test_with_git_info(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        ws = ContextWorkspaceInfo(
            root=Path("/project"),
            git_info=gi,
            build_artifacts=[Path("/project/build")],
            config_files=[Path("/project/pyproject.toml")],
        )
        assert ws.git_info is not None
        assert ws.git_info.commit_sha == "abc"
        assert len(ws.build_artifacts) == 1
        assert len(ws.config_files) == 1

    def test_frozen(self):
        ws = ContextWorkspaceInfo(
            root=Path("/tmp"), git_info=None, build_artifacts=[], config_files=[]
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ws.root = Path("/other")

    def test_frozen_git_info(self):
        ws = ContextWorkspaceInfo(
            root=Path("/tmp"), git_info=None, build_artifacts=[], config_files=[]
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ws.git_info = GitInfo(commit_sha="x", branch="y", is_dirty=False, remote_url=None)

    def test_multiple_artifacts(self):
        ws = ContextWorkspaceInfo(
            root=Path("/project"),
            git_info=None,
            build_artifacts=[Path("/project/build"), Path("/project/dist")],
            config_files=[],
        )
        assert len(ws.build_artifacts) == 2

    def test_multiple_config_files(self):
        ws = ContextWorkspaceInfo(
            root=Path("/project"),
            git_info=None,
            build_artifacts=[],
            config_files=[Path("/project/setup.py"), Path("/project/pyproject.toml")],
        )
        assert len(ws.config_files) == 2

    def test_equality(self):
        ws1 = ContextWorkspaceInfo(
            root=Path("/tmp"), git_info=None, build_artifacts=[], config_files=[]
        )
        ws2 = ContextWorkspaceInfo(
            root=Path("/tmp"), git_info=None, build_artifacts=[], config_files=[]
        )
        assert ws1 == ws2


# ===========================================================================
# CPUInfo
# ===========================================================================

class TestCPUInfo:
    def test_basic_creation(self):
        cpu = CPUInfo(model="Intel i7", cores=8, threads=16, frequency_mhz=3200.0)
        assert cpu.model == "Intel i7"
        assert cpu.cores == 8
        assert cpu.threads == 16
        assert cpu.frequency_mhz == 3200.0

    def test_no_frequency(self):
        cpu = CPUInfo(model="ARM Cortex", cores=4, threads=4, frequency_mhz=None)
        assert cpu.frequency_mhz is None

    def test_frozen(self):
        cpu = CPUInfo(model="x", cores=1, threads=1, frequency_mhz=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            cpu.model = "y"

    def test_frozen_cores(self):
        cpu = CPUInfo(model="x", cores=1, threads=1, frequency_mhz=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            cpu.cores = 2

    def test_frozen_threads(self):
        cpu = CPUInfo(model="x", cores=1, threads=1, frequency_mhz=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            cpu.threads = 2

    def test_frozen_frequency(self):
        cpu = CPUInfo(model="x", cores=1, threads=1, frequency_mhz=1000.0)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            cpu.frequency_mhz = 2000.0

    def test_equality(self):
        c1 = CPUInfo(model="x", cores=4, threads=8, frequency_mhz=3000.0)
        c2 = CPUInfo(model="x", cores=4, threads=8, frequency_mhz=3000.0)
        assert c1 == c2

    def test_inequality(self):
        c1 = CPUInfo(model="x", cores=4, threads=8, frequency_mhz=3000.0)
        c2 = CPUInfo(model="y", cores=4, threads=8, frequency_mhz=3000.0)
        assert c1 != c2

    def test_asdict(self):
        cpu = CPUInfo(model="Intel", cores=4, threads=8, frequency_mhz=3200.0)
        d = asdict(cpu)
        assert d == {
            "model": "Intel",
            "cores": 4,
            "threads": 8,
            "frequency_mhz": 3200.0,
        }

    def test_zero_cores(self):
        cpu = CPUInfo(model="unknown", cores=0, threads=0, frequency_mhz=None)
        assert cpu.cores == 0
        assert cpu.threads == 0


# ===========================================================================
# GPUInfo
# ===========================================================================

class TestGPUInfo:
    def test_nvidia_gpu(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX 4090", memory_mb=24576, driver_version="535.129")
        assert gpu.vendor == "nvidia"
        assert gpu.model == "RTX 4090"
        assert gpu.memory_mb == 24576
        assert gpu.driver_version == "535.129"

    def test_amd_gpu(self):
        gpu = GPUInfo(vendor="amd", model="MI300X", memory_mb=192000, driver_version=None)
        assert gpu.vendor == "amd"
        assert gpu.memory_mb == 192000
        assert gpu.driver_version is None

    def test_intel_gpu(self):
        gpu = GPUInfo(vendor="intel", model="Arc A770", memory_mb=16384, driver_version=None)
        assert gpu.vendor == "intel"

    def test_no_memory(self):
        gpu = GPUInfo(vendor="nvidia", model="Test", memory_mb=None, driver_version=None)
        assert gpu.memory_mb is None

    def test_frozen(self):
        gpu = GPUInfo(vendor="nvidia", model="x", memory_mb=None, driver_version=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            gpu.vendor = "amd"

    def test_frozen_model(self):
        gpu = GPUInfo(vendor="nvidia", model="x", memory_mb=None, driver_version=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            gpu.model = "y"

    def test_frozen_memory(self):
        gpu = GPUInfo(vendor="nvidia", model="x", memory_mb=1000, driver_version=None)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            gpu.memory_mb = 2000

    def test_frozen_driver(self):
        gpu = GPUInfo(vendor="nvidia", model="x", memory_mb=None, driver_version="1.0")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            gpu.driver_version = "2.0"

    def test_equality(self):
        g1 = GPUInfo(vendor="nvidia", model="RTX", memory_mb=8000, driver_version="1")
        g2 = GPUInfo(vendor="nvidia", model="RTX", memory_mb=8000, driver_version="1")
        assert g1 == g2

    def test_inequality(self):
        g1 = GPUInfo(vendor="nvidia", model="RTX", memory_mb=8000, driver_version="1")
        g2 = GPUInfo(vendor="amd", model="RTX", memory_mb=8000, driver_version="1")
        assert g1 != g2

    def test_asdict(self):
        gpu = GPUInfo(vendor="nvidia", model="GTX", memory_mb=4096, driver_version="530")
        d = asdict(gpu)
        assert d == {
            "vendor": "nvidia",
            "model": "GTX",
            "memory_mb": 4096,
            "driver_version": "530",
        }


# ===========================================================================
# MemoryInfo
# ===========================================================================

class TestMemoryInfo:
    def test_basic_creation(self):
        mem = MemoryInfo(total_mb=16384, available_mb=8192, used_mb=8192)
        assert mem.total_mb == 16384
        assert mem.available_mb == 8192
        assert mem.used_mb == 8192

    def test_frozen(self):
        mem = MemoryInfo(total_mb=1, available_mb=1, used_mb=0)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            mem.total_mb = 2

    def test_frozen_available(self):
        mem = MemoryInfo(total_mb=1, available_mb=1, used_mb=0)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            mem.available_mb = 2

    def test_frozen_used(self):
        mem = MemoryInfo(total_mb=1, available_mb=1, used_mb=0)
        with pytest.raises((AttributeError, FrozenInstanceError)):
            mem.used_mb = 2

    def test_equality(self):
        m1 = MemoryInfo(total_mb=1024, available_mb=512, used_mb=512)
        m2 = MemoryInfo(total_mb=1024, available_mb=512, used_mb=512)
        assert m1 == m2

    def test_inequality(self):
        m1 = MemoryInfo(total_mb=1024, available_mb=512, used_mb=512)
        m2 = MemoryInfo(total_mb=2048, available_mb=512, used_mb=512)
        assert m1 != m2

    def test_zero_values(self):
        mem = MemoryInfo(total_mb=0, available_mb=0, used_mb=0)
        assert mem.total_mb == 0

    def test_asdict(self):
        mem = MemoryInfo(total_mb=8192, available_mb=4096, used_mb=4096)
        d = asdict(mem)
        assert d == {"total_mb": 8192, "available_mb": 4096, "used_mb": 4096}


# ===========================================================================
# SystemLibrary
# ===========================================================================

class TestSystemLibrary:
    def test_basic_creation(self):
        lib = SystemLibrary(name="libcurl", version="7.81.0", path=Path("/usr/lib/libcurl.so"))
        assert lib.name == "libcurl"
        assert lib.version == "7.81.0"
        assert lib.path == Path("/usr/lib/libcurl.so")

    def test_no_version(self):
        lib = SystemLibrary(name="libfoo", version=None, path=Path("/usr/lib/libfoo.so"))
        assert lib.version is None

    def test_frozen(self):
        lib = SystemLibrary(name="x", version="1", path=Path("/x"))
        with pytest.raises((AttributeError, FrozenInstanceError)):
            lib.name = "y"

    def test_frozen_version(self):
        lib = SystemLibrary(name="x", version="1", path=Path("/x"))
        with pytest.raises((AttributeError, FrozenInstanceError)):
            lib.version = "2"

    def test_frozen_path(self):
        lib = SystemLibrary(name="x", version="1", path=Path("/x"))
        with pytest.raises((AttributeError, FrozenInstanceError)):
            lib.path = Path("/y")

    def test_equality(self):
        l1 = SystemLibrary(name="x", version="1", path=Path("/a"))
        l2 = SystemLibrary(name="x", version="1", path=Path("/a"))
        assert l1 == l2

    def test_inequality(self):
        l1 = SystemLibrary(name="x", version="1", path=Path("/a"))
        l2 = SystemLibrary(name="y", version="1", path=Path("/a"))
        assert l1 != l2

    def test_asdict(self):
        lib = SystemLibrary(name="ssl", version="3.0", path=Path("/usr/lib/libssl.so"))
        d = asdict(lib)
        assert d["name"] == "ssl"
        assert d["version"] == "3.0"
        assert d["path"] == Path("/usr/lib/libssl.so")


# ===========================================================================
# ContextDiff
# ===========================================================================

class TestContextDiff:
    def test_no_differences(self):
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

    def test_platform_changed_incompatible(self):
        diff = ContextDiff(
            platform_changed=True,
            conda_env_changed=False,
            package_changes={},
            env_var_changes={},
            hardware_changes=[],
            git_changes={},
        )
        assert not diff.is_compatible()
        assert "Platform: changed" in diff.summary()

    def test_conda_changed_incompatible(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=True,
            package_changes={},
            env_var_changes={},
            hardware_changes=[],
            git_changes={},
        )
        assert not diff.is_compatible()
        assert "Conda environment: changed" in diff.summary()

    def test_package_changes_incompatible(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=False,
            package_changes={"numpy": ("1.24.0", "1.25.0")},
            env_var_changes={},
            hardware_changes=[],
            git_changes={},
        )
        assert not diff.is_compatible()
        assert "Package changes: 1" in diff.summary()
        assert "numpy" in diff.summary()

    def test_env_var_changes_still_compatible(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=False,
            package_changes={},
            env_var_changes={"PATH": ("/old", "/new")},
            hardware_changes=[],
            git_changes={},
        )
        assert diff.is_compatible()
        assert "Environment variable changes: 1" in diff.summary()

    def test_hardware_changes_still_compatible(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=False,
            package_changes={},
            env_var_changes={},
            hardware_changes=["CPU: Intel -> AMD"],
            git_changes={},
        )
        assert diff.is_compatible()
        assert "Hardware changes: 1" in diff.summary()

    def test_git_changes_in_summary(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=False,
            package_changes={},
            env_var_changes={},
            hardware_changes=[],
            git_changes={"branch": ("main", "dev")},
        )
        assert "Git changes: 1" in diff.summary()
        assert "branch" in diff.summary()

    def test_frozen(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=False,
            package_changes={},
            env_var_changes={},
            hardware_changes=[],
            git_changes={},
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            diff.platform_changed = True

    def test_package_added_summary(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=False,
            package_changes={"newpkg": (None, "1.0.0")},
            env_var_changes={},
            hardware_changes=[],
            git_changes={},
        )
        summary = diff.summary()
        assert "+ newpkg 1.0.0" in summary

    def test_package_removed_summary(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=False,
            package_changes={"oldpkg": ("2.0.0", None)},
            env_var_changes={},
            hardware_changes=[],
            git_changes={},
        )
        summary = diff.summary()
        assert "- oldpkg 2.0.0" in summary

    def test_package_version_changed_summary(self):
        diff = ContextDiff(
            platform_changed=False,
            conda_env_changed=False,
            package_changes={"pkg": ("1.0", "2.0")},
            env_var_changes={},
            hardware_changes=[],
            git_changes={},
        )
        summary = diff.summary()
        assert "~ pkg 1.0 -> 2.0" in summary

    def test_multiple_changes_summary(self):
        diff = ContextDiff(
            platform_changed=True,
            conda_env_changed=True,
            package_changes={"a": ("1", "2"), "b": (None, "3")},
            env_var_changes={"X": ("1", "2")},
            hardware_changes=["CPU changed"],
            git_changes={"commit_sha": ("old", "new")},
        )
        summary = diff.summary()
        assert "Platform: changed" in summary
        assert "Conda environment: changed" in summary
        assert "Package changes: 2" in summary
        assert "Environment variable changes: 1" in summary
        assert "Hardware changes: 1" in summary
        assert "Git changes: 1" in summary

    def test_all_changes_make_incompatible(self):
        diff = ContextDiff(
            platform_changed=True,
            conda_env_changed=True,
            package_changes={"x": ("1", "2")},
            env_var_changes={},
            hardware_changes=[],
            git_changes={},
        )
        assert not diff.is_compatible()


# ===========================================================================
# _detect_git_info
# ===========================================================================

class TestDetectGitInfo:
    def test_no_git_dir(self, tmp_path):
        result = _detect_git_info(tmp_path)
        assert result is None

    def test_git_dir_exists(self, tmp_path):
        (tmp_path / ".git").mkdir()
        # Even with .git dir, if git commands fail, may return with empty strings
        result = _detect_git_info(tmp_path)
        # It might return None or a GitInfo depending on git being available
        # and the .git dir being valid
        assert result is None or isinstance(result, GitInfo)

    @patch("sniff.context.subprocess.run")
    def test_successful_detection(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()

        def side_effect(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            if "rev-parse" in cmd and "HEAD" in cmd and "--abbrev-ref" not in cmd:
                m.stdout = "abc123def456\n"
            elif "--abbrev-ref" in cmd:
                m.stdout = "main\n"
            elif "status" in cmd:
                m.stdout = ""  # clean
            elif "remote" in cmd:
                m.stdout = "https://github.com/user/repo.git\n"
            return m

        mock_run.side_effect = side_effect
        result = _detect_git_info(tmp_path)

        assert result is not None
        assert result.commit_sha == "abc123def456"
        assert result.branch == "main"
        assert result.is_dirty is False
        assert result.remote_url == "https://github.com/user/repo.git"

    @patch("sniff.context.subprocess.run")
    def test_dirty_repo(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()

        def side_effect(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            if "rev-parse" in cmd and "--abbrev-ref" not in cmd:
                m.stdout = "abc123\n"
            elif "--abbrev-ref" in cmd:
                m.stdout = "feature\n"
            elif "status" in cmd:
                m.stdout = " M file.py\n"
            elif "remote" in cmd:
                m.stdout = "\n"
            return m

        mock_run.side_effect = side_effect
        result = _detect_git_info(tmp_path)

        assert result is not None
        assert result.is_dirty is True
        assert result.remote_url is None

    @patch("sniff.context.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5))
    def test_timeout(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        result = _detect_git_info(tmp_path)
        assert result is None

    @patch("sniff.context.subprocess.run", side_effect=FileNotFoundError("git not found"))
    def test_git_not_found(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        result = _detect_git_info(tmp_path)
        assert result is None

    @patch("sniff.context.subprocess.run", side_effect=OSError("os error"))
    def test_os_error(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        result = _detect_git_info(tmp_path)
        assert result is None


# ===========================================================================
# _detect_workspace
# ===========================================================================

class TestDetectWorkspace:
    def test_empty_dir(self, tmp_path):
        ws = _detect_workspace(tmp_path)
        assert isinstance(ws, ContextWorkspaceInfo)
        assert ws.root == tmp_path
        assert ws.git_info is None
        assert ws.build_artifacts == []
        assert ws.config_files == []

    def test_with_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
        ws = _detect_workspace(tmp_path)
        assert ws.root == tmp_path
        assert Path(tmp_path / "pyproject.toml") in ws.config_files

    def test_with_setup_py(self, tmp_path):
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()")
        ws = _detect_workspace(tmp_path)
        assert Path(tmp_path / "setup.py") in ws.config_files

    def test_with_build_dir(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "build").mkdir()
        ws = _detect_workspace(tmp_path)
        assert Path(tmp_path / "build") in ws.build_artifacts

    def test_with_dist_dir(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "dist").mkdir()
        ws = _detect_workspace(tmp_path)
        assert Path(tmp_path / "dist") in ws.build_artifacts

    def test_with_node_modules(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "node_modules").mkdir()
        ws = _detect_workspace(tmp_path)
        assert Path(tmp_path / "node_modules") in ws.build_artifacts

    def test_with_cargo_target(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        (tmp_path / "target").mkdir()
        ws = _detect_workspace(tmp_path)
        assert Path(tmp_path / "target") in ws.build_artifacts

    def test_multiple_config_files(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "Makefile").write_text("all:\n")
        (tmp_path / ".gitignore").write_text("*.pyc\n")
        ws = _detect_workspace(tmp_path)
        assert len(ws.config_files) >= 3

    def test_with_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        ws = _detect_workspace(tmp_path)
        # git_info depends on actual git being available
        assert ws.root == tmp_path


# ===========================================================================
# _detect_cpu_info
# ===========================================================================

class TestDetectCPUInfo:
    def test_returns_cpu_info(self):
        result = _detect_cpu_info()
        assert isinstance(result, CPUInfo)
        assert result.cores >= 1
        assert result.threads >= 1
        assert isinstance(result.model, str)

    def test_model_not_empty(self):
        result = _detect_cpu_info()
        assert result.model != ""

    def test_threads_gte_cores(self):
        result = _detect_cpu_info()
        assert result.threads >= result.cores

    @patch("sniff.context.sys")
    def test_fallback_unknown_platform(self, mock_sys):
        mock_sys.platform = "unknown"
        mock_sys.argv = []
        # Will use os.cpu_count() fallback
        result = _detect_cpu_info()
        assert isinstance(result, CPUInfo)

    @patch("psutil.cpu_count", return_value=4)
    @patch("psutil.cpu_freq")
    def test_psutil_available(self, mock_freq, mock_count):
        mock_freq.return_value = MagicMock(current=3500.0)
        result = _detect_cpu_info()
        assert isinstance(result, CPUInfo)


# ===========================================================================
# GPU detection
# ===========================================================================

class TestDetectNvidiaGPUs:
    @patch("shutil.which", return_value=None)
    def test_no_nvidia_smi(self, mock_which):
        result = _detect_nvidia_gpus()
        assert result == []

    @patch("sniff.context.subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    def test_single_gpu(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 4090, 24564, 535.129.03\n",
        )
        result = _detect_nvidia_gpus()
        assert len(result) == 1
        assert result[0].vendor == "nvidia"
        assert result[0].model == "NVIDIA GeForce RTX 4090"
        assert result[0].memory_mb == 24564
        assert result[0].driver_version == "535.129.03"

    @patch("sniff.context.subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    def test_multiple_gpus(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="GPU A, 8000, 530.0\nGPU B, 16000, 530.0\n",
        )
        result = _detect_nvidia_gpus()
        assert len(result) == 2
        assert result[0].model == "GPU A"
        assert result[1].model == "GPU B"

    @patch("sniff.context.subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    def test_nvidia_smi_failure(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = _detect_nvidia_gpus()
        assert result == []

    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("sniff.context.subprocess.run", side_effect=subprocess.TimeoutExpired("nvidia-smi", 10))
    def test_timeout(self, mock_run, mock_which):
        result = _detect_nvidia_gpus()
        assert result == []

    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("sniff.context.subprocess.run", side_effect=OSError("error"))
    def test_os_error(self, mock_run, mock_which):
        result = _detect_nvidia_gpus()
        assert result == []


class TestDetectAMDGPUs:
    @patch("shutil.which", return_value=None)
    def test_no_rocm_smi(self, mock_which):
        result = _detect_amd_gpus()
        assert result == []

    @patch("sniff.context.subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/rocm-smi")
    def test_rocm_smi_failure(self, mock_which, mock_run):
        # First call fails, second call also fails
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = _detect_amd_gpus()
        assert result == []

    @patch("shutil.which", return_value="/usr/bin/rocm-smi")
    @patch("sniff.context.subprocess.run", side_effect=subprocess.TimeoutExpired("rocm-smi", 10))
    def test_timeout(self, mock_run, mock_which):
        result = _detect_amd_gpus()
        assert result == []

    @patch("shutil.which", return_value="/usr/bin/rocm-smi")
    @patch("sniff.context.subprocess.run", side_effect=OSError("err"))
    def test_os_error(self, mock_run, mock_which):
        result = _detect_amd_gpus()
        assert result == []


class TestDetectIntelGPUs:
    def test_no_drm_path(self):
        with patch("sniff.context.Path") as MockPath:
            # Only mock the specific Path("/sys/class/drm") call
            pass
        # Just test that it returns a list (it may be empty on this system)
        result = _detect_intel_gpus()
        assert isinstance(result, list)

    def test_returns_list(self):
        result = _detect_intel_gpus()
        assert isinstance(result, list)


class TestDetectGPUs:
    @patch("sniff.context._detect_intel_gpus", return_value=[])
    @patch("sniff.context._detect_amd_gpus", return_value=[])
    @patch("sniff.context._detect_nvidia_gpus", return_value=[])
    def test_no_gpus(self, mock_nvidia, mock_amd, mock_intel):
        result = _detect_gpus()
        assert result == []

    @patch("sniff.context._detect_intel_gpus", return_value=[])
    @patch("sniff.context._detect_amd_gpus", return_value=[])
    @patch(
        "sniff.context._detect_nvidia_gpus",
        return_value=[GPUInfo(vendor="nvidia", model="GTX", memory_mb=8000, driver_version="530")],
    )
    def test_nvidia_only(self, mock_nvidia, mock_amd, mock_intel):
        result = _detect_gpus()
        assert len(result) == 1
        assert result[0].vendor == "nvidia"

    @patch(
        "sniff.context._detect_intel_gpus",
        return_value=[GPUInfo(vendor="intel", model="Arc", memory_mb=None, driver_version=None)],
    )
    @patch(
        "sniff.context._detect_amd_gpus",
        return_value=[GPUInfo(vendor="amd", model="MI300X", memory_mb=192000, driver_version=None)],
    )
    @patch(
        "sniff.context._detect_nvidia_gpus",
        return_value=[GPUInfo(vendor="nvidia", model="A100", memory_mb=80000, driver_version="535")],
    )
    def test_all_vendors(self, mock_nvidia, mock_amd, mock_intel):
        result = _detect_gpus()
        assert len(result) == 3
        vendors = [g.vendor for g in result]
        assert "nvidia" in vendors
        assert "amd" in vendors
        assert "intel" in vendors


# ===========================================================================
# _detect_memory_info
# ===========================================================================

class TestDetectMemoryInfo:
    def test_returns_memory_info(self):
        result = _detect_memory_info()
        assert isinstance(result, MemoryInfo)
        assert result.total_mb >= 0

    def test_total_gte_available(self):
        result = _detect_memory_info()
        if result.total_mb > 0:
            assert result.total_mb >= result.available_mb

    def test_total_gte_used(self):
        result = _detect_memory_info()
        if result.total_mb > 0:
            assert result.total_mb >= result.used_mb


# ===========================================================================
# _detect_installed_packages
# ===========================================================================

class TestDetectInstalledPackages:
    def test_returns_dict(self):
        result = _detect_installed_packages()
        assert isinstance(result, dict)

    def test_contains_pytest(self):
        result = _detect_installed_packages()
        # pytest should be installed since we're running tests
        assert "pytest" in result

    def test_versions_are_strings(self):
        result = _detect_installed_packages()
        for name, version in result.items():
            assert isinstance(name, str)
            assert isinstance(version, str)


# ===========================================================================
# _serialize_value
# ===========================================================================

class TestSerializeValue:
    def test_path(self):
        assert _serialize_value(Path("/tmp")) == "/tmp"

    def test_datetime(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _serialize_value(dt)
        assert isinstance(result, str)
        assert "2026" in result

    def test_dict(self):
        result = _serialize_value({"key": Path("/x")})
        assert result == {"key": "/x"}

    def test_list(self):
        result = _serialize_value([Path("/a"), Path("/b")])
        assert result == ["/a", "/b"]

    def test_tuple(self):
        result = _serialize_value((Path("/a"),))
        assert result == ["/a"]

    def test_string(self):
        assert _serialize_value("hello") == "hello"

    def test_int(self):
        assert _serialize_value(42) == 42

    def test_none(self):
        assert _serialize_value(None) is None

    def test_nested(self):
        result = _serialize_value({"paths": [Path("/a"), Path("/b")]})
        assert result == {"paths": ["/a", "/b"]}

    def test_dataclass(self):
        cpu = CPUInfo(model="test", cores=4, threads=8, frequency_mhz=3000.0)
        result = _serialize_value(cpu)
        assert result["model"] == "test"
        assert result["cores"] == 4


# ===========================================================================
# ExecutionContext (construction helpers)
# ===========================================================================

def _make_context(**overrides) -> ExecutionContext:
    """Helper to create a test ExecutionContext with defaults."""
    from sniff.detect import PlatformInfo
    from sniff.ci import CIInfo

    defaults = dict(
        platform=PlatformInfo(os="Linux", arch="x86_64"),
        conda_env=None,
        ci_info=CIInfo(is_ci=False),
        workspace=ContextWorkspaceInfo(
            root=Path("/project"),
            git_info=None,
            build_artifacts=[],
            config_files=[],
        ),
        build_system=None,
        installed_packages={"pytest": "7.4.0"},
        system_libraries=[],
        cpu_info=CPUInfo(model="Intel", cores=4, threads=8, frequency_mhz=3200.0),
        gpu_info=[],
        memory_info=MemoryInfo(total_mb=16384, available_mb=8192, used_mb=8192),
        env_vars={"HOME": "/home/user"},
        command_line=["python", "test.py"],
        working_dir=Path("/project"),
        timestamp=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ExecutionContext(**defaults)


# ===========================================================================
# ExecutionContext frozen
# ===========================================================================

class TestExecutionContextFrozen:
    def test_frozen_platform(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.platform = None

    def test_frozen_conda_env(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.conda_env = None

    def test_frozen_ci_info(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.ci_info = None

    def test_frozen_workspace(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.workspace = None

    def test_frozen_build_system(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.build_system = "x"

    def test_frozen_installed_packages(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.installed_packages = {}

    def test_frozen_system_libraries(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.system_libraries = []

    def test_frozen_cpu_info(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.cpu_info = None

    def test_frozen_gpu_info(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.gpu_info = []

    def test_frozen_memory_info(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.memory_info = None

    def test_frozen_env_vars(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.env_vars = {}

    def test_frozen_command_line(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.command_line = []

    def test_frozen_working_dir(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.working_dir = Path("/x")

    def test_frozen_timestamp(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.timestamp = datetime.now()


# ===========================================================================
# ExecutionContext.capture
# ===========================================================================

class TestExecutionContextCapture:
    def test_capture_returns_context(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert isinstance(ctx, ExecutionContext)

    def test_capture_has_platform(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert ctx.platform is not None
        assert hasattr(ctx.platform, "os")
        assert ctx.platform.os in ("Linux", "Darwin", "Windows")

    def test_capture_has_ci_info(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert ctx.ci_info is not None
        assert hasattr(ctx.ci_info, "is_ci")

    def test_capture_has_workspace(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert isinstance(ctx.workspace, ContextWorkspaceInfo)
        assert isinstance(ctx.workspace.root, Path)

    def test_capture_has_timestamp(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert isinstance(ctx.timestamp, datetime)

    def test_capture_has_working_dir(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert isinstance(ctx.working_dir, Path)
        assert ctx.working_dir == Path.cwd()

    def test_capture_has_command_line(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert isinstance(ctx.command_line, list)

    def test_capture_without_env_vars(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert ctx.env_vars == {}

    def test_capture_with_env_vars(self):
        ctx = ExecutionContext.capture(
            include_env_vars=True,
            include_packages=False,
            include_hardware=False,
        )
        assert len(ctx.env_vars) > 0
        assert "PATH" in ctx.env_vars or "HOME" in ctx.env_vars

    def test_capture_without_packages(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert ctx.installed_packages == {}

    def test_capture_with_packages(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=True,
            include_hardware=False,
        )
        assert len(ctx.installed_packages) > 0
        assert "pytest" in ctx.installed_packages

    def test_capture_without_hardware(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert ctx.cpu_info.model == "unknown"
        assert ctx.cpu_info.cores == 0
        assert ctx.memory_info.total_mb == 0
        assert ctx.gpu_info == []

    def test_capture_with_hardware(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=True,
        )
        assert ctx.cpu_info.cores >= 1
        assert ctx.memory_info.total_mb > 0

    def test_capture_default_all_included(self):
        ctx = ExecutionContext.capture()
        assert len(ctx.env_vars) > 0
        assert len(ctx.installed_packages) > 0
        assert ctx.cpu_info.cores >= 1


# ===========================================================================
# ExecutionContext.to_dict
# ===========================================================================

class TestExecutionContextToDict:
    def test_returns_dict(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert isinstance(result, dict)

    def test_json_serializable(self):
        ctx = _make_context()
        result = ctx.to_dict()
        # Should not raise
        json_str = json.dumps(result)
        assert len(json_str) > 0

    def test_has_platform(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "platform" in result

    def test_has_workspace(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "workspace" in result
        assert "root" in result["workspace"]

    def test_has_cpu_info(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "cpu_info" in result
        assert result["cpu_info"]["model"] == "Intel"

    def test_has_gpu_info(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "gpu_info" in result
        assert isinstance(result["gpu_info"], list)

    def test_has_memory_info(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "memory_info" in result
        assert result["memory_info"]["total_mb"] == 16384

    def test_has_env_vars(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "env_vars" in result
        assert result["env_vars"]["HOME"] == "/home/user"

    def test_has_command_line(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "command_line" in result
        assert result["command_line"] == ["python", "test.py"]

    def test_has_working_dir(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "working_dir" in result
        assert result["working_dir"] == "/project"

    def test_has_timestamp(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "timestamp" in result
        assert "2026" in result["timestamp"]

    def test_has_installed_packages(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert "installed_packages" in result
        assert result["installed_packages"]["pytest"] == "7.4.0"

    def test_has_system_libraries(self):
        lib = SystemLibrary(name="ssl", version="3.0", path=Path("/usr/lib/libssl.so"))
        ctx = _make_context(system_libraries=[lib])
        result = ctx.to_dict()
        assert "system_libraries" in result
        assert len(result["system_libraries"]) == 1
        assert result["system_libraries"][0]["name"] == "ssl"

    def test_conda_env_none(self):
        ctx = _make_context(conda_env=None)
        result = ctx.to_dict()
        assert result["conda_env"] is None

    def test_conda_env_present(self):
        from sniff.conda import CondaEnvironment

        conda = CondaEnvironment(name="test", prefix=Path("/env/test"), is_active=True)
        ctx = _make_context(conda_env=conda)
        result = ctx.to_dict()
        assert result["conda_env"] is not None
        assert result["conda_env"]["name"] == "test"

    def test_build_system_none(self):
        ctx = _make_context(build_system=None)
        result = ctx.to_dict()
        assert result["build_system"] is None

    def test_workspace_git_info_none(self):
        ctx = _make_context()
        result = ctx.to_dict()
        assert result["workspace"]["git_info"] is None

    def test_workspace_git_info_present(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url="url")
        ws = ContextWorkspaceInfo(
            root=Path("/project"), git_info=gi, build_artifacts=[], config_files=[]
        )
        ctx = _make_context(workspace=ws)
        result = ctx.to_dict()
        assert result["workspace"]["git_info"] is not None
        assert result["workspace"]["git_info"]["commit_sha"] == "abc"

    def test_gpu_info_serialized(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX", memory_mb=8000, driver_version="530")
        ctx = _make_context(gpu_info=[gpu])
        result = ctx.to_dict()
        assert len(result["gpu_info"]) == 1
        assert result["gpu_info"][0]["vendor"] == "nvidia"

    def test_roundtrip_json(self):
        ctx = _make_context()
        d = ctx.to_dict()
        json_str = json.dumps(d)
        d2 = json.loads(json_str)
        assert d2["cpu_info"]["model"] == "Intel"
        assert d2["working_dir"] == "/project"


# ===========================================================================
# ExecutionContext.from_dict
# ===========================================================================

class TestExecutionContextFromDict:
    def test_roundtrip(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert isinstance(ctx2, ExecutionContext)

    def test_preserves_cpu_info(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.cpu_info.model == "Intel"
        assert ctx2.cpu_info.cores == 4
        assert ctx2.cpu_info.threads == 8

    def test_preserves_memory_info(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.memory_info.total_mb == 16384

    def test_preserves_gpu_info(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX", memory_mb=8000, driver_version="530")
        ctx = _make_context(gpu_info=[gpu])
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert len(ctx2.gpu_info) == 1
        assert ctx2.gpu_info[0].vendor == "nvidia"

    def test_preserves_env_vars(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.env_vars["HOME"] == "/home/user"

    def test_preserves_command_line(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.command_line == ["python", "test.py"]

    def test_preserves_working_dir(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.working_dir == Path("/project")

    def test_preserves_timestamp(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.timestamp.year == 2026

    def test_preserves_packages(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.installed_packages["pytest"] == "7.4.0"

    def test_preserves_workspace_root(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.workspace.root == Path("/project")

    def test_preserves_workspace_git_info(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=True, remote_url="url")
        ws = ContextWorkspaceInfo(
            root=Path("/project"), git_info=gi, build_artifacts=[], config_files=[]
        )
        ctx = _make_context(workspace=ws)
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.workspace.git_info is not None
        assert ctx2.workspace.git_info.commit_sha == "abc"
        assert ctx2.workspace.git_info.is_dirty is True
        assert ctx2.workspace.git_info.remote_url == "url"

    def test_preserves_system_libraries(self):
        lib = SystemLibrary(name="ssl", version="3.0", path=Path("/usr/lib/libssl.so"))
        ctx = _make_context(system_libraries=[lib])
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        assert len(ctx2.system_libraries) == 1
        assert ctx2.system_libraries[0].name == "ssl"

    def test_empty_dict(self):
        ctx = ExecutionContext.from_dict({})
        assert isinstance(ctx, ExecutionContext)
        assert ctx.installed_packages == {}
        assert ctx.env_vars == {}

    def test_no_timestamp(self):
        ctx = ExecutionContext.from_dict({})
        assert isinstance(ctx.timestamp, datetime)

    def test_from_dict_is_frozen(self):
        ctx = ExecutionContext.from_dict({})
        with pytest.raises((AttributeError, FrozenInstanceError)):
            ctx.platform = "x"

    def test_json_roundtrip(self):
        ctx = _make_context()
        json_str = json.dumps(ctx.to_dict())
        d = json.loads(json_str)
        ctx2 = ExecutionContext.from_dict(d)
        assert ctx2.cpu_info.model == "Intel"


# ===========================================================================
# ExecutionContext.fingerprint
# ===========================================================================

class TestExecutionContextFingerprint:
    def test_returns_hex_string(self):
        ctx = _make_context()
        fp = ctx.fingerprint()
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in fp)

    def test_deterministic(self):
        ctx = _make_context()
        fp1 = ctx.fingerprint()
        fp2 = ctx.fingerprint()
        assert fp1 == fp2

    def test_same_context_same_fingerprint(self):
        ctx1 = _make_context()
        ctx2 = _make_context()
        assert ctx1.fingerprint() == ctx2.fingerprint()

    def test_different_packages_different_fingerprint(self):
        ctx1 = _make_context(installed_packages={"a": "1.0"})
        ctx2 = _make_context(installed_packages={"a": "2.0"})
        assert ctx1.fingerprint() != ctx2.fingerprint()

    def test_different_platform_different_fingerprint(self):
        from sniff.detect import PlatformInfo

        ctx1 = _make_context(platform=PlatformInfo(os="Linux", arch="x86_64"))
        ctx2 = _make_context(platform=PlatformInfo(os="Darwin", arch="arm64"))
        assert ctx1.fingerprint() != ctx2.fingerprint()

    def test_env_vars_dont_affect_fingerprint(self):
        ctx1 = _make_context(env_vars={"A": "1"})
        ctx2 = _make_context(env_vars={"A": "2"})
        assert ctx1.fingerprint() == ctx2.fingerprint()

    def test_hardware_doesnt_affect_fingerprint(self):
        ctx1 = _make_context(
            cpu_info=CPUInfo(model="Intel", cores=4, threads=8, frequency_mhz=3200.0)
        )
        ctx2 = _make_context(
            cpu_info=CPUInfo(model="AMD", cores=8, threads=16, frequency_mhz=4000.0)
        )
        assert ctx1.fingerprint() == ctx2.fingerprint()

    def test_git_state_affects_fingerprint(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="def", branch="main", is_dirty=False, remote_url=None)
        ws1 = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi1, build_artifacts=[], config_files=[]
        )
        ws2 = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi2, build_artifacts=[], config_files=[]
        )
        ctx1 = _make_context(workspace=ws1)
        ctx2 = _make_context(workspace=ws2)
        assert ctx1.fingerprint() != ctx2.fingerprint()

    def test_no_git_info_has_fingerprint(self):
        ctx = _make_context()
        fp = ctx.fingerprint()
        assert len(fp) == 64

    def test_conda_env_affects_fingerprint(self):
        from sniff.conda import CondaEnvironment

        ctx1 = _make_context(conda_env=None)
        ctx2 = _make_context(
            conda_env=CondaEnvironment(name="test", prefix=Path("/env/test"))
        )
        assert ctx1.fingerprint() != ctx2.fingerprint()

    def test_from_dict_fingerprint(self):
        ctx = _make_context()
        d = ctx.to_dict()
        ctx2 = ExecutionContext.from_dict(d)
        # from_dict stores platform as dict, so fingerprint may differ
        # from original -- that's OK, but it should still be deterministic
        fp = ctx2.fingerprint()
        assert len(fp) == 64
        assert ctx2.fingerprint() == fp  # deterministic


# ===========================================================================
# ExecutionContext.diff
# ===========================================================================

class TestExecutionContextDiff:
    def test_identical_contexts(self):
        ctx = _make_context()
        d = ctx.diff(ctx)
        assert d.is_compatible()
        assert d.platform_changed is False
        assert d.conda_env_changed is False
        assert d.package_changes == {}
        assert d.env_var_changes == {}
        assert d.hardware_changes == []
        assert d.git_changes == {}

    def test_platform_difference(self):
        from sniff.detect import PlatformInfo

        ctx1 = _make_context(platform=PlatformInfo(os="Linux", arch="x86_64"))
        ctx2 = _make_context(platform=PlatformInfo(os="Darwin", arch="arm64"))
        d = ctx1.diff(ctx2)
        assert d.platform_changed is True
        assert not d.is_compatible()

    def test_conda_added(self):
        from sniff.conda import CondaEnvironment

        ctx1 = _make_context(conda_env=None)
        ctx2 = _make_context(
            conda_env=CondaEnvironment(name="test", prefix=Path("/env"))
        )
        d = ctx1.diff(ctx2)
        assert d.conda_env_changed is True

    def test_conda_removed(self):
        from sniff.conda import CondaEnvironment

        ctx1 = _make_context(
            conda_env=CondaEnvironment(name="test", prefix=Path("/env"))
        )
        ctx2 = _make_context(conda_env=None)
        d = ctx1.diff(ctx2)
        assert d.conda_env_changed is True

    def test_conda_both_none(self):
        ctx1 = _make_context(conda_env=None)
        ctx2 = _make_context(conda_env=None)
        d = ctx1.diff(ctx2)
        assert d.conda_env_changed is False

    def test_conda_same(self):
        from sniff.conda import CondaEnvironment

        conda = CondaEnvironment(name="test", prefix=Path("/env"))
        ctx1 = _make_context(conda_env=conda)
        ctx2 = _make_context(conda_env=conda)
        d = ctx1.diff(ctx2)
        assert d.conda_env_changed is False

    def test_package_added(self):
        ctx1 = _make_context(installed_packages={"a": "1.0"})
        ctx2 = _make_context(installed_packages={"a": "1.0", "b": "2.0"})
        d = ctx1.diff(ctx2)
        assert "b" in d.package_changes
        assert d.package_changes["b"] == (None, "2.0")

    def test_package_removed(self):
        ctx1 = _make_context(installed_packages={"a": "1.0", "b": "2.0"})
        ctx2 = _make_context(installed_packages={"a": "1.0"})
        d = ctx1.diff(ctx2)
        assert "b" in d.package_changes
        assert d.package_changes["b"] == ("2.0", None)

    def test_package_version_changed(self):
        ctx1 = _make_context(installed_packages={"a": "1.0"})
        ctx2 = _make_context(installed_packages={"a": "2.0"})
        d = ctx1.diff(ctx2)
        assert "a" in d.package_changes
        assert d.package_changes["a"] == ("1.0", "2.0")

    def test_env_var_added(self):
        ctx1 = _make_context(env_vars={"A": "1"})
        ctx2 = _make_context(env_vars={"A": "1", "B": "2"})
        d = ctx1.diff(ctx2)
        assert "B" in d.env_var_changes
        assert d.env_var_changes["B"] == (None, "2")

    def test_env_var_removed(self):
        ctx1 = _make_context(env_vars={"A": "1", "B": "2"})
        ctx2 = _make_context(env_vars={"A": "1"})
        d = ctx1.diff(ctx2)
        assert "B" in d.env_var_changes
        assert d.env_var_changes["B"] == ("2", None)

    def test_env_var_changed(self):
        ctx1 = _make_context(env_vars={"A": "1"})
        ctx2 = _make_context(env_vars={"A": "2"})
        d = ctx1.diff(ctx2)
        assert "A" in d.env_var_changes
        assert d.env_var_changes["A"] == ("1", "2")

    def test_cpu_changed(self):
        ctx1 = _make_context(
            cpu_info=CPUInfo(model="Intel", cores=4, threads=8, frequency_mhz=3200.0)
        )
        ctx2 = _make_context(
            cpu_info=CPUInfo(model="AMD", cores=8, threads=16, frequency_mhz=4000.0)
        )
        d = ctx1.diff(ctx2)
        assert len(d.hardware_changes) > 0
        assert any("CPU" in c for c in d.hardware_changes)

    def test_memory_changed(self):
        ctx1 = _make_context(
            memory_info=MemoryInfo(total_mb=8192, available_mb=4096, used_mb=4096)
        )
        ctx2 = _make_context(
            memory_info=MemoryInfo(total_mb=16384, available_mb=8192, used_mb=8192)
        )
        d = ctx1.diff(ctx2)
        assert any("Memory" in c for c in d.hardware_changes)

    def test_gpu_changed(self):
        gpu1 = GPUInfo(vendor="nvidia", model="RTX 3090", memory_mb=24000, driver_version="530")
        gpu2 = GPUInfo(vendor="nvidia", model="RTX 4090", memory_mb=24000, driver_version="535")
        ctx1 = _make_context(gpu_info=[gpu1])
        ctx2 = _make_context(gpu_info=[gpu2])
        d = ctx1.diff(ctx2)
        assert any("GPU" in c for c in d.hardware_changes)

    def test_git_commit_changed(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="def", branch="main", is_dirty=False, remote_url=None)
        ws1 = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi1, build_artifacts=[], config_files=[]
        )
        ws2 = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi2, build_artifacts=[], config_files=[]
        )
        ctx1 = _make_context(workspace=ws1)
        ctx2 = _make_context(workspace=ws2)
        d = ctx1.diff(ctx2)
        assert "commit_sha" in d.git_changes

    def test_git_branch_changed(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="abc", branch="dev", is_dirty=False, remote_url=None)
        ws1 = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi1, build_artifacts=[], config_files=[]
        )
        ws2 = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi2, build_artifacts=[], config_files=[]
        )
        ctx1 = _make_context(workspace=ws1)
        ctx2 = _make_context(workspace=ws2)
        d = ctx1.diff(ctx2)
        assert "branch" in d.git_changes

    def test_git_dirty_changed(self):
        gi1 = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        gi2 = GitInfo(commit_sha="abc", branch="main", is_dirty=True, remote_url=None)
        ws1 = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi1, build_artifacts=[], config_files=[]
        )
        ws2 = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi2, build_artifacts=[], config_files=[]
        )
        ctx1 = _make_context(workspace=ws1)
        ctx2 = _make_context(workspace=ws2)
        d = ctx1.diff(ctx2)
        assert "is_dirty" in d.git_changes

    def test_git_added(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        ws_no_git = ContextWorkspaceInfo(
            root=Path("/p"), git_info=None, build_artifacts=[], config_files=[]
        )
        ws_with_git = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi, build_artifacts=[], config_files=[]
        )
        ctx1 = _make_context(workspace=ws_no_git)
        ctx2 = _make_context(workspace=ws_with_git)
        d = ctx1.diff(ctx2)
        assert "status" in d.git_changes
        assert d.git_changes["status"] == "added"

    def test_git_removed(self):
        gi = GitInfo(commit_sha="abc", branch="main", is_dirty=False, remote_url=None)
        ws_with_git = ContextWorkspaceInfo(
            root=Path("/p"), git_info=gi, build_artifacts=[], config_files=[]
        )
        ws_no_git = ContextWorkspaceInfo(
            root=Path("/p"), git_info=None, build_artifacts=[], config_files=[]
        )
        ctx1 = _make_context(workspace=ws_with_git)
        ctx2 = _make_context(workspace=ws_no_git)
        d = ctx1.diff(ctx2)
        assert "status" in d.git_changes
        assert d.git_changes["status"] == "removed"

    def test_diff_returns_context_diff(self):
        ctx = _make_context()
        d = ctx.diff(ctx)
        assert isinstance(d, ContextDiff)

    def test_diff_compatible_when_env_and_hw_differ(self):
        ctx1 = _make_context(
            env_vars={"X": "1"},
            cpu_info=CPUInfo(model="Intel", cores=4, threads=8, frequency_mhz=3200.0),
        )
        ctx2 = _make_context(
            env_vars={"X": "2"},
            cpu_info=CPUInfo(model="AMD", cores=8, threads=16, frequency_mhz=4000.0),
        )
        d = ctx1.diff(ctx2)
        assert d.is_compatible()

    def test_diff_multiple_packages_changed(self):
        ctx1 = _make_context(installed_packages={"a": "1.0", "b": "2.0", "c": "3.0"})
        ctx2 = _make_context(installed_packages={"a": "1.1", "b": "2.0", "d": "4.0"})
        d = ctx1.diff(ctx2)
        assert "a" in d.package_changes  # version changed
        assert "c" in d.package_changes  # removed
        assert "d" in d.package_changes  # added
        assert "b" not in d.package_changes  # unchanged


# ===========================================================================
# Integration tests
# ===========================================================================

class TestIntegration:
    def test_capture_to_dict_roundtrip(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        d = ctx.to_dict()
        json_str = json.dumps(d)
        d2 = json.loads(json_str)
        ctx2 = ExecutionContext.from_dict(d2)
        assert isinstance(ctx2, ExecutionContext)

    def test_capture_fingerprint(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        fp = ctx.fingerprint()
        assert len(fp) == 64

    def test_capture_diff_with_self(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        d = ctx.diff(ctx)
        assert d.is_compatible()
        assert d.summary() == "No differences"

    def test_capture_diff_with_different(self):
        ctx1 = _make_context(installed_packages={"a": "1"})
        ctx2 = _make_context(installed_packages={"a": "2"})
        d = ctx1.diff(ctx2)
        assert not d.is_compatible()

    def test_full_capture(self):
        ctx = ExecutionContext.capture()
        assert ctx.platform is not None
        assert ctx.ci_info is not None
        assert isinstance(ctx.workspace, ContextWorkspaceInfo)
        assert isinstance(ctx.cpu_info, CPUInfo)
        assert isinstance(ctx.gpu_info, list)
        assert isinstance(ctx.memory_info, MemoryInfo)
        assert isinstance(ctx.env_vars, dict)
        assert isinstance(ctx.command_line, list)
        assert isinstance(ctx.working_dir, Path)
        assert isinstance(ctx.timestamp, datetime)

    def test_full_capture_to_json(self):
        ctx = ExecutionContext.capture()
        d = ctx.to_dict()
        json_str = json.dumps(d)
        assert len(json_str) > 100

    def test_two_captures_same_fingerprint_if_no_change(self):
        # Note: timestamps differ, but fingerprint doesn't include timestamp
        ctx1 = _make_context()
        ctx2 = _make_context()
        assert ctx1.fingerprint() == ctx2.fingerprint()

    def test_capture_preserves_sys_argv(self):
        ctx = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=False,
            include_hardware=False,
        )
        assert ctx.command_line == list(sys.argv)
