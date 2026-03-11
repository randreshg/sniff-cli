"""Tests for sniff.cli.config -- ConfigManager, TOML support, multi-tier precedence."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import builtins

import pytest

from sniff.cli.config import ConfigManager, _deep_copy, _deep_merge, _load_toml


# ---------------------------------------------------------------------------
# _deep_copy
# ---------------------------------------------------------------------------


class TestDeepCopy:
    """Tests for the _deep_copy helper."""

    def test_shallow_dict(self):
        d = {"a": 1, "b": "two"}
        copy = _deep_copy(d)
        assert copy == d
        assert copy is not d

    def test_nested_dict(self):
        d = {"a": {"b": {"c": 3}}}
        copy = _deep_copy(d)
        assert copy == d
        assert copy["a"] is not d["a"]
        assert copy["a"]["b"] is not d["a"]["b"]

    def test_list_values_copied(self):
        d = {"items": [1, 2, 3]}
        copy = _deep_copy(d)
        assert copy["items"] == [1, 2, 3]
        assert copy["items"] is not d["items"]

    def test_empty_dict(self):
        assert _deep_copy({}) == {}

    def test_scalar_values(self):
        d = {"a": 1, "b": "s", "c": True, "d": None}
        assert _deep_copy(d) == d


# ---------------------------------------------------------------------------
# _deep_merge
# ---------------------------------------------------------------------------


class TestDeepMerge:
    """Tests for the _deep_merge helper."""

    def test_flat_merge(self):
        target = {"a": 1}
        _deep_merge(target, {"b": 2})
        assert target == {"a": 1, "b": 2}

    def test_override_value(self):
        target = {"a": 1}
        _deep_merge(target, {"a": 99})
        assert target["a"] == 99

    def test_nested_merge(self):
        target = {"db": {"host": "localhost", "port": 5432}}
        _deep_merge(target, {"db": {"port": 3306, "name": "mydb"}})
        assert target == {"db": {"host": "localhost", "port": 3306, "name": "mydb"}}

    def test_source_adds_nested(self):
        target = {"a": 1}
        _deep_merge(target, {"b": {"c": 2}})
        assert target == {"a": 1, "b": {"c": 2}}

    def test_non_dict_replaces_dict(self):
        target = {"a": {"b": 1}}
        _deep_merge(target, {"a": "flat"})
        assert target["a"] == "flat"

    def test_dict_replaces_non_dict(self):
        target = {"a": "flat"}
        _deep_merge(target, {"a": {"b": 1}})
        assert target["a"] == {"b": 1}

    def test_empty_source(self):
        target = {"a": 1}
        _deep_merge(target, {})
        assert target == {"a": 1}

    def test_empty_target(self):
        target: dict = {}
        _deep_merge(target, {"a": 1})
        assert target == {"a": 1}


# ---------------------------------------------------------------------------
# _load_toml
# ---------------------------------------------------------------------------


class TestLoadToml:
    """Tests for the _load_toml helper."""

    def test_valid_toml(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text('[section]\nkey = "value"\n')
        result = _load_toml(p)
        assert result == {"section": {"key": "value"}}

    def test_missing_file(self, tmp_path):
        p = tmp_path / "missing.toml"
        result = _load_toml(p)
        assert result == {}

    def test_invalid_toml(self, tmp_path):
        p = tmp_path / "bad.toml"
        p.write_text("not valid [toml")
        result = _load_toml(p)
        assert result == {}

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.toml"
        p.write_text("")
        result = _load_toml(p)
        assert result == {}

    def test_load_toml_returns_empty_when_tomllib_none(self, tmp_path, monkeypatch):
        import sniff.cli.config as _cfg_mod

        p = tmp_path / "config.toml"
        p.write_text('[s]\nk = "v"\n')
        orig = _cfg_mod.tomllib
        _cfg_mod.tomllib = None
        try:
            result = _load_toml(p)
            assert result == {}
        finally:
            _cfg_mod.tomllib = orig


# ---------------------------------------------------------------------------
# ConfigManager -- init / defaults
# ---------------------------------------------------------------------------


class TestConfigManagerInit:
    """Tests for ConfigManager initialization."""

    def test_default_app_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp")
        assert cfg.app_name == "testapp"
        assert cfg.config_file == "config.toml"

    def test_defaults_loaded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"a": 1, "b": {"c": 2}})
        assert cfg.get("a") == 1
        assert cfg.get("b.c") == 2

    def test_defaults_not_mutated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        defaults = {"a": {"b": 1}}
        cfg = ConfigManager("testapp", defaults=defaults)
        cfg.set("a.b", 99)
        assert defaults["a"]["b"] == 1  # original unchanged

    def test_no_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp")
        assert cfg.to_dict() == {}


# ---------------------------------------------------------------------------
# ConfigManager -- get / set
# ---------------------------------------------------------------------------


class TestGetSet:
    """Tests for ConfigManager.get and ConfigManager.set."""

    def test_get_simple_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"key": "value"})
        assert cfg.get("key") == "value"

    def test_get_dot_notation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"db": {"host": "localhost"}})
        assert cfg.get("db.host") == "localhost"

    def test_get_missing_returns_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp")
        assert cfg.get("missing") is None
        assert cfg.get("missing", "fallback") == "fallback"

    def test_get_deep_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"a": 1})
        assert cfg.get("a.b.c") is None

    def test_set_creates_intermediates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp")
        cfg.set("a.b.c", 42)
        assert cfg.get("a.b.c") == 42
        assert cfg.get("a.b") == {"c": 42}

    def test_set_overwrites(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"key": "old"})
        cfg.set("key", "new")
        assert cfg.get("key") == "new"

    def test_set_replaces_scalar_with_dict(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"a": "scalar"})
        cfg.set("a.b", "nested")
        assert cfg.get("a.b") == "nested"


# ---------------------------------------------------------------------------
# ConfigManager -- user config file
# ---------------------------------------------------------------------------


class TestUserConfig:
    """Tests for loading user config from ~/.{app_name}/config.toml."""

    def test_user_config_loaded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".testapp"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text('[build]\noptimize = true\n')
        cfg = ConfigManager("testapp")
        assert cfg.get("build.optimize") is True

    def test_user_config_merges_with_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".testapp"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text('[build]\noptimize = true\n')
        cfg = ConfigManager("testapp", defaults={"build": {"target": "release"}})
        assert cfg.get("build.optimize") is True
        assert cfg.get("build.target") == "release"


# ---------------------------------------------------------------------------
# ConfigManager -- project config file
# ---------------------------------------------------------------------------


class TestProjectConfig:
    """Tests for loading project config from .{app_name}/config.toml in ancestors."""

    def test_project_config_loaded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        config_dir = project_dir / ".testapp"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text('[local]\nflag = true\n')
        cfg = ConfigManager("testapp")
        assert cfg.get("local.flag") is True

    def test_project_config_in_parent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir()
        parent = tmp_path / "project"
        parent.mkdir()
        child = parent / "subdir"
        child.mkdir()
        monkeypatch.chdir(child)
        config_dir = parent / ".testapp"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text('[proj]\nname = "parent"\n')
        cfg = ConfigManager("testapp")
        assert cfg.get("proj.name") == "parent"

    def test_project_overrides_user(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        user_cfg = home / ".testapp"
        user_cfg.mkdir()
        (user_cfg / "config.toml").write_text('[tier]\nwho = "user"\n')

        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.chdir(project)
        proj_cfg = project / ".testapp"
        proj_cfg.mkdir()
        (proj_cfg / "config.toml").write_text('[tier]\nwho = "project"\n')

        cfg = ConfigManager("testapp")
        assert cfg.get("tier.who") == "project"


# ---------------------------------------------------------------------------
# ConfigManager -- environment variables
# ---------------------------------------------------------------------------


class TestEnvVars:
    """Tests for config overrides from environment variables."""

    def test_env_var_simple(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TESTAPP_LOG_LEVEL", "debug")
        cfg = ConfigManager("testapp")
        assert cfg.get("log.level") == "debug"

    def test_env_var_overrides_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".testapp"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text('[log]\nlevel = "info"\n')
        monkeypatch.setenv("TESTAPP_LOG_LEVEL", "debug")
        cfg = ConfigManager("testapp")
        assert cfg.get("log.level") == "debug"

    def test_env_var_nested(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TESTAPP_DATABASE_HOST", "db.example.com")
        cfg = ConfigManager("testapp")
        assert cfg.get("database.host") == "db.example.com"

    def test_unrelated_env_var_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("OTHER_APP_KEY", "value")
        cfg = ConfigManager("testapp")
        assert cfg.get("app.key") is None


# ---------------------------------------------------------------------------
# ConfigManager -- save
# ---------------------------------------------------------------------------


class TestSave:
    """Tests for ConfigManager.save."""

    def test_save_user_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp")
        cfg.set("build.opt", True)
        cfg.save(user=True)
        saved = tmp_path / ".testapp" / "config.toml"
        assert saved.exists()
        content = saved.read_text()
        assert "opt" in content

    def test_save_project_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir()
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp")
        cfg.set("local.key", "val")
        cfg.save(user=False)
        saved = tmp_path / ".testapp" / "config.toml"
        assert saved.exists()

    def test_save_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp")
        cfg.set("a.b", "hello")
        cfg.set("x", 42)
        cfg.save(user=True)
        cfg2 = ConfigManager("testapp")
        assert cfg2.get("a.b") == "hello"
        assert cfg2.get("x") == 42

    def test_save_raises_when_tomli_w_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        import sniff.cli.config as _cfg_mod

        orig = _cfg_mod.tomli_w
        _cfg_mod.tomli_w = None
        try:
            cfg = ConfigManager("testapp")
            cfg.set("k", "v")
            with pytest.raises(builtins.RuntimeError, match="tomli_w is required"):
                cfg.save()
        finally:
            _cfg_mod.tomli_w = orig


# ---------------------------------------------------------------------------
# ConfigManager -- to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    """Tests for ConfigManager.to_dict."""

    def test_returns_copy(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"a": 1})
        d = cfg.to_dict()
        d["a"] = 99
        assert cfg.get("a") == 1  # internal state not changed

    def test_contains_all_keys(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"x": 1, "y": 2})
        d = cfg.to_dict()
        assert d == {"x": 1, "y": 2}


# ---------------------------------------------------------------------------
# ConfigManager -- reload
# ---------------------------------------------------------------------------


class TestReload:
    """Tests for ConfigManager.load (reload)."""

    def test_reload_picks_up_changes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".testapp"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text('[build]\nopt = false\n')
        cfg = ConfigManager("testapp")
        assert cfg.get("build.opt") is False

        (config_dir / "config.toml").write_text('[build]\nopt = true\n')
        cfg.load()
        assert cfg.get("build.opt") is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for ConfigManager."""

    def test_single_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"simple": "value"})
        assert cfg.get("simple") == "value"

    def test_get_on_non_dict_intermediate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("testapp", defaults={"a": "string"})
        assert cfg.get("a.b") is None

    def test_custom_config_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".testapp"
        config_dir.mkdir()
        (config_dir / "settings.toml").write_text('[s]\nk = "v"\n')
        cfg = ConfigManager("testapp", config_file="settings.toml")
        assert cfg.get("s.k") == "v"

    def test_empty_app_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        cfg = ConfigManager("", defaults={"k": "v"})
        assert cfg.get("k") == "v"
