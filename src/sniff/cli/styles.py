"""Unified styling and output functions for sniff CLI applications.

Provides semantic color styles, Unicode status symbols, and 12 core output
functions that cover 89% of all CLI output across APXM and Tully codebases.

Usage::

    from sniff.cli.styles import print_success, print_error, print_info, Colors

    print_success("Build completed")
    print_error("Compilation failed")
    print_info("Using conda environment: base")
"""

from __future__ import annotations

from enum import Enum

from rich.console import Console
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Theme & Global Consoles
# ---------------------------------------------------------------------------

CLI_THEME = Theme(
    {
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "cyan",
        "debug": "dim",
        "header": "bold cyan",
        "step": "bold blue",
        "dim": "dim",
        "highlight": "bold white",
    }
)
"""Rich Theme with semantic styles for CLI output."""

console = Console(theme=CLI_THEME)
"""Global Rich Console for standard output."""

err_console = Console(theme=CLI_THEME, stderr=True)
"""Global Rich Console for error/warning output (writes to stderr)."""

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Colors(str, Enum):
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


class Symbols:
    """Unicode symbols for status indicators.

    These are used as prefix icons in the ``print_*`` helper functions.
    """

    PASS = "\u2713"      # checkmark
    FAIL = "\u2717"      # ballot x
    SKIP = "\u25cb"      # white circle
    TIMEOUT = "\u23f1"   # stopwatch
    RUNNING = "\u25cf"   # black circle
    INFO = "\u2139"      # information source
    WARNING = "\u26a0"   # warning sign

# ---------------------------------------------------------------------------
# Status Messages (89% of all CLI output)
# ---------------------------------------------------------------------------


def print_success(msg: str) -> None:
    """Print a success message with a green checkmark icon.

    Args:
        msg: The message to display.
    """
    icon = f"[{Colors.SUCCESS}]{Symbols.PASS}[/{Colors.SUCCESS}]"
    console.print(f"  {icon} {msg}")


def print_error(msg: str) -> None:
    """Print an error message with a red X icon to stderr.

    Args:
        msg: The error message to display.
    """
    icon = f"[{Colors.ERROR}]{Symbols.FAIL}[/{Colors.ERROR}]"
    err_console.print(f"  {icon} {msg}")


def print_warning(msg: str) -> None:
    """Print a warning message with a warning icon to stderr.

    Args:
        msg: The warning message to display.
    """
    icon = f"[{Colors.WARNING}]{Symbols.WARNING}[/{Colors.WARNING}]"
    err_console.print(f"  {icon} {msg}")


def print_info(msg: str) -> None:
    """Print an informational message with an info icon.

    Args:
        msg: The informational message to display.
    """
    icon = f"[{Colors.INFO}]{Symbols.INFO}[/{Colors.INFO}]"
    console.print(f"  {icon} {msg}")


def print_debug(msg: str) -> None:
    """Print a debug message in dimmed style.

    Args:
        msg: The debug message to display.
    """
    console.print(f"  [{Colors.DEBUG}]{Symbols.SKIP} {msg}[/{Colors.DEBUG}]")

# ---------------------------------------------------------------------------
# Structural Elements
# ---------------------------------------------------------------------------


def print_header(title: str, subtitle: str | None = None) -> None:
    """Print a header panel with a heavy border.

    Args:
        title: The header title text.
        subtitle: Optional subtitle displayed below the title in dim style.
    """
    from rich import box
    from rich.panel import Panel

    text = f"[{Colors.HEADER}]{title}[/{Colors.HEADER}]"
    if subtitle:
        text += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel(text, box=box.HEAVY, border_style="cyan"))


def print_step(msg: str, step_num: int | None = None, total: int | None = None) -> None:
    """Print a step indicator with an optional ``[N/M]`` prefix.

    Args:
        msg: The step description.
        step_num: Current step number (requires *total* as well).
        total: Total number of steps (requires *step_num* as well).
    """
    prefix = ""
    if step_num is not None and total is not None:
        prefix = f"[{Colors.STEP}][{step_num}/{total}][/{Colors.STEP}] "
    console.print(f"{prefix}[{Colors.STEP}]\u25b6[/{Colors.STEP}] {msg}")


def print_section(title: str) -> None:
    """Print a section divider (bold text preceded by a blank line).

    Args:
        title: The section title.
    """
    console.print(f"\n[bold]{title}[/bold]")


def print_blank() -> None:
    """Print a blank line for visual spacing."""
    console.print()

# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def print_table(title: str, headers: list[str], rows: list[list[str]]) -> None:
    """Print a formatted Rich table with rounded borders.

    Args:
        title: Table title displayed above the table.
        headers: Column header labels.
        rows: List of rows, where each row is a list of cell values.
    """
    from rich import box
    from rich.table import Table

    table = Table(title=title, box=box.ROUNDED, header_style="bold cyan")
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*row)
    console.print(table)


def print_numbered_list(items: list[str]) -> None:
    """Print a numbered list of items.

    Args:
        items: The items to number and display.
    """
    for i, item in enumerate(items, 1):
        console.print(f"  {i}. {item}")


def print_next_steps(steps: list[str]) -> None:
    """Print a 'Next steps:' block with a numbered list.

    Args:
        steps: List of recommended next actions.
    """
    console.print("\n[bold]Next steps:[/bold]")
    print_numbered_list(steps)
