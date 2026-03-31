"""Focused tests for CLI configuration management."""

from __future__ import annotations

from dekk.cli.config import ConfigManager
from dekk.paths import project_config_file, user_config_file


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

    user_config = user_config_file("testapp")
    user_config.parent.mkdir(parents=True)
    user_config.write_text('[tier]\nwho = "user"\n[build]\noptimize = false\n')

    project_config = project_config_file("testapp", start_dir=project)
    project_config.parent.mkdir()
    project_config.write_text(
        '[tier]\nwho = "project"\n[build]\ntarget = "release"\n'
    )

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
    assert user_config_file("testapp").exists()

    project_config = ConfigManager("testapp")
    project_config.set("local.key", "value")
    project_config.save(user=False)
    assert project_config_file("testapp", start_dir=project).exists()

    reloaded = ConfigManager("testapp")
    assert reloaded.get("build.optimize") is True
    assert reloaded.get("local.key") == "value"


def test_config_manager_save_falls_back_without_tomli_w(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    import dekk.cli.config as config_module

    original = config_module.tomli_w
    config_module.tomli_w = None
    try:
        config = ConfigManager("testapp")
        config.set("key", "value")
        config.set("build.optimize", True)
        config.save()

        reloaded = ConfigManager("testapp")
        assert reloaded.get("key") == "value"
        assert reloaded.get("build.optimize") is True
    finally:
        config_module.tomli_w = original
