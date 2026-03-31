from __future__ import annotations

from dekk.diagnostics.validation_cache import ValidationCache
from dekk.paths import user_cache_dir


def test_validation_cache_uses_shared_user_cache_dir(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    cache = ValidationCache()

    assert cache.cache_dir == user_cache_dir("dekk")


def test_validation_cache_roundtrips_entries(tmp_path):
    cache = ValidationCache(cache_dir=tmp_path / "cache")
    project_path = tmp_path / "project"
    project_path.mkdir()

    cache.set(
        project_path,
        "env-key",
        project_path / ".dekk" / "env",
        {"PATH": "/tmp/bin"},
        ["python"],
    )
    cached = cache.get(project_path, "env-key")

    assert cached is not None
    assert cached.environment_prefix == str(project_path / ".dekk" / "env")
    assert cached.env_vars == {"PATH": "/tmp/bin"}
    assert cached.missing_tools == ["python"]
