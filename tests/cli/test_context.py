"""Tests for sniff.cli.context -- CLIContext dataclass."""

from __future__ import annotations

from dataclasses import fields
from unittest.mock import MagicMock

import pytest

from sniff.cli.context import CLIContext


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestCLIContextInit:
    """Tests for CLIContext construction."""

    def test_required_fields(self):
        config = MagicMock()
        output = MagicMock()
        ctx = CLIContext(config=config, output=output)
        assert ctx.config is config
        assert ctx.output is output

    def test_default_verbose_false(self):
        ctx = CLIContext(config=MagicMock(), output=MagicMock())
        assert ctx.verbose is False

    def test_default_quiet_false(self):
        ctx = CLIContext(config=MagicMock(), output=MagicMock())
        assert ctx.quiet is False

    def test_custom_flags(self):
        ctx = CLIContext(config=MagicMock(), output=MagicMock(), verbose=True, quiet=True)
        assert ctx.verbose is True
        assert ctx.quiet is True


# ---------------------------------------------------------------------------
# Dataclass behavior
# ---------------------------------------------------------------------------


class TestDataclassBehavior:
    """Tests verifying CLIContext behaves as a proper dataclass."""

    def test_is_dataclass(self):
        assert hasattr(CLIContext, "__dataclass_fields__")

    def test_field_names(self):
        names = {f.name for f in fields(CLIContext)}
        assert names == {"config", "output", "verbose", "quiet"}

    def test_equality(self):
        config = MagicMock()
        output = MagicMock()
        a = CLIContext(config=config, output=output, verbose=True)
        b = CLIContext(config=config, output=output, verbose=True)
        assert a == b

    def test_inequality(self):
        config = MagicMock()
        output = MagicMock()
        a = CLIContext(config=config, output=output, verbose=True)
        b = CLIContext(config=config, output=output, verbose=False)
        assert a != b

    def test_repr_contains_class_name(self):
        ctx = CLIContext(config=MagicMock(), output=MagicMock())
        assert "CLIContext" in repr(ctx)


# ---------------------------------------------------------------------------
# __post_init__ hook
# ---------------------------------------------------------------------------


class TestPostInit:
    """Tests for __post_init__ hook."""

    def test_post_init_called(self):
        """__post_init__ runs on construction without errors."""
        ctx = CLIContext(config=MagicMock(), output=MagicMock())
        # No exception means __post_init__ ran successfully

    def test_post_init_subclass_override(self):
        """Subclasses can override __post_init__ for lazy initialization."""
        class ExtendedContext(CLIContext):
            extra: str = ""

            def __post_init__(self):
                super().__post_init__()
                self.extra = "initialized"

        ctx = ExtendedContext(config=MagicMock(), output=MagicMock())
        assert ctx.extra == "initialized"


# ---------------------------------------------------------------------------
# Integration with real types
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests with real ConfigManager and OutputFormatter."""

    def test_with_real_output_formatter(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        from sniff.cli.config import ConfigManager
        from sniff.cli.output import OutputFormatter

        config = ConfigManager("testapp")
        output = OutputFormatter(verbose=True, quiet=False)
        ctx = CLIContext(config=config, output=output, verbose=True)

        assert ctx.config.app_name == "testapp"
        assert ctx.output.verbose is True
        assert ctx.verbose is True

    def test_config_access_through_context(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        from sniff.cli.config import ConfigManager
        from sniff.cli.output import OutputFormatter

        config = ConfigManager("testapp", defaults={"build": {"target": "release"}})
        output = OutputFormatter()
        ctx = CLIContext(config=config, output=output)

        assert ctx.config.get("build.target") == "release"

    def test_output_methods_through_context(self, tmp_path, monkeypatch):
        """Verify output methods are callable through context."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        from sniff.cli.config import ConfigManager
        from sniff.cli.output import OutputFormatter

        config = ConfigManager("testapp")
        output = OutputFormatter(quiet=True)
        ctx = CLIContext(config=config, output=output, quiet=True)

        # These should not raise; output suppressed by quiet=True
        ctx.output.success("ok")
        ctx.output.error("err")
        ctx.output.warning("warn")
        ctx.output.info("info")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for CLIContext."""

    def test_none_config_accepted(self):
        """CLIContext does not validate types; None is accepted."""
        ctx = CLIContext(config=None, output=None)  # type: ignore[arg-type]
        assert ctx.config is None

    def test_attribute_mutation(self):
        ctx = CLIContext(config=MagicMock(), output=MagicMock())
        ctx.verbose = True
        assert ctx.verbose is True
        ctx.quiet = True
        assert ctx.quiet is True

    def test_extra_attributes_assignable(self):
        """Dataclass instances accept arbitrary attribute assignment."""
        ctx = CLIContext(config=MagicMock(), output=MagicMock())
        ctx.custom_attr = "extra"  # type: ignore[attr-defined]
        assert ctx.custom_attr == "extra"  # type: ignore[attr-defined]
