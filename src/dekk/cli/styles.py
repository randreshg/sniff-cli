"""Unified styling and output functions for dekk CLI applications.

Provides semantic color styles, Unicode status symbols, and 12 core output
functions that cover 89% of all CLI output across APXM and Tully codebases.

Rich is imported lazily on first use of any print_* function or console access,
so importing this module alone does NOT pull in Rich.

Usage::

    from dekk.cli.styles import print_success, print_error, print_info, Colors

    print_success("Build completed")
    print_error("Compilation failed")
    print_info("Using conda environment: base")
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.console import Console
    from rich.theme import Theme

# ---------------------------------------------------------------------------
# Enums (pure Python, no Rich dependency)
# ---------------------------------------------------------------------------


class Colors(StrEnum):
    """Semantic color styles for CLI output.

    Values are Rich markup style strings that can be used directly in
    ``console.print(f"[{Colors.SUCCESS}]text[/{Colors.SUCCESS}]")``.
    """

    SUCCESS = "bold green"
    ERROR = "bold red"
    WARNING = "bold yellow"
    INFO = "cyan"
    DEBUG = "dim"
    HEADER = "bold cyan"
    STEP = "bold blue"
    DIM = "dim"
    HIGHLIGHT = "bold white"

    def __format__(self, format_spec: str) -> str:
        return self.value.__format__(format_spec)


class Symbols:
    """Unicode symbols for status indicators.

    These are used as prefix icons in the ``print_*`` helper functions.
    """

    PASS = "\u2713"  # checkmark
    FAIL = "\u2717"  # ballot x
    SKIP = "\u25cb"  # white circle
    TIMEOUT = "\u23f1"  # stopwatch
    RUNNING = "\u25cf"  # black circle
    INFO = "\u2139"  # information source
    WARNING = "\u26a0"  # warning sign


# ---------------------------------------------------------------------------
# Lazy Rich console singletons
# ---------------------------------------------------------------------------

_console: Console | None = None
_err_console: Console | None = None
_cli_theme: Theme | None = None


def _get_theme() -> Theme:
    global _cli_theme
    if _cli_theme is None:
        from rich.theme import Theme

        _cli_theme = Theme({c.name.lower(): c.value for c in Colors})
    return _cli_theme


def _get_console() -> Console:
    global _console
    if _console is None:
        from rich.console import Console

        _console = Console(theme=_get_theme())
    return _console


def _get_err_console() -> Console:
    global _err_console
    if _err_console is None:
        from rich.console import Console

        _err_console = Console(theme=_get_theme(), stderr=True)
    return _err_console


# Module-level __getattr__ for lazy access to console, err_console, CLI_THEME
def __getattr__(name: str) -> Any:  # noqa: N807
    if name == "console":
        console_value = _get_console()
        globals()["console"] = console_value
        return console_value
    if name == "err_console":
        err_console_value = _get_err_console()
        globals()["err_console"] = err_console_value
        return err_console_value
    if name == "CLI_THEME":
        theme_value = _get_theme()
        globals()["CLI_THEME"] = theme_value
        return theme_value
    raise AttributeError(f"module 'dekk.cli.styles' has no attribute {name!r}")


# ---------------------------------------------------------------------------
# Status Messages (89% of all CLI output)
# ---------------------------------------------------------------------------


def print_success(msg: str) -> None:
    """Print a success message with a green checkmark icon."""
    icon = f"[{Colors.SUCCESS}]{Symbols.PASS}[/]"
    _get_console().print(f"  {icon} {msg}")


def print_error(msg: str) -> None:
    """Print an error message with a red X icon to stderr."""
    icon = f"[{Colors.ERROR}]{Symbols.FAIL}[/]"
    _get_err_console().print(f"  {icon} {msg}")


def print_warning(msg: str) -> None:
    """Print a warning message with a warning icon to stderr."""
    icon = f"[{Colors.WARNING}]{Symbols.WARNING}[/]"
    _get_err_console().print(f"  {icon} {msg}")


def print_info(msg: str) -> None:
    """Print an informational message with an info icon."""
    icon = f"[{Colors.INFO}]{Symbols.INFO}[/]"
    _get_console().print(f"  {icon} {msg}")


def print_debug(msg: str) -> None:
    """Print a debug message in dimmed style."""
    _get_console().print(f"  [{Colors.DEBUG}]{Symbols.SKIP} {msg}[/]")


# ---------------------------------------------------------------------------
# Structural Elements
# ---------------------------------------------------------------------------


def print_header(title: str, subtitle: str | None = None) -> None:
    """Print a header with minimal token usage."""
    c = _get_console()
    c.print()
    c.print(f"[{Colors.HEADER}]{title}[/]")
    if subtitle:
        c.print(f"[dim]{subtitle}[/]")
    c.print(f"[dim]{'─' * 40}[/]")


def print_step(msg: str, step_num: int | None = None, total: int | None = None) -> None:
    """Print a step indicator with an optional ``[N/M]`` prefix."""
    prefix = ""
    if step_num is not None and total is not None:
        prefix = f"[{Colors.STEP}][{step_num}/{total}][/] "
    _get_console().print(f"{prefix}[{Colors.STEP}]\u25b6[/] {msg}")


def print_section(title: str) -> None:
    """Print a section divider (bold text preceded by a blank line)."""
    _get_console().print(f"\n[bold]{title}[/]")


def print_blank() -> None:
    """Print a blank line for visual spacing."""
    _get_console().print()


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def print_table(title: str, headers: list[str], rows: list[list[str]]) -> None:
    """Print a formatted Rich table with minimal borders."""
    from rich import box
    from rich.table import Table

    table = Table(title=title, box=box.SIMPLE, header_style="bold cyan", show_edge=False)
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*row)
    _get_console().print(table)


def print_numbered_list(items: list[str]) -> None:
    """Print a numbered list of items."""
    c = _get_console()
    for i, item in enumerate(items, 1):
        c.print(f"  {i}. {item}")


def print_next_steps(steps: list[str]) -> None:
    """Print a 'Next steps:' block with a numbered list."""
    _get_console().print("\n[bold]Next steps:[/]")
    print_numbered_list(steps)
