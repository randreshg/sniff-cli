"""Focused tests for CLI configuration management."""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from dekk.cli.config import ConfigManager, _deep_copy, _deep_merge, _load_toml


def test_deep_copy_copies_nested_dicts_and_lists_without_aliasing():
    original = {"nested": {"items": [1, 2, 3]}, "flag": True}
    copied = _deep_copy(original)

    assert copied == original
    assert copied is not original
    assert copied["nested"] is not original["nested"]
    assert copied["nested"]["items"] is not original["nested"]["items"]


def test_deep_merge_merges_nested_values_and_replaces_shape_changes():
    target = {"db": {"host": "localhost", "port": 5432}, "mode": {"debug": False}}
    _deep_merge(target, {"db": {"port": 3306, "name": "app"}, "mode": "flat"})

    assert target == {
        "db": {"host": "localhost", "port": 3306, "name": "app"},
        "mode": "flat",
    }


def test_load_toml_handles_valid_missing_invalid_and_disabled_cases(tmp_path):
    valid = tmp_path / "valid.toml"
    valid.write_text('[section]\nkey = "value"\n')
    invalid = tmp_path / "invalid.toml"
    invalid.write_text("not valid [toml")

    assert _load_toml(valid) == {"section": {"key": "value"}}
    assert _load_toml(tmp_path / "missing.toml") == {}
    assert _load_toml(invalid) == {}

    import dekk.cli.config as config_module

    original = config_module.tomllib
    config_module.tomllib = None
    try:
        assert _load_toml(valid) == {}
    finally:
        config_module.tomllib = original


def test_config_manager_loads_defaults_without_mutating_source(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    defaults = {"build": {"target": "release"}}
    config = ConfigManager("testapp", defaults=defaults)
    config.set("build.target", "debug")

    assert config.app_name == "testapp"
    assert config.config_file == "config.toml"
    assert defaults["build"]["target"] == "release"


def test_config_manager_get_set_and_to_dict_are_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config = ConfigManager("testapp", defaults={"db": {"host": "localhost"}, "mode": "prod"})

    assert config.get("db.host") == "localhost"
    assert config.get("missing", "fallback") == "fallback"
    assert config.get("mode.port") is None

    config.set("db.port", 5432)
    config.set("mode.level", "debug")
    snapshot = config.to_dict()
    snapshot["db"] = {"host": "changed"}

    assert config.get("db.port") == 5432
    assert config.get("mode.level") == "debug"
    assert config.get("db.host") == "localhost"


def test_config_manager_merges_user_project_and_env_precedence(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    child = project / "subdir"
    child.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(child)

    user_config = home / ".testapp"
    user_config.mkdir()
    (user_config / "config.toml").write_text('[tier]\nwho = "user"\n[build]\noptimize = false\n')

    project_config = project / ".testapp"
    project_config.mkdir()
    (project_config / "config.toml").write_text('[tier]\nwho = "project"\n[build]\ntarget = "release"\n')

    monkeypatch.setenv("TESTAPP_BUILD_OPTIMIZE", "true")
    monkeypatch.setenv("TESTAPP_DATABASE_HOST", "db.example.com")
    monkeypatch.setenv("OTHERAPP_BUILD_OPTIMIZE", "ignored")

    config = ConfigManager("testapp", defaults={"tier": {"who": "default"}})

    assert config.get("tier.who") == "project"
    assert config.get("build.optimize") == "true"
    assert config.get("build.target") == "release"
    assert config.get("database.host") == "db.example.com"
    assert config.get("otherapp.build.optimize") is None


def test_config_manager_supports_custom_config_file_and_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".testapp"
    config_dir.mkdir()
    settings = config_dir / "settings.toml"
    settings.write_text('[s]\nvalue = "first"\n')
    config = ConfigManager("testapp", config_file="settings.toml")

    assert config.get("s.value") == "first"

    settings.write_text('[s]\nvalue = "second"\n')
    config.load()

    assert config.get("s.value") == "second"


def test_config_manager_save_roundtrips_user_and_project_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)

    user_config = ConfigManager("testapp")
    user_config.set("build.optimize", True)
    user_config.save(user=True)
    assert (home / ".testapp" / "config.toml").exists()

    project_config = ConfigManager("testapp")
    project_config.set("local.key", "value")
    project_config.save(user=False)
    assert (project / ".testapp" / "config.toml").exists()

    reloaded = ConfigManager("testapp")
    assert reloaded.get("build.optimize") is True
    assert reloaded.get("local.key") == "value"


def test_config_manager_save_requires_tomli_w(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    import dekk.cli.config as config_module

    original = config_module.tomli_w
    config_module.tomli_w = None
    try:
        config = ConfigManager("testapp")
        config.set("key", "value")
        with pytest.raises(builtins.RuntimeError, match="tomli_w is required"):
            config.save()
    finally:
        config_module.tomli_w = original

