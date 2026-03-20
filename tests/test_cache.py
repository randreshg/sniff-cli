"""Tests for build cache detection."""

import pytest

from dekk.cache import BuildCacheDetector, BuildCacheInfo, CacheKind


@pytest.fixture
def detector(tmp_path):
    return BuildCacheDetector(project_root=tmp_path)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove cache-related env vars so detection starts clean."""
    cache_vars = [
        "RUSTC_WRAPPER",
        "CC",
        "CXX",
        "SCCACHE_BUCKET",
        "SCCACHE_GCS_BUCKET",
        "SCCACHE_AZURE_CONNECTION_STRING",
        "SCCACHE_REDIS",
        "SCCACHE_MEMCACHED",
        "SCCACHE_DIR",
        "SCCACHE_CONF",
        "CCACHE_DIR",
        "CCACHE_MAXSIZE",
        "CCACHE_CONFIGPATH",
        "TURBO_TOKEN",
        "TURBO_TEAM",
        "TURBO_API",
        "NX_CLOUD_ACCESS_TOKEN",
        "NX_CACHE_DIRECTORY",
        "BAZEL_REMOTE_CACHE",
    ]
    for var in cache_vars:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestCacheKind:
    """Test CacheKind enum values."""

    def test_values(self):
        assert CacheKind.SCCACHE.value == "sccache"
        assert CacheKind.CCACHE.value == "ccache"
        assert CacheKind.TURBOREPO.value == "turborepo"
        assert CacheKind.NX.value == "nx"
        assert CacheKind.BAZEL.value == "bazel"


class TestBuildCacheInfoFrozen:
    """Test BuildCacheInfo is frozen."""

    def test_frozen(self):
        info = BuildCacheInfo(kind=CacheKind.SCCACHE)
        with pytest.raises(AttributeError):
            info.kind = CacheKind.CCACHE  # type: ignore[misc]


class TestDetectAll:
    """Test detect_all returns empty when nothing is available."""

    def test_no_caches_detected(self, detector, clean_env, monkeypatch):
        # Ensure no cache binaries are found
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        results = detector.detect_all()
        assert results == []


class TestSccacheDetection:
    """Tests for sccache detection."""

    def test_not_detected_when_absent(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        info = detector.detect(CacheKind.SCCACHE)
        assert info is None

    def test_detected_via_binary(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/sccache" if cmd == "sccache" else None
        )
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert info.kind == CacheKind.SCCACHE
        assert info.binary_path == "/usr/bin/sccache"

    def test_enabled_via_rustc_wrapper(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setenv("RUSTC_WRAPPER", "sccache")
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert info.is_enabled

    def test_enabled_via_cc(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setenv("CC", "sccache cc")
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert info.is_enabled

    def test_not_enabled_without_wrapper(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/sccache" if cmd == "sccache" else None
        )
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert not info.is_enabled

    def test_s3_storage_detected(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/sccache" if cmd == "sccache" else None
        )
        monkeypatch.setenv("SCCACHE_BUCKET", "my-bucket")
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert info.extra["storage"] == "s3"
        assert info.extra["bucket"] == "my-bucket"

    def test_gcs_storage_detected(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/sccache" if cmd == "sccache" else None
        )
        monkeypatch.setenv("SCCACHE_GCS_BUCKET", "gcs-bucket")
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert info.extra["storage"] == "gcs"

    def test_redis_storage_detected(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/sccache" if cmd == "sccache" else None
        )
        monkeypatch.setenv("SCCACHE_REDIS", "redis://localhost:6379")
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert info.extra["storage"] == "redis"

    def test_local_storage_detected(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/sccache" if cmd == "sccache" else None
        )
        monkeypatch.setenv("SCCACHE_DIR", "/tmp/sccache")
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert info.extra["storage"] == "local"
        assert info.extra["dir"] == "/tmp/sccache"

    def test_config_path_from_env(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/sccache" if cmd == "sccache" else None
        )
        monkeypatch.setenv("SCCACHE_CONF", "/etc/sccache.conf")
        info = detector.detect(CacheKind.SCCACHE)
        assert info is not None
        assert info.config_path == "/etc/sccache.conf"


class TestCcacheDetection:
    """Tests for ccache detection."""

    def test_not_detected_when_absent(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        info = detector.detect(CacheKind.CCACHE)
        assert info is None

    def test_detected_via_binary(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/ccache" if cmd == "ccache" else None
        )
        info = detector.detect(CacheKind.CCACHE)
        assert info is not None
        assert info.kind == CacheKind.CCACHE
        assert info.binary_path == "/usr/bin/ccache"
        assert info.is_enabled  # ccache is enabled when binary is found

    def test_enabled_via_cc_env(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setenv("CC", "ccache gcc")
        info = detector.detect(CacheKind.CCACHE)
        assert info is not None
        assert info.is_enabled

    def test_ccache_dir_extra(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/ccache" if cmd == "ccache" else None
        )
        monkeypatch.setenv("CCACHE_DIR", "/opt/ccache")
        monkeypatch.setenv("CCACHE_MAXSIZE", "5G")
        info = detector.detect(CacheKind.CCACHE)
        assert info is not None
        assert info.extra["dir"] == "/opt/ccache"
        assert info.extra["max_size"] == "5G"

    def test_config_path_from_env(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/ccache" if cmd == "ccache" else None
        )
        monkeypatch.setenv("CCACHE_CONFIGPATH", "/etc/ccache.conf")
        info = detector.detect(CacheKind.CCACHE)
        assert info is not None
        assert info.config_path == "/etc/ccache.conf"


class TestTurborepoDetection:
    """Tests for Turborepo detection."""

    def test_not_detected_when_absent(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        info = detector.detect(CacheKind.TURBOREPO)
        assert info is None

    def test_detected_via_binary(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/turbo" if cmd == "turbo" else None
        )
        info = detector.detect(CacheKind.TURBOREPO)
        assert info is not None
        assert info.kind == CacheKind.TURBOREPO
        assert info.binary_path == "/usr/bin/turbo"
        assert info.is_enabled

    def test_detected_via_config(self, tmp_path, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        (tmp_path / "turbo.json").write_text("{}")
        det = BuildCacheDetector(project_root=tmp_path)
        info = det.detect(CacheKind.TURBOREPO)
        assert info is not None
        assert info.config_path == str(tmp_path / "turbo.json")
        assert info.is_enabled

    def test_remote_cache_env(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/turbo" if cmd == "turbo" else None
        )
        monkeypatch.setenv("TURBO_TOKEN", "tok_abc")
        monkeypatch.setenv("TURBO_TEAM", "my-team")
        info = detector.detect(CacheKind.TURBOREPO)
        assert info is not None
        assert info.extra["remote_cache"] == "enabled"
        assert info.extra["team"] == "my-team"


class TestNxDetection:
    """Tests for Nx detection."""

    def test_not_detected_when_absent(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        info = detector.detect(CacheKind.NX)
        assert info is None

    def test_detected_via_binary(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nx" if cmd == "nx" else None)
        info = detector.detect(CacheKind.NX)
        assert info is not None
        assert info.kind == CacheKind.NX
        assert info.is_enabled

    def test_detected_via_config(self, tmp_path, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        (tmp_path / "nx.json").write_text("{}")
        det = BuildCacheDetector(project_root=tmp_path)
        info = det.detect(CacheKind.NX)
        assert info is not None
        assert info.config_path == str(tmp_path / "nx.json")

    def test_cloud_env(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nx" if cmd == "nx" else None)
        monkeypatch.setenv("NX_CLOUD_ACCESS_TOKEN", "cloud-token")
        monkeypatch.setenv("NX_CACHE_DIRECTORY", "/tmp/nx-cache")
        info = detector.detect(CacheKind.NX)
        assert info is not None
        assert info.extra["cloud"] == "enabled"
        assert info.extra["cache_dir"] == "/tmp/nx-cache"


class TestBazelDetection:
    """Tests for Bazel detection."""

    def test_not_detected_when_absent(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        info = detector.detect(CacheKind.BAZEL)
        assert info is None

    def test_detected_via_bazel_binary(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/bazel" if cmd == "bazel" else None
        )
        info = detector.detect(CacheKind.BAZEL)
        assert info is not None
        assert info.kind == CacheKind.BAZEL
        assert info.binary_path == "/usr/bin/bazel"
        assert info.is_enabled

    def test_detected_via_bazelisk(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/bazelisk" if cmd == "bazelisk" else None
        )
        info = detector.detect(CacheKind.BAZEL)
        assert info is not None
        assert info.binary_path == "/usr/bin/bazelisk"

    def test_detected_via_workspace(self, tmp_path, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        (tmp_path / "WORKSPACE").write_text("")
        det = BuildCacheDetector(project_root=tmp_path)
        info = det.detect(CacheKind.BAZEL)
        assert info is not None
        assert info.config_path == str(tmp_path / "WORKSPACE")

    def test_detected_via_module_bazel(self, tmp_path, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        (tmp_path / "MODULE.bazel").write_text("")
        det = BuildCacheDetector(project_root=tmp_path)
        info = det.detect(CacheKind.BAZEL)
        assert info is not None
        assert info.config_path == str(tmp_path / "MODULE.bazel")

    def test_bazelrc_detected(self, tmp_path, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/bazel" if cmd == "bazel" else None
        )
        (tmp_path / ".bazelrc").write_text("build --remote_cache=grpcs://cache.example.com")
        det = BuildCacheDetector(project_root=tmp_path)
        info = det.detect(CacheKind.BAZEL)
        assert info is not None
        assert info.extra["bazelrc"] == str(tmp_path / ".bazelrc")

    def test_remote_cache_env(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr(
            "shutil.which", lambda cmd: "/usr/bin/bazel" if cmd == "bazel" else None
        )
        monkeypatch.setenv("BAZEL_REMOTE_CACHE", "grpcs://cache.example.com")
        info = detector.detect(CacheKind.BAZEL)
        assert info is not None
        assert info.extra["remote_cache"] == "grpcs://cache.example.com"


class TestDetectAllIntegration:
    """Test detect_all returns multiple caches."""

    def test_multiple_caches_detected(self, tmp_path, clean_env, monkeypatch):
        def fake_which(cmd):
            if cmd == "sccache":
                return "/usr/bin/sccache"
            if cmd == "ccache":
                return "/usr/bin/ccache"
            return None

        monkeypatch.setattr("shutil.which", fake_which)
        monkeypatch.setenv("RUSTC_WRAPPER", "sccache")
        det = BuildCacheDetector(project_root=tmp_path)
        results = det.detect_all()
        kinds = {r.kind for r in results}
        assert CacheKind.SCCACHE in kinds
        assert CacheKind.CCACHE in kinds
        assert len(results) == 2

    def test_detect_all_returns_list(self, detector, clean_env, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        results = detector.detect_all()
        assert isinstance(results, list)
