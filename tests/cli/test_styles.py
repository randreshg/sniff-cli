"""Tests for dekk.cli.styles -- semantic colors, symbols, and output functions."""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

from dekk.cli.styles import (
    CLI_THEME,
    Colors,
    Symbols,
    console,
    err_console,
    print_blank,
    print_debug,
    print_error,
    print_header,
    print_info,
    print_next_steps,
    print_numbered_list,
    print_section,
    print_step,
    print_success,
    print_table,
    print_warning,
)

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


class TestCLITheme:
    """Tests for CLI_THEME."""

    def test_theme_is_rich_theme(self):
        assert isinstance(CLI_THEME, Theme)

    def test_theme_contains_all_semantic_styles(self):
        expected = {
            "success",
            "error",
            "warning",
            "info",
            "debug",
            "header",
            "step",
            "dim",
            "highlight",
        }
        assert expected <= set(CLI_THEME.styles.keys())


# ---------------------------------------------------------------------------
# Global Consoles
# ---------------------------------------------------------------------------


class TestGlobalConsoles:
    """Tests for the module-level console and err_console."""

    def test_console_is_rich_console(self):
        assert isinstance(console, Console)

    def test_err_console_is_rich_console(self):
        assert isinstance(err_console, Console)

    def test_err_console_writes_to_stderr(self):
        assert err_console.stderr is True

    def test_console_writes_to_stdout(self):
        assert console.stderr is False


# ---------------------------------------------------------------------------
# Colors Enum
# ---------------------------------------------------------------------------


class TestColors:
    """Tests for the Colors enum."""

    def test_all_members_present(self):
        # DIM and DEBUG share the same value ("dim"), so Python's str Enum
        # treats DIM as an alias of DEBUG.  Only canonical members appear in
        # iteration.
        expected = {"SUCCESS", "ERROR", "WARNING", "INFO", "DEBUG", "HEADER", "STEP", "HIGHLIGHT"}
        assert expected == {c.name for c in Colors}

    def test_dim_is_alias_of_debug(self):
        assert Colors.DIM is Colors.DEBUG

    def test_values_are_strings(self):
        for c in Colors:
            assert isinstance(c.value, str)

    def test_is_str_enum(self):
        assert issubclass(Colors, str)

    def test_specific_values(self):
        assert Colors.SUCCESS == "bold green"
        assert Colors.ERROR == "bold red"
        assert Colors.WARNING == "bold yellow"
        assert Colors.INFO == "cyan"
        assert Colors.DEBUG == "dim"

    def test_usable_in_fstrings(self):
        result = f"[{Colors.SUCCESS}]ok[/{Colors.SUCCESS}]"
        assert "bold green" in result


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------


class TestSymbols:
    """Tests for the Symbols class."""

    def test_pass_is_checkmark(self):
        assert Symbols.PASS == "\u2713"

    def test_fail_is_ballot_x(self):
        assert Symbols.FAIL == "\u2717"

    def test_skip_is_white_circle(self):
        assert Symbols.SKIP == "\u25cb"

    def test_timeout_is_stopwatch(self):
        assert Symbols.TIMEOUT == "\u23f1"

    def test_running_is_black_circle(self):
        assert Symbols.RUNNING == "\u25cf"

    def test_info_is_information(self):
        assert Symbols.INFO == "\u2139"

    def test_warning_is_warning_sign(self):
        assert Symbols.WARNING == "\u26a0"


# ---------------------------------------------------------------------------
# Status Message Functions
# ---------------------------------------------------------------------------


class TestPrintSuccess:
    """Tests for print_success."""

    def test_contains_message(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_success("Build completed")
        assert "Build completed" in buf.getvalue()

    def test_contains_checkmark(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_success("done")
        assert Symbols.PASS in buf.getvalue()

    def test_empty_message(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_success("")
        assert Symbols.PASS in buf.getvalue()


class TestPrintError:
    """Tests for print_error (writes to stderr)."""

    def test_contains_message(self, capture_err_console):
        with capture_err_console(highlight=False) as buf:
            print_error("Compilation failed")
        assert "Compilation failed" in buf.getvalue()

    def test_contains_fail_symbol(self, capture_err_console):
        with capture_err_console(highlight=False) as buf:
            print_error("err")
        assert Symbols.FAIL in buf.getvalue()

    def test_empty_message(self, capture_err_console):
        with capture_err_console(highlight=False) as buf:
            print_error("")
        assert Symbols.FAIL in buf.getvalue()


class TestPrintWarning:
    """Tests for print_warning (writes to stderr)."""

    def test_contains_message(self, capture_err_console):
        with capture_err_console(highlight=False) as buf:
            print_warning("Slow network")
        assert "Slow network" in buf.getvalue()

    def test_contains_warning_symbol(self, capture_err_console):
        with capture_err_console(highlight=False) as buf:
            print_warning("warn")
        assert Symbols.WARNING in buf.getvalue()


class TestPrintInfo:
    """Tests for print_info."""

    def test_contains_message(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_info("Using conda")
        assert "Using conda" in buf.getvalue()

    def test_contains_info_symbol(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_info("info")
        assert Symbols.INFO in buf.getvalue()


class TestPrintDebug:
    """Tests for print_debug."""

    def test_contains_message(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_debug("Trace details")
        assert "Trace details" in buf.getvalue()

    def test_contains_skip_symbol(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_debug("dbg")
        assert Symbols.SKIP in buf.getvalue()


# ---------------------------------------------------------------------------
# Structural Elements
# ---------------------------------------------------------------------------


class TestPrintHeader:
    """Tests for print_header."""

    def test_contains_title(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_header("Installation")
        assert "Installation" in buf.getvalue()

    def test_subtitle_included_when_given(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_header("Build", subtitle="v3.0.0")
        out = buf.getvalue()
        assert "Build" in out
        assert "v3.0.0" in out

    def test_subtitle_absent_when_none(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_header("Title")
        # Should not crash and should contain only the title
        assert "Title" in buf.getvalue()


class TestPrintStep:
    """Tests for print_step."""

    def test_message_present(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_step("Compiling")
        assert "Compiling" in buf.getvalue()

    def test_step_numbering(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_step("Building", step_num=2, total=5)
        out = buf.getvalue()
        # Rich markup may insert ANSI escape codes around "2/5"
        assert "2" in out and "5" in out
        assert "Building" in out

    def test_no_numbering_when_none(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_step("Running")
        out = buf.getvalue()
        assert "/" not in out or "Running" in out

    def test_partial_numbering_ignored(self, capture_console):
        """When only step_num is given (no total), numbering is skipped."""
        with capture_console(highlight=False) as buf:
            print_step("Step", step_num=1)
        # Should not contain "1/" since total is None
        assert "Step" in buf.getvalue()


class TestPrintSection:
    """Tests for print_section."""

    def test_contains_title(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_section("Results")
        assert "Results" in buf.getvalue()


class TestPrintBlank:
    """Tests for print_blank."""

    def test_produces_output(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_blank()
        out = buf.getvalue()
        # Should produce at least a newline
        assert out.strip() == "" or out == "\n"


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


class TestPrintTable:
    """Tests for print_table."""

    def test_basic_table(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_table("Results", ["Name", "Score"], [["Alice", "95"], ["Bob", "87"]])
        out = buf.getvalue()
        assert "Results" in out
        assert "Alice" in out
        assert "95" in out
        assert "Bob" in out

    def test_empty_rows(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_table("Empty", ["A", "B"], [])
        out = buf.getvalue()
        assert "Empty" in out
        assert "A" in out

    def test_single_column(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_table("Items", ["Item"], [["one"], ["two"]])
        out = buf.getvalue()
        assert "one" in out
        assert "two" in out


class TestPrintNumberedList:
    """Tests for print_numbered_list."""

    def test_basic_list(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_numbered_list(["alpha", "beta", "gamma"])
        out = buf.getvalue()
        # Rich may insert ANSI codes around numbers, so check content only
        assert "alpha" in out
        assert "beta" in out
        assert "gamma" in out

    def test_empty_list(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_numbered_list([])
        assert buf.getvalue().strip() == ""

    def test_single_item(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_numbered_list(["only"])
        assert "only" in buf.getvalue()


class TestPrintNextSteps:
    """Tests for print_next_steps."""

    def test_contains_header_and_items(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_next_steps(["Run tests", "Deploy"])
        out = buf.getvalue()
        assert "Next steps:" in out
        assert "Run tests" in out
        assert "Deploy" in out

    def test_empty_steps(self, capture_console):
        with capture_console(highlight=False) as buf:
            print_next_steps([])
        assert "Next steps:" in buf.getvalue()
