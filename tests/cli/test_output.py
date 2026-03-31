"""Tests for dekk.cli.output -- OutputFormat, OutputFormatter, print_dep_results."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from unittest.mock import patch

from dekk.cli.output import OutputFormat, OutputFormatter, print_dep_results

# ---------------------------------------------------------------------------
# Minimal DependencyResult stub (avoids importing dekk.detection.deps to keep tests fast)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DepResult:
    name: str
    command: str
    found: bool
    version: str | None = None
    meets_minimum: bool = True
    required: bool = True
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_stdout(fn, *args, **kwargs) -> str:
    """Capture stdout (print()) output."""
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        fn(*args, **kwargs)
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
        out = _capture_stdout(fmt.print_result, {"name": "dekk", "version": "3.0.0"})
        parsed = json.loads(out)
        assert parsed == {"name": "dekk", "version": "3.0.0"}

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
        assert parsed == {"x": 1}
        assert "Ignored Title" not in out


# ---------------------------------------------------------------------------
# print_result -- YAML
# ---------------------------------------------------------------------------


class TestPrintResultYAML:
    """Tests for print_result in YAML mode."""

    def test_yaml_output(self):
        import yaml

        fmt = OutputFormatter(format=OutputFormat.YAML)
        out = _capture_stdout(fmt.print_result, {"name": "dekk"})
        parsed = yaml.safe_load(out)
        assert parsed == {"name": "dekk"}

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
        out = _capture_stdout(fmt.print_result, {"name": "dekk", "version": "3.0.0"})
        assert "name: dekk" in out
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

    def test_table_contains_values(self, capture_console):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        with capture_console() as buf:
            fmt.print_result({"name": "dekk"})
        out = buf.getvalue()
        assert "name" in out
        assert "dekk" in out

    def test_table_with_title(self, capture_console):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        with capture_console() as buf:
            fmt.print_result({"k": "v"}, title="My Title")
        assert "My Title" in buf.getvalue()

    def test_table_nested_value_json_serialized(self, capture_console):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        with capture_console() as buf:
            fmt.print_result({"items": [1, 2, 3]})
        assert "items" in buf.getvalue()

    def test_table_dict_value_json_serialized(self, capture_console):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        with capture_console() as buf:
            fmt.print_result({"nested": {"a": 1}})
        assert "nested" in buf.getvalue()


# ---------------------------------------------------------------------------
# Quiet mode
# ---------------------------------------------------------------------------


class TestQuietMode:
    """Tests for quiet mode suppression."""

    def test_print_result_suppressed(self):
        fmt = OutputFormatter(format=OutputFormat.JSON, quiet=True)
        out = _capture_stdout(fmt.print_result, {"key": "val"})
        assert out == ""

    def test_success_suppressed(self, capture_console):
        fmt = OutputFormatter(quiet=True)
        with capture_console() as buf:
            fmt.success("done")
        assert buf.getvalue() == ""

    def test_error_suppressed(self, capture_err_console):
        fmt = OutputFormatter(quiet=True)
        with capture_err_console() as buf:
            fmt.error("fail")
        assert buf.getvalue() == ""

    def test_warning_suppressed(self, capture_console):
        fmt = OutputFormatter(quiet=True)
        with capture_console() as buf:
            fmt.warning("warn")
        assert buf.getvalue() == ""

    def test_info_suppressed(self, capture_console):
        fmt = OutputFormatter(quiet=True, verbose=True)
        with capture_console() as buf:
            fmt.info("detail")
        assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# Delegating status methods
# ---------------------------------------------------------------------------


class TestStatusMethods:
    """Tests for success/error/warning/info delegation."""

    def test_success_in_table_mode(self, capture_console):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        with capture_console() as buf:
            fmt.success("All good")
        assert "All good" in buf.getvalue()

    def test_success_suppressed_in_json_mode(self, capture_console):
        fmt = OutputFormatter(format=OutputFormat.JSON)
        with capture_console() as buf:
            fmt.success("hidden")
        assert buf.getvalue() == ""

    def test_error_shown_in_any_format(self, capture_err_console):
        for f in OutputFormat:
            fmt = OutputFormatter(format=f)
            with capture_err_console() as buf:
                fmt.error("fail")
            assert "fail" in buf.getvalue(), f"error not shown in {f.name} mode"

    def test_warning_in_table_mode(self, capture_err_console):
        fmt = OutputFormatter(format=OutputFormat.TABLE)
        with capture_err_console() as buf:
            fmt.warning("caution")
        assert "caution" in buf.getvalue()

    def test_warning_suppressed_in_json_mode(self, capture_err_console):
        fmt = OutputFormatter(format=OutputFormat.JSON)
        with capture_err_console() as buf:
            fmt.warning("hidden")
        assert buf.getvalue() == ""

    def test_info_requires_verbose(self, capture_console):
        fmt = OutputFormatter(verbose=False)
        with capture_console() as buf:
            fmt.info("hidden")
        assert buf.getvalue() == ""

    def test_info_shown_when_verbose(self, capture_console):
        fmt = OutputFormatter(verbose=True)
        with capture_console() as buf:
            fmt.info("visible")
        assert "visible" in buf.getvalue()


# ---------------------------------------------------------------------------
# print_dep_results
# ---------------------------------------------------------------------------


class TestPrintDepResults:
    """Tests for the print_dep_results() helper."""

    def test_returns_empty_list_when_all_ok(self):
        results = [
            _DepResult(name="cmake", command="cmake", found=True, version="3.28.0"),
            _DepResult(name="git", command="git", found=True, version="2.44.0"),
        ]
        missing = print_dep_results(results)
        assert missing == []

    def test_required_missing_dep_in_returned_list(self):
        results = [_DepResult(name="cmake", command="cmake", found=False, required=True)]
        missing = print_dep_results(results)
        assert "cmake" in missing

    def test_optional_missing_dep_not_in_returned_list(self):
        results = [_DepResult(name="ninja", command="ninja", found=False, required=False)]
        missing = print_dep_results(results)
        assert missing == []

    def test_needs_upgrade_in_returned_list(self):
        results = [
            _DepResult(
                name="cmake", command="cmake", found=True, version="3.10.0", meets_minimum=False
            )
        ]
        missing = print_dep_results(results)
        assert any("cmake" in m for m in missing)
        assert any("upgrade" in m.lower() for m in missing)

    def test_skip_names_excludes_from_missing(self):
        results = [
            _DepResult(name="Rust", command="rustc", found=False, required=True),
            _DepResult(name="cmake", command="cmake", found=False, required=True),
        ]
        missing = print_dep_results(results, skip_names={"Rust"})
        assert not any("Rust" in m for m in missing)
        assert any("cmake" in m for m in missing)

    def test_skip_names_none_includes_all(self):
        results = [
            _DepResult(name="Rust", command="rustc", found=False, required=True),
        ]
        missing = print_dep_results(results, skip_names=None)
        assert any("Rust" in m for m in missing)

    def test_success_prints_to_stdout(self):
        results = [_DepResult(name="git", command="git", found=True, version="2.44.0")]
        with patch("dekk.cli.output.print_success") as mock_ok:
            print_dep_results(results)
        mock_ok.assert_called_once()
        assert "git" in mock_ok.call_args[0][0]

    def test_missing_required_prints_error(self):
        results = [_DepResult(name="cmake", command="cmake", found=False, required=True)]
        with patch("dekk.cli.output.print_error") as mock_err:
            print_dep_results(results)
        mock_err.assert_called_once()

    def test_missing_optional_prints_warning(self):
        results = [_DepResult(name="ninja", command="ninja", found=False, required=False)]
        with patch("dekk.cli.output.print_warning") as mock_warn:
            print_dep_results(results)
        mock_warn.assert_called_once()

    def test_needs_upgrade_prints_warning(self):
        results = [
            _DepResult(
                name="cmake", command="cmake", found=True, version="3.10.0", meets_minimum=False
            )
        ]
        with patch("dekk.cli.output.print_warning") as mock_warn:
            print_dep_results(results)
        mock_warn.assert_called_once()

    def test_version_shown_when_present(self):
        results = [_DepResult(name="git", command="git", found=True, version="2.44.0")]
        with patch("dekk.cli.output.print_success") as mock_ok:
            print_dep_results(results)
        assert "2.44.0" in mock_ok.call_args[0][0]

    def test_no_version_does_not_crash(self):
        results = [_DepResult(name="cmake", command="cmake", found=True, version=None)]
        missing = print_dep_results(results)
        assert missing == []

    def test_empty_results(self):
        assert print_dep_results([]) == []

    def test_frozenset_skip_names_accepted(self):
        results = [_DepResult(name="Rust", command="rustc", found=False, required=True)]
        missing = print_dep_results(results, skip_names=frozenset({"Rust"}))
        assert missing == []
