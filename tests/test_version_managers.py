"""Tests for version manager detection."""

import os
from pathlib import Path

import pytest

from sniff_cli.version_managers import (
    ManagedVersion,
    VersionManagerDetector,
    VersionManagerInfo,
)


@pytest.fixture
def detector():
    return VersionManagerDetector()


class TestVersionManagerInfo:
    def test_is_available_true(self, tmp_path):
        info = VersionManagerInfo(
            name="test", command="test", root=tmp_path,
        )
        assert info.is_available is True

    def test_is_available_false(self, tmp_path):
        info = VersionManagerInfo(
            name="test", command="test", root=tmp_path / "no_such_dir",
        )
        assert info.is_available is False

    def test_version_count(self, tmp_path):
        versions = (
            ManagedVersion("3.11.0", tmp_path / "3.11.0"),
            ManagedVersion("3.12.0", tmp_path / "3.12.0"),
        )
        info = VersionManagerInfo(
            name="test", command="test", root=tmp_path,
            installed_versions=versions,
        )
        assert info.version_count == 2


class TestManagedVersion:
    def test_creation(self, tmp_path):
        mv = ManagedVersion("3.11.0", tmp_path, is_active=True)
        assert mv.version == "3.11.0"
        assert mv.path == tmp_path
        assert mv.is_active is True

    def test_default_not_active(self, tmp_path):
        mv = ManagedVersion("3.11.0", tmp_path)
        assert mv.is_active is False


class TestPyenvDetection:
    def test_detects_pyenv(self, tmp_path, monkeypatch, detector):
        # Set up a fake pyenv structure
        pyenv_root = tmp_path / ".pyenv"
        versions_dir = pyenv_root / "versions"
        (versions_dir / "3.11.0").mkdir(parents=True)
        (versions_dir / "3.12.0").mkdir(parents=True)

        monkeypatch.setenv("PYENV_ROOT", str(pyenv_root))
        monkeypatch.setenv("PYENV_VERSION", "3.12.0")

        info = detector.detect("pyenv")
        assert info is not None
        assert info.name == "pyenv"
        assert info.version_count == 2
        assert info.active_version == "3.12.0"

        # Check active flag
        active = [v for v in info.installed_versions if v.is_active]
        assert len(active) == 1
        assert active[0].version == "3.12.0"

    def test_no_pyenv(self, tmp_path, monkeypatch, detector):
        monkeypatch.setenv("PYENV_ROOT", str(tmp_path / "nonexistent"))
        info = detector.detect("pyenv")
        assert info is None


class TestRustupDetection:
    def test_detects_rustup(self, tmp_path, monkeypatch, detector):
        rustup_home = tmp_path / ".rustup"
        toolchains = rustup_home / "toolchains"
        (toolchains / "stable-x86_64-unknown-linux-gnu").mkdir(parents=True)
        (toolchains / "nightly-x86_64-unknown-linux-gnu").mkdir(parents=True)

        # Write a settings.toml
        settings = rustup_home / "settings.toml"
        settings.write_text('default_toolchain = "nightly-x86_64-unknown-linux-gnu"\n')

        monkeypatch.setenv("RUSTUP_HOME", str(rustup_home))
        monkeypatch.delenv("RUSTUP_TOOLCHAIN", raising=False)

        info = detector.detect("rustup")
        assert info is not None
        assert info.name == "rustup"
        assert info.version_count == 2
        assert info.active_version == "nightly-x86_64-unknown-linux-gnu"

    def test_rustup_env_override(self, tmp_path, monkeypatch, detector):
        rustup_home = tmp_path / ".rustup"
        (rustup_home / "toolchains" / "stable").mkdir(parents=True)

        monkeypatch.setenv("RUSTUP_HOME", str(rustup_home))
        monkeypatch.setenv("RUSTUP_TOOLCHAIN", "stable")

        info = detector.detect("rustup")
        assert info is not None
        assert info.active_version == "stable"


class TestNvmDetection:
    def test_detects_nvm(self, tmp_path, monkeypatch, detector):
        nvm_dir = tmp_path / ".nvm"
        node_versions = nvm_dir / "versions" / "node"
        (node_versions / "v18.17.0").mkdir(parents=True)
        (node_versions / "v20.10.0").mkdir(parents=True)

        monkeypatch.setenv("NVM_DIR", str(nvm_dir))
        monkeypatch.setenv("NVM_BIN", str(node_versions / "v20.10.0" / "bin"))

        info = detector.detect("nvm")
        assert info is not None
        assert info.name == "nvm"
        assert info.version_count == 2
        assert info.active_version == "20.10.0"

    def test_no_nvm(self, tmp_path, monkeypatch, detector):
        monkeypatch.setenv("NVM_DIR", str(tmp_path / "nonexistent"))
        info = detector.detect("nvm")
        assert info is None


class TestRbenvDetection:
    def test_detects_rbenv(self, tmp_path, monkeypatch, detector):
        rbenv_root = tmp_path / ".rbenv"
        versions = rbenv_root / "versions"
        (versions / "3.2.0").mkdir(parents=True)
        (versions / "3.3.0").mkdir(parents=True)

        monkeypatch.setenv("RBENV_ROOT", str(rbenv_root))
        monkeypatch.setenv("RBENV_VERSION", "3.3.0")

        info = detector.detect("rbenv")
        assert info is not None
        assert info.name == "rbenv"
        assert info.version_count == 2
        assert info.active_version == "3.3.0"


class TestAsdfDetection:
    def test_detects_asdf(self, tmp_path, monkeypatch, detector):
        asdf_dir = tmp_path / ".asdf"
        installs = asdf_dir / "installs"
        (installs / "python" / "3.11.0").mkdir(parents=True)
        (installs / "nodejs" / "20.10.0").mkdir(parents=True)

        monkeypatch.setenv("ASDF_DATA_DIR", str(asdf_dir))

        info = detector.detect("asdf")
        assert info is not None
        assert info.name == "asdf"
        assert info.version_count == 2
        assert any("python/3.11.0" in v.version for v in info.installed_versions)
        assert any("nodejs/20.10.0" in v.version for v in info.installed_versions)


class TestSdkmanDetection:
    def test_detects_sdkman(self, tmp_path, monkeypatch, detector):
        sdkman_dir = tmp_path / ".sdkman"
        candidates = sdkman_dir / "candidates"
        (candidates / "java" / "21.0.1-tem").mkdir(parents=True)
        (candidates / "java" / "17.0.9-tem").mkdir(parents=True)

        monkeypatch.setenv("SDKMAN_DIR", str(sdkman_dir))

        info = detector.detect("sdkman")
        assert info is not None
        assert info.name == "sdkman"
        assert info.version_count == 2


class TestDetectAll:
    def test_detect_all_returns_list(self, tmp_path, monkeypatch, detector):
        # Set up pyenv
        pyenv_root = tmp_path / ".pyenv"
        (pyenv_root / "versions" / "3.11.0").mkdir(parents=True)
        monkeypatch.setenv("PYENV_ROOT", str(pyenv_root))

        # Ensure others are absent
        monkeypatch.setenv("NVM_DIR", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("RBENV_ROOT", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("RUSTUP_HOME", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("GOENV_ROOT", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("SDKMAN_DIR", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("ASDF_DATA_DIR", str(tmp_path / "nonexistent"))

        results = detector.detect_all()
        assert isinstance(results, list)
        # At least pyenv should be detected
        names = [r.name for r in results]
        assert "pyenv" in names

    def test_detect_unknown_returns_none(self, detector):
        assert detector.detect("unknown_manager") is None
