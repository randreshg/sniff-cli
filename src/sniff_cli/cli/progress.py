"""
Progress indicators for CLI commands.

Rich imports are deferred to first use of progress_bar/spinner/StatusReporter.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

__all__ = [
    "progress_bar",
    "spinner",
]


@contextmanager
def progress_bar(
    description: str,
    total: int | None = None,
) -> Generator:
    """Context manager for deterministic progress with spinner, bar, %, and time."""
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from sniff_cli.cli.styles import _get_console

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=_get_console(),
        transient=True,
    ) as progress:
        progress.add_task(description, total=total)
        yield progress


@contextmanager
def spinner(description: str) -> Generator[None, None, None]:
    """Context manager for an indeterminate spinner."""
    from sniff_cli.cli.styles import _get_console

    with _get_console().status(description, spinner="dots"):
        yield
