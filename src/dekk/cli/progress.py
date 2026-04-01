"""
Progress indicators for CLI commands.

Rich imports are deferred to first use of progress_bar/spinner/StatusReporter.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.status import Status

__all__ = [
    "progress_bar",
    "spinner",
]


@contextmanager
def progress_bar(
    description: str,
    total: int | None = None,
) -> Generator[object, None, None]:
    """Context manager for deterministic progress with spinner, bar, %, and time."""
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    from dekk.cli.styles import _get_console

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
def spinner(description: str) -> Generator[Status, None, None]:
    """Context manager for an indeterminate spinner.

    Yields the Rich ``Status`` object so callers can update the displayed
    text via ``status.update("new message...")``.
    """
    from dekk.cli.styles import _get_console

    with _get_console().status(description, spinner="dots") as status:
        yield status
