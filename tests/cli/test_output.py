"""Tests for sniff.cli.output -- OutputFormat and OutputFormatter."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.theme import Theme

from sniff.cli.output import OutputFormat, OutputFormatter
from sniff.cli.styles import CLI_THEME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_stdout(fn, *args, **kwargs) -> str:
    """Capture stdout (print()) output."""
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        fn(*args, **kwargs)
    return buf.getvalue()


def _capture_console(fn, *args, **kwargs) -> str:
    """Capture Rich console output by patching the styles module console.

    Also patches the ``console`` reference in ``sniff.cli.output`` since
    ``_print_table`` uses it directly.
    """
    buf = io.StringIO()
    capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)

    import sniff.cli.output as _out_mod
    import sniff.cli.styles as _mod

    orig_styles = _mod.console
    orig_output = _out_mod.console
    _mod.console = capture_console
    _out_mod.console = capture_console
    try:
        fn(*args, **kwargs)
    finally:
        _mod.console = orig_styles
        _out_mod.console = orig_output
    return buf.getvalue()


def _capture_err_console(fn, *args, **kwargs) -> str:
    """Capture Rich err_console output."""
    buf = io.StringIO()
    capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)

    import sniff.cli.styles as _mod

    orig = _mod.err_console
    _mod.err_console = capture_console
    try:
        fn(*args, **kwargs)
    finally:
        _mod.err_console = orig
    return buf.getvalue()


# ---------------------------------------------------------------------------
# OutputFormat Enum
# ---------------------------------------------------------------------------


class TestOutputFormat:
    """Tests for the OutputFormat enum."""

    def test_all_formats_present(self):
        expected = {"TABLE", "JSON", "YAML", "TEXT"}
        assert expected == {f.name for f in OutputFormat}

    def test_values(self):
        assert OutputFormat.TABLE == "table"
        assert OutputFormat.JSON == "json"
        assert OutputFormat.YAML == "yaml"
        assert OutputFormat.TEXT == "text"

    def test_is_str_enum(self):
        assert issubclass(OutputFormat, str)

    def test_from_string(self):
        assert OutputFormat("json") == OutputFormat.JSON


# ---------------------------------------------------------------------------
# OutputFormatter construction
# ---------------------------------------------------------------------------


class TestOutputFormatterInit:
    """Tests for OutputFormatter initialization."""

    def test_defaults(self):
        fmt = OutputFormatter()
        assert fmt.format == OutputFormat.TABLE
        assert fmt.quiet is False
        assert fmt.verbose is False

    def test_custom_params(self):
        fmt = OutputFormatter(format=OutputFormat.JSON, quiet=True, verbose=True)
        assert fmt.format == OutputFormat.JSON
        assert fmt.quiet is True
        assert fmt.verbose is True


# ---------------------------------------------------------------------------
# print_result -- JSON
# ---------------------------------------------------------------------------


class TestPrintResultJSON:
    """Tests for print_result in JSON mode."""

    def test_valid_json(self):
        fmt = OutputFormatter(format=OutputFormat.JSON)
        out = _capture_stdout(fmt.print_result, {"name": "sniff", "version": "3.0.0"})
        parsed = json.loads(out)
        assert parsed == {"name": "sniff", "version": "3.0.0"}

    def test_json_indent(self):
        fmt = OutputFormatter(format=OutputFormat.JSON)
        out = _capture_stdout(fmt.print_result, {"k": "v"})
        assert "  " in out  # indented

    def test_json_with_nested_data(self):
        fmt = OutputFormatter(format=OutputFormat.JSON)
        data = {"a": {"b": [1, 2, 3]}}
        out = _capture_stdout(fmt.print_result, data)
        parsed = json.loads(out)
        assert parsed["a"]["b"] == [1, 2, 3]

    def test_json_ignores_title(self):
        fmt = OutputFormatter(format=OutputFormat.JSON)
        out = _capture_stdout(fmt.print_result, {"x": 1}, title="Ignored Title")
        parsed = json.loads(out)
        assert "Ignored Title" not in out or parsed == {"x": 1}


# ---------------------------------------------------------------------------
# print_result -- YAML
# ---------------------------------------------------------------------------


class TestPrintResultYAML:
    """Tests for print_result in YAML mode."""

    def test_yaml_output(self):
        import yaml

        fmt = OutputFormatter(format=OutputFormat.YAML)
        out = _capture_stdout(fmt.print_result, {"name": "sniff"})
        parsed = yaml.safe_load(out)
        assert parsed == {"name": "sniff"}

    def test_yaml_nested(self):
        import yaml

        fmt = OutputFormatter(format=OutputFormat.YAML)
        data = {"db": {"host": "localhost", "port": 5432}}
        out = _capture_stdout(fmt.print_result, data)
        parsed = yaml.safe_load(out)
        assert parsed["db"]["port"] == 5432


# ---------------------------------------------------------------------------
# print_result -- TEXT
# ---------------------------------------------------------------------------


class TestPrintResultText:
    """Tests for print_result in TEXT mode."""

    def test_text_key_value(self):
        fmt = OutputFormatter(format=OutputFormat.TEXT)
        out = _capture_stdout(fmt.print_result, {"name": "sniff", "version": "3.0.0"})
        assert "name: sniff" in out
        assert "version: 3.0.0" in out

    def test_text_empty_dict(self):
        fmt = OutputFormatter(format=OutputFormat.TEXT)
        out = _capture_stdout(fmt.print_result, {})
        assert out.strip() == ""


# ---------------------------------------------------------------------------
# print_result -- TABLE
# ---------------------------------------------------------------------------


class TestPrintResultTable:
    """Tests for print_result in TABLE mode."""

    def test_table_contains_values(self):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        out = _capture_console(fmt.print_result, {"name": "sniff"})
        assert "name" in out
        assert "sniff" in out

    def test_table_with_title(self):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        out = _capture_console(fmt.print_result, {"k": "v"}, title="My Title")
        assert "My Title" in out

    def test_table_nested_value_json_serialized(self):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        out = _capture_console(fmt.print_result, {"items": [1, 2, 3]})
        assert "items" in out

    def test_table_dict_value_json_serialized(self):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        out = _capture_console(fmt.print_result, {"nested": {"a": 1}})
        assert "nested" in out


# ---------------------------------------------------------------------------
# Quiet mode
# ---------------------------------------------------------------------------


class TestQuietMode:
    """Tests for quiet mode suppression."""

    def test_print_result_suppressed(self):
        fmt = OutputFormatter(format=OutputFormat.JSON, quiet=True)
        out = _capture_stdout(fmt.print_result, {"key": "val"})
        assert out == ""

    def test_success_suppressed(self):
        fmt = OutputFormatter(quiet=True)
        out = _capture_console(fmt.success, "done")
        assert out == ""

    def test_error_suppressed(self):
        fmt = OutputFormatter(quiet=True)
        out = _capture_err_console(fmt.error, "fail")
        assert out == ""

    def test_warning_suppressed(self):
        fmt = OutputFormatter(quiet=True)
        out = _capture_console(fmt.warning, "warn")
        assert out == ""

    def test_info_suppressed(self):
        fmt = OutputFormatter(quiet=True, verbose=True)
        out = _capture_console(fmt.info, "detail")
        assert out == ""


# ---------------------------------------------------------------------------
# Delegating status methods
# ---------------------------------------------------------------------------


class TestStatusMethods:
    """Tests for success/error/warning/info delegation."""

    def test_success_in_table_mode(self):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        out = _capture_console(fmt.success, "All good")
        assert "All good" in out

    def test_success_suppressed_in_json_mode(self):
        fmt = OutputFormatter(format=OutputFormat.JSON)
        out = _capture_console(fmt.success, "hidden")
        assert out == ""

    def test_error_shown_in_any_format(self):
        for f in OutputFormat:
            fmt = OutputFormatter(format=f)
            out = _capture_err_console(fmt.error, "fail")
            assert "fail" in out, f"error not shown in {f.name} mode"

    def test_warning_in_table_mode(self):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        out = _capture_err_console(fmt.warning, "caution")
        assert "caution" in out

    def test_warning_suppressed_in_json_mode(self):
        fmt = OutputFormatter(format=OutputFormat.JSON)
        out = _capture_err_console(fmt.warning, "hidden")
        assert out == ""

    def test_info_requires_verbose(self):
        fmt = OutputFormatter(verbose=False)
        out = _capture_console(fmt.info, "hidden")
        assert out == ""

    def test_info_shown_when_verbose(self):
        fmt = OutputFormatter(verbose=True)
        out = _capture_console(fmt.info, "visible")
        assert "visible" in out
