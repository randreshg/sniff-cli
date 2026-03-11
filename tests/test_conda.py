"""Tests for conda environment detection."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sniff.conda import (
    COMMON_INSTALL_PATHS,
    CondaDetector,
    CondaEnvironment,
    CondaValidation,
)


# ---------------------------------------------------------------------------
# COMMON_INSTALL_PATHS constant
# ---------------------------------------------------------------------------

class TestCommonInstallPaths:
    def test_is_tuple(self):
        assert isinstance(COMMON_INSTALL_PATHS, tuple)

    def test_contains_known_distros(self):
        assert "miniforge3" in COMMON_INSTALL_PATHS
        assert "mambaforge" in COMMON_INSTALL_PATHS
        assert "miniconda3" in COMMON_INSTALL_PATHS
        assert "anaconda3" in COMMON_INSTALL_PATHS


# ---------------------------------------------------------------------------
# CondaEnvironment dataclass
# ---------------------------------------------------------------------------

class TestCondaEnvironment:
    def test_basic_creation(self):
        env = CondaEnvironment(name="test", prefix=Path("/tmp/test"))
        assert env.name == "test"
        assert env.prefix == Path("/tmp/test")
        assert env.is_active is False
        assert env.python_version is None

    def test_active_with_python(self):
        env = CondaEnvironment(
            name="myenv",
            prefix=Path("/home/user/miniconda3/envs/myenv"),
            is_active=True,
            python_version="3.11.5",
        )
        assert env.is_active is True
        assert env.python_version == "3.11.5"

    def test_frozen(self):
        env = CondaEnvironment(name="test", prefix=Path("/tmp/test"))
        with pytest.raises(AttributeError):
            env.name = "other"


# ---------------------------------------------------------------------------
# CondaValidation dataclass
# ---------------------------------------------------------------------------

class TestCondaValidation:
    def test_ok_when_found_no_missing(self):
        v = CondaValidation(env_name="myenv", found=True, prefix=Path("/tmp/myenv"))
        assert v.ok is True

    def test_not_ok_when_not_found(self):
        v = CondaValidation(
            env_name="myenv", found=False, errors=("Environment 'myenv' not found",)
        )
        assert v.ok is False

    def test_not_ok_when_packages_missing(self):
        v = CondaValidation(
            env_name="myenv",
            found=True,
            prefix=Path("/tmp/myenv"),
            missing_packages=("numpy",),
        )
        assert v.ok is False
        assert "numpy" in v.missing_packages

    def test_not_ok_when_errors(self):
        v = CondaValidation(
            env_name="myenv", found=True, prefix=Path("/tmp/myenv"), errors=("bad",)
        )
        assert v.ok is False

    def test_frozen(self):
        v = CondaValidation(env_name="test", found=True)
        with pytest.raises(AttributeError):
            v.found = False


# ---------------------------------------------------------------------------
# CondaDetector.find_active
# ---------------------------------------------------------------------------

class TestFindActive:
    def test_returns_none_without_conda_prefix(self, monkeypatch):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()
        assert detector.find_active() is None

    def test_returns_env_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("CONDA_PREFIX", "/home/user/miniconda3/envs/test")
        monkeypatch.setenv("CONDA_DEFAULT_ENV", "test")
        detector = CondaDetector()
        with patch.object(detector, "_get_python_version", return_value=None):
            env = detector.find_active()
        assert env is not None
        assert env.name == "test"
        assert env.prefix == Path("/home/user/miniconda3/envs/test")
        assert env.is_active is True

    def test_uses_prefix_name_when_no_default_env(self, monkeypatch):
        monkeypatch.setenv("CONDA_PREFIX", "/home/user/miniconda3/envs/myenv")
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()
        with patch.object(detector, "_get_python_version", return_value=None):
            env = detector.find_active()
        assert env is not None
        assert env.name == "myenv"


# ---------------------------------------------------------------------------
# CondaDetector.find_prefix
# ---------------------------------------------------------------------------

class TestFindPrefix:
    def test_returns_active_prefix_when_name_matches(self, monkeypatch):
        monkeypatch.setenv("CONDA_PREFIX", "/home/user/miniconda3/envs/apxm")
        monkeypatch.setenv("CONDA_DEFAULT_ENV", "apxm")
        detector = CondaDetector()
        with patch.object(detector, "_get_python_version", return_value=None):
            result = detector.find_prefix("apxm")
        assert result == Path("/home/user/miniconda3/envs/apxm")

    def test_skips_active_when_name_differs(self, monkeypatch):
        monkeypatch.setenv("CONDA_PREFIX", "/home/user/miniconda3/envs/other")
        monkeypatch.setenv("CONDA_DEFAULT_ENV", "other")
        detector = CondaDetector()
        with patch.object(detector, "_get_python_version", return_value=None), \
             patch.object(detector, "find_environment", return_value=None):
            result = detector.find_prefix("apxm", probe_common=False)
        assert result is None

    def test_falls_back_to_find_environment(self, monkeypatch):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        fake_env = CondaEnvironment(name="apxm", prefix=Path("/conda/envs/apxm"))
        detector = CondaDetector()
        with patch.object(detector, "find_environment", return_value=fake_env):
            result = detector.find_prefix("apxm")
        assert result == Path("/conda/envs/apxm")

    def test_probes_common_paths(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()

        # Create a fake miniforge3 env dir
        fake_env = tmp_path / "miniforge3" / "envs" / "myenv"
        fake_env.mkdir(parents=True)

        with patch.object(detector, "find_environment", return_value=None), \
             patch.object(
                 CondaDetector,
                 "_common_prefix_candidates",
                 return_value=[fake_env],
             ):
            result = detector.find_prefix("myenv")
        assert result == fake_env

    def test_probe_common_false_skips_filesystem(self, monkeypatch):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()
        with patch.object(detector, "find_environment", return_value=None):
            result = detector.find_prefix("apxm", probe_common=False)
        assert result is None

    def test_returns_none_when_nothing_found(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()
        # Use a path inside tmp_path that does not exist
        bogus = tmp_path / "does_not_exist" / "envs" / "apxm"
        with patch.object(detector, "find_environment", return_value=None), \
             patch.object(
                 CondaDetector,
                 "_common_prefix_candidates",
                 return_value=[bogus],
             ):
            result = detector.find_prefix("apxm")
        assert result is None


# ---------------------------------------------------------------------------
# CondaDetector._common_prefix_candidates
# ---------------------------------------------------------------------------

class TestCommonPrefixCandidates:
    def test_generates_expected_paths(self):
        candidates = CondaDetector._common_prefix_candidates("myenv")
        home = Path.home()

        expected = [
            home / "miniforge3" / "envs" / "myenv",
            home / "mambaforge" / "envs" / "myenv",
            home / "miniconda3" / "envs" / "myenv",
            home / "anaconda3" / "envs" / "myenv",
            Path("/opt/conda/envs/myenv"),
        ]
        assert candidates == expected

    def test_includes_opt_conda(self):
        candidates = CondaDetector._common_prefix_candidates("test")
        assert Path("/opt/conda/envs/test") in candidates


# ---------------------------------------------------------------------------
# CondaDetector.validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_not_found(self, monkeypatch):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()
        with patch.object(detector, "find_prefix", return_value=None):
            result = detector.validate("noenv")
        assert result.found is False
        assert not result.ok
        assert "noenv" in result.errors[0]

    def test_found_no_required_packages(self, monkeypatch):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()
        with patch.object(detector, "find_prefix", return_value=Path("/envs/myenv")):
            result = detector.validate("myenv")
        assert result.found is True
        assert result.ok is True
        assert result.prefix == Path("/envs/myenv")
        assert result.missing_packages == ()

    def test_found_all_packages_present(self, monkeypatch):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()
        with patch.object(detector, "find_prefix", return_value=Path("/envs/myenv")), \
             patch.object(detector, "_check_packages", return_value=[]):
            result = detector.validate("myenv", required_packages=["numpy", "scipy"])
        assert result.ok is True
        assert result.missing_packages == ()

    def test_found_missing_packages(self, monkeypatch):
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        detector = CondaDetector()
        with patch.object(detector, "find_prefix", return_value=Path("/envs/myenv")), \
             patch.object(detector, "_check_packages", return_value=["scipy"]):
            result = detector.validate("myenv", required_packages=["numpy", "scipy"])
        assert not result.ok
        assert "scipy" in result.missing_packages

    def test_is_active_when_prefix_matches(self, monkeypatch):
        monkeypatch.setenv("CONDA_PREFIX", "/envs/myenv")
        monkeypatch.setenv("CONDA_DEFAULT_ENV", "myenv")
        detector = CondaDetector()
        with patch.object(detector, "find_prefix", return_value=Path("/envs/myenv")), \
             patch.object(detector, "_get_python_version", return_value=None):
            result = detector.validate("myenv")
        assert result.is_active is True

    def test_not_active_when_prefix_differs(self, monkeypatch):
        monkeypatch.setenv("CONDA_PREFIX", "/envs/other")
        monkeypatch.setenv("CONDA_DEFAULT_ENV", "other")
        detector = CondaDetector()
        with patch.object(detector, "find_prefix", return_value=Path("/envs/myenv")), \
             patch.object(detector, "_get_python_version", return_value=None):
            result = detector.validate("myenv")
        assert result.is_active is False


# ---------------------------------------------------------------------------
# CondaDetector._check_packages
# ---------------------------------------------------------------------------

class TestCheckPackages:
    def test_all_installed(self):
        detector = CondaDetector()
        installed_json = json.dumps([
            {"name": "numpy", "version": "1.26"},
            {"name": "scipy", "version": "1.12"},
        ])
        mock_result = MagicMock(returncode=0, stdout=installed_json)
        with patch("shutil.which", return_value="/usr/bin/conda"), \
             patch("subprocess.run", return_value=mock_result):
            missing = detector._check_packages(Path("/envs/test"), ["numpy", "scipy"])
        assert missing == []

    def test_some_missing(self):
        detector = CondaDetector()
        installed_json = json.dumps([
            {"name": "numpy", "version": "1.26"},
        ])
        mock_result = MagicMock(returncode=0, stdout=installed_json)
        with patch("shutil.which", return_value="/usr/bin/conda"), \
             patch("subprocess.run", return_value=mock_result):
            missing = detector._check_packages(
                Path("/envs/test"), ["numpy", "scipy", "pandas"]
            )
        assert missing == ["scipy", "pandas"]

    def test_no_conda_returns_all(self):
        detector = CondaDetector()
        with patch("shutil.which", return_value=None):
            missing = detector._check_packages(Path("/envs/test"), ["numpy"])
        assert missing == ["numpy"]

    def test_subprocess_failure_returns_all(self):
        detector = CondaDetector()
        mock_result = MagicMock(returncode=1, stdout="")
        with patch("shutil.which", return_value="/usr/bin/conda"), \
             patch("subprocess.run", return_value=mock_result):
            missing = detector._check_packages(Path("/envs/test"), ["a", "b"])
        assert missing == ["a", "b"]

    def test_json_error_returns_all(self):
        detector = CondaDetector()
        mock_result = MagicMock(returncode=0, stdout="not json")
        with patch("shutil.which", return_value="/usr/bin/conda"), \
             patch("subprocess.run", return_value=mock_result):
            missing = detector._check_packages(Path("/envs/test"), ["pkg"])
        assert missing == ["pkg"]

    def test_timeout_returns_all(self):
        detector = CondaDetector()
        with patch("shutil.which", return_value="/usr/bin/conda"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("conda", 10)):
            missing = detector._check_packages(Path("/envs/test"), ["pkg"])
        assert missing == ["pkg"]


# ---------------------------------------------------------------------------
# Backward compatibility: existing find_active / find_environment still work
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_find_active_still_works(self, monkeypatch):
        monkeypatch.setenv("CONDA_PREFIX", "/fake/prefix")
        monkeypatch.setenv("CONDA_DEFAULT_ENV", "base")
        detector = CondaDetector()
        with patch.object(detector, "_get_python_version", return_value=None):
            env = detector.find_active()
        assert isinstance(env, CondaEnvironment)
        assert env.name == "base"

    def test_find_environment_returns_none_without_conda(self, monkeypatch):
        detector = CondaDetector()
        with patch("shutil.which", return_value=None):
            result = detector.find_environment("nonexistent")
        assert result is None

    def test_importable_from_top_level(self):
        from sniff import CondaDetector, CondaEnvironment, CondaValidation, COMMON_INSTALL_PATHS
        assert CondaDetector is not None
        assert CondaEnvironment is not None
        assert CondaValidation is not None
        assert COMMON_INSTALL_PATHS is not None
