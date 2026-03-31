"""Tests for configuration management."""

from __future__ import annotations

from pathlib import Path

import pytest

from dekk.core.config import ConfigManager, ConfigReconciler, ConfigSource
from dekk.core.paths import project_config_file, user_config_file

# ===========================================================================
# ConfigSource tests
# ===========================================================================


class TestConfigSource:
    def test_basic_creation(self):
        src = ConfigSource("key", "value", "default", None, None, 0)
        assert src.key == "key"
        assert src.value == "value"
        assert src.source == "default"
        assert src.file_path is None
        assert src.line_number is None
        assert src.precedence == 0

    def test_file_source(self):
        path = Path("/etc/app/config.toml")
        src = ConfigSource("db.host", "localhost", "file", path, 42, 1)
        assert src.file_path == path
        assert src.line_number == 42
        assert src.source == "file"

    def test_frozen(self):
        src = ConfigSource("key", "val", "default", None, None, 0)
        with pytest.raises(AttributeError):
            src.key = "other"  # type: ignore[misc]

    def test_frozen_value(self):
        src = ConfigSource("key", "val", "default", None, None, 0)
        with pytest.raises(AttributeError):
            src.value = "changed"  # type: ignore[misc]

    def test_frozen_precedence(self):
        src = ConfigSource("key", "val", "default", None, None, 0)
        with pytest.raises(AttributeError):
            src.precedence = 99  # type: ignore[misc]

    def test_equality(self):
        a = ConfigSource("k", "v", "default", None, None, 0)
        b = ConfigSource("k", "v", "default", None, None, 0)
        assert a == b

    def test_inequality_key(self):
        a = ConfigSource("k1", "v", "default", None, None, 0)
        b = ConfigSource("k2", "v", "default", None, None, 0)
        assert a != b

    def test_inequality_value(self):
        a = ConfigSource("k", "v1", "default", None, None, 0)
        b = ConfigSource("k", "v2", "default", None, None, 0)
        assert a != b

    def test_inequality_precedence(self):
        a = ConfigSource("k", "v", "default", None, None, 0)
        b = ConfigSource("k", "v", "default", None, None, 1)
        assert a != b

    def test_various_value_types_int(self):
        src = ConfigSource("count", 42, "default", None, None, 0)
        assert src.value == 42

    def test_various_value_types_float(self):
        src = ConfigSource("rate", 3.14, "default", None, None, 0)
        assert src.value == 3.14

    def test_various_value_types_bool(self):
        src = ConfigSource("enabled", True, "cli", None, None, 3)
        assert src.value is True

    def test_various_value_types_list(self):
        src = ConfigSource("items", [1, 2, 3], "file", Path("x.toml"), 1, 1)
        assert src.value == [1, 2, 3]

    def test_various_value_types_dict(self):
        src = ConfigSource("nested", {"a": 1}, "default", None, None, 0)
        assert src.value == {"a": 1}

    def test_various_value_types_none(self):
        src = ConfigSource("empty", None, "default", None, None, 0)
        assert src.value is None

    def test_source_types(self):
        for source_type in ("environment", "file", "default", "cli"):
            src = ConfigSource("k", "v", source_type, None, None, 0)
            assert src.source == source_type

    def test_hash(self):
        src = ConfigSource("k", "v", "default", None, None, 0)
        # Frozen dataclasses are hashable
        assert hash(src) is not None
        d = {src: True}
        assert d[src] is True

    def test_repr(self):
        src = ConfigSource("k", "v", "default", None, None, 0)
        r = repr(src)
        assert "ConfigSource" in r
        assert "k" in r


# ===========================================================================
# ConfigReconciler tests
# ===========================================================================


class TestConfigReconcilerInit:
    def test_empty(self):
        rec = ConfigReconciler()
        assert rec.sources == {}

    def test_keys_empty(self):
        rec = ConfigReconciler()
        assert rec.keys() == []


class TestConfigReconcilerAddSource:
    def test_add_single(self):
        rec = ConfigReconciler()
        src = ConfigSource("key", "val", "default", None, None, 0)
        rec.add_source(src)
        assert "key" in rec.sources
        assert len(rec.sources["key"]) == 1

    def test_add_multiple_same_key(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "a", "default", None, None, 0))
        rec.add_source(ConfigSource("k", "b", "file", Path("f"), 1, 1))
        rec.add_source(ConfigSource("k", "c", "cli", None, None, 3))
        assert len(rec.sources["k"]) == 3

    def test_add_multiple_different_keys(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("x", 1, "default", None, None, 0))
        rec.add_source(ConfigSource("y", 2, "default", None, None, 0))
        assert "x" in rec.sources
        assert "y" in rec.sources

    def test_add_duplicate_source(self):
        rec = ConfigReconciler()
        src = ConfigSource("k", "v", "default", None, None, 0)
        rec.add_source(src)
        rec.add_source(src)
        assert len(rec.sources["k"]) == 2


class TestConfigReconcilerResolve:
    def test_resolve_single(self):
        rec = ConfigReconciler()
        src = ConfigSource("k", "v", "default", None, None, 0)
        rec.add_source(src)
        assert rec.resolve("k") == src

    def test_resolve_highest_precedence(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "low", "default", None, None, 0))
        rec.add_source(ConfigSource("k", "mid", "file", Path("f"), 1, 1))
        rec.add_source(ConfigSource("k", "high", "cli", None, None, 3))
        result = rec.resolve("k")
        assert result.value == "high"
        assert result.precedence == 3

    def test_resolve_not_found(self):
        rec = ConfigReconciler()
        assert rec.resolve("missing") is None

    def test_resolve_env_over_file(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "file_val", "file", Path("f"), 1, 1))
        rec.add_source(ConfigSource("k", "env_val", "environment", None, None, 2))
        result = rec.resolve("k")
        assert result.value == "env_val"

    def test_resolve_cli_over_env(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "env_val", "environment", None, None, 2))
        rec.add_source(ConfigSource("k", "cli_val", "cli", None, None, 3))
        result = rec.resolve("k")
        assert result.value == "cli_val"

    def test_resolve_same_precedence(self):
        """When precedence is equal, highest precedence still wins (deterministic)."""
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "first", "file", Path("a"), 1, 1))
        rec.add_source(ConfigSource("k", "second", "file", Path("b"), 2, 1))
        result = rec.resolve("k")
        # Both have precedence 1, result is deterministic via max()
        assert result.precedence == 1
        assert result.value in ("first", "second")

    def test_resolve_negative_precedence(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "neg", "default", None, None, -1))
        rec.add_source(ConfigSource("k", "zero", "default", None, None, 0))
        result = rec.resolve("k")
        assert result.value == "zero"

    def test_resolve_large_precedence(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "normal", "default", None, None, 0))
        rec.add_source(ConfigSource("k", "override", "cli", None, None, 9999))
        result = rec.resolve("k")
        assert result.value == "override"

    def test_resolve_returns_config_source(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "v", "default", None, None, 0))
        result = rec.resolve("k")
        assert isinstance(result, ConfigSource)

    def test_resolve_preserves_file_path(self):
        rec = ConfigReconciler()
        path = Path("/etc/app/config.toml")
        rec.add_source(ConfigSource("k", "v", "file", path, 42, 10))
        result = rec.resolve("k")
        assert result.file_path == path
        assert result.line_number == 42


class TestConfigReconcilerExplain:
    def test_explain_not_found(self):
        rec = ConfigReconciler()
        assert rec.explain("missing") == "missing: not found"

    def test_explain_single_default(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "v", "default", None, None, 0))
        text = rec.explain("k")
        assert "Configuration for 'k':" in text
        assert "default: v" in text
        assert "Final value: v (from default)" in text

    def test_explain_single_file(self):
        rec = ConfigReconciler()
        path = Path("config.yaml")
        rec.add_source(ConfigSource("k", "v", "file", path, 12, 1))
        text = rec.explain("k")
        assert "file: v (from config.yaml:12)" in text
        assert "Final value: v (from file)" in text

    def test_explain_multiple_sources(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("batch_size", 32, "default", None, None, 0))
        rec.add_source(ConfigSource("batch_size", 64, "file", Path("config.yaml"), 12, 1))
        rec.add_source(ConfigSource("batch_size", 128, "environment", None, None, 2))
        rec.add_source(ConfigSource("batch_size", 256, "cli", None, None, 3))
        text = rec.explain("batch_size")
        assert "Configuration for 'batch_size':" in text
        assert "default: 32" in text
        assert "file: 64 (from config.yaml:12)" in text
        assert "environment: 128" in text
        assert "cli: 256" in text
        assert "Final value: 256 (from cli)" in text

    def test_explain_sorted_by_precedence(self):
        rec = ConfigReconciler()
        # Add in reverse order
        rec.add_source(ConfigSource("k", "high", "cli", None, None, 3))
        rec.add_source(ConfigSource("k", "low", "default", None, None, 0))
        text = rec.explain("k")
        lines = text.split("\n")
        # default (prec 0) should appear before cli (prec 3)
        default_idx = next(i for i, line in enumerate(lines) if "default:" in line)
        cli_idx = next(i for i, line in enumerate(lines) if "cli:" in line)
        assert default_idx < cli_idx

    def test_explain_arrow_in_final_line(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "v", "default", None, None, 0))
        text = rec.explain("k")
        assert "\u2192" in text  # Unicode arrow

    def test_explain_file_without_line_number(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "v", "file", Path("f.toml"), None, 1))
        text = rec.explain("k")
        assert "file: v (from f.toml:None)" in text

    def test_explain_file_without_path(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "v", "file", None, None, 1))
        text = rec.explain("k")
        # Without file_path, falls into the else branch
        assert "file: v" in text
        assert "(from" not in text.split("file: v")[1].split("\n")[0]


class TestConfigReconcilerKeys:
    def test_keys_sorted(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("z_key", 1, "default", None, None, 0))
        rec.add_source(ConfigSource("a_key", 2, "default", None, None, 0))
        rec.add_source(ConfigSource("m_key", 3, "default", None, None, 0))
        assert rec.keys() == ["a_key", "m_key", "z_key"]

    def test_keys_no_duplicates(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", 1, "default", None, None, 0))
        rec.add_source(ConfigSource("k", 2, "cli", None, None, 3))
        assert rec.keys() == ["k"]


class TestConfigReconcilerAllSources:
    def test_all_sources_not_found(self):
        rec = ConfigReconciler()
        assert rec.all_sources("missing") == []

    def test_all_sources_sorted_by_precedence(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "c", "cli", None, None, 3))
        rec.add_source(ConfigSource("k", "a", "default", None, None, 0))
        rec.add_source(ConfigSource("k", "b", "file", Path("f"), 1, 1))
        sources = rec.all_sources("k")
        assert len(sources) == 3
        assert sources[0].precedence == 0
        assert sources[1].precedence == 1
        assert sources[2].precedence == 3

    def test_all_sources_returns_list(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "v", "default", None, None, 0))
        result = rec.all_sources("k")
        assert isinstance(result, list)
        assert all(isinstance(s, ConfigSource) for s in result)


# ===========================================================================
# Integration / full-workflow tests
# ===========================================================================


class TestConfigReconcilerIntegration:
    def test_full_precedence_chain(self):
        """default < file < environment < cli"""
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("host", "default.local", "default", None, None, 0))
        rec.add_source(ConfigSource("host", "file.local", "file", Path("app.toml"), 5, 1))
        rec.add_source(ConfigSource("host", "env.local", "environment", None, None, 2))
        rec.add_source(ConfigSource("host", "cli.local", "cli", None, None, 3))
        assert rec.resolve("host").value == "cli.local"

    def test_partial_chain_file_wins(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("port", 8080, "default", None, None, 0))
        rec.add_source(ConfigSource("port", 9090, "file", Path("cfg.toml"), 10, 1))
        assert rec.resolve("port").value == 9090

    def test_multiple_keys_independent(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("host", "a", "default", None, None, 0))
        rec.add_source(ConfigSource("host", "b", "cli", None, None, 3))
        rec.add_source(ConfigSource("port", 80, "default", None, None, 0))
        rec.add_source(ConfigSource("port", 443, "environment", None, None, 2))
        assert rec.resolve("host").value == "b"
        assert rec.resolve("port").value == 443

    def test_explain_after_resolve(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "a", "default", None, None, 0))
        rec.add_source(ConfigSource("k", "b", "cli", None, None, 3))
        # resolve doesn't affect explain
        rec.resolve("k")
        text = rec.explain("k")
        assert "default: a" in text
        assert "cli: b" in text

    def test_add_source_after_resolve(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "low", "default", None, None, 0))
        assert rec.resolve("k").value == "low"
        rec.add_source(ConfigSource("k", "high", "cli", None, None, 3))
        assert rec.resolve("k").value == "high"

    def test_dotted_keys(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("database.host", "localhost", "default", None, None, 0))
        rec.add_source(ConfigSource("database.host", "prod.db", "file", Path("p.toml"), 7, 1))
        assert rec.resolve("database.host").value == "prod.db"

    def test_empty_string_key(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("", "val", "default", None, None, 0))
        assert rec.resolve("").value == "val"

    def test_empty_string_value(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "", "default", None, None, 0))
        assert rec.resolve("k").value == ""

    def test_many_sources_for_one_key(self):
        rec = ConfigReconciler()
        for i in range(20):
            rec.add_source(ConfigSource("k", f"v{i}", "default", None, None, i))
        result = rec.resolve("k")
        assert result.value == "v19"
        assert result.precedence == 19

    def test_explain_multiline_output(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "a", "default", None, None, 0))
        rec.add_source(ConfigSource("k", "b", "cli", None, None, 3))
        text = rec.explain("k")
        lines = text.strip().split("\n")
        assert len(lines) == 4  # header + 2 sources + final

    def test_keys_reflects_all_added(self):
        rec = ConfigReconciler()
        for name in ["z", "a", "m", "b"]:
            rec.add_source(ConfigSource(name, name, "default", None, None, 0))
        assert rec.keys() == ["a", "b", "m", "z"]

    def test_file_path_as_absolute(self):
        rec = ConfigReconciler()
        path = Path("/home/user/.config/app/config.toml")
        rec.add_source(ConfigSource("k", "v", "file", path, 100, 1))
        result = rec.resolve("k")
        assert result.file_path == path
        assert result.file_path.is_absolute()

    def test_resolve_with_string_and_int_values(self):
        rec = ConfigReconciler()
        rec.add_source(ConfigSource("k", "string_val", "default", None, None, 0))
        rec.add_source(ConfigSource("k", 42, "cli", None, None, 3))
        result = rec.resolve("k")
        assert result.value == 42


# ===========================================================================
# ConfigManager tests (existing functionality)
# ===========================================================================


class TestConfigManager:
    def test_get_set(self):
        config = ConfigManager("test", defaults={"database": {"path": "/tmp/db"}})
        assert config.get("database.path") == "/tmp/db"
        assert config.get("nonexistent.key", default="fallback") == "fallback"
        config.set("custom.value", "test")
        assert config.get("custom.value") == "test"

    def test_env_override(self, monkeypatch):
        config = ConfigManager("testapp", env_prefix="TESTAPP", defaults={"key": "default"})
        monkeypatch.setenv("TESTAPP_KEY", "from_env")
        config._load()
        assert config.get("key") == "from_env"

    def test_to_dict(self):
        config = ConfigManager("test", defaults={"a": 1, "b": {"c": 2}})
        result = config.to_dict()
        assert result == {"a": 1, "b": {"c": 2}}

    def test_default_values(self):
        config = ConfigManager("test", defaults={"x": 10, "y": 20})
        assert config.get("x") == 10
        assert config.get("y") == 20

    def test_nested_set(self):
        config = ConfigManager("test", defaults={})
        config.set("a.b.c", "deep")
        assert config.get("a.b.c") == "deep"

    def test_get_missing_returns_none(self):
        config = ConfigManager("test", defaults={})
        assert config.get("nonexistent") is None

    def test_get_missing_returns_default(self):
        config = ConfigManager("test", defaults={})
        assert config.get("nonexistent", "fallback") == "fallback"

    def test_overwrite_set(self):
        config = ConfigManager("test", defaults={"k": "old"})
        config.set("k", "new")
        assert config.get("k") == "new"

    def test_deep_merge(self):
        config = ConfigManager("test", defaults={"a": {"b": 1, "c": 2}})
        config._merge({"a": {"c": 3, "d": 4}})
        assert config.get("a.b") == 1
        assert config.get("a.c") == 3
        assert config.get("a.d") == 4

    def test_env_prefix_default(self):
        config = ConfigManager("myapp")
        assert config.env_prefix == "MYAPP"

    def test_config_dir_default(self):
        config = ConfigManager("myapp")
        assert config.config_dir == ".myapp"

    def test_custom_env_prefix(self):
        config = ConfigManager("myapp", env_prefix="CUSTOM")
        assert config.env_prefix == "CUSTOM"

    def test_custom_config_dir(self):
        config = ConfigManager("myapp", config_dir=".custom")
        assert config.config_dir == ".custom"

    def test_loads_user_and_project_config_from_shared_path_policy(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        project = tmp_path / "project"
        child = project / "subdir"
        child.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(child)

        user_path = user_config_file("testapp")
        user_path.parent.mkdir(parents=True)
        user_path.write_text('[database]\nhost = "user"\n', encoding="utf-8")

        project_path = project_config_file("testapp", start_dir=project)
        project_path.parent.mkdir()
        project_path.write_text('[database]\nhost = "project"\n', encoding="utf-8")

        config = ConfigManager("testapp")
        assert config.get("database.host") == "project"
