"""
Progress indicators for CLI commands.

Provides three patterns for tracking progress in long-running operations:

- :func:`progress_bar` -- Deterministic progress with spinner, bar, percentage,
  and elapsed time. Use when you know the total number of items.
- :func:`spinner` -- Indeterminate spinner for operations with unknown duration.
- :class:`StatusReporter` -- Sequential step tracker that prints semantic status
  messages (start, success, error, warning, info) for multi-step workflows.

All three integrate with the global :data:`sniff.cli.styles.console` and reuse
the project's semantic output functions so that output is visually consistent
with the rest of the CLI.

Example usage::

    # Deterministic progress
    with progress_bar("Compiling modules", total=42) as progress:
        task = progress.tasks[0]
        for i in range(42):
            progress.update(task.id, advance=1)

    # Indeterminate spinner
    with spinner("Resolving dependencies..."):
        do_long_operation()

    # Multi-step status reporting
    reporter = StatusReporter("Installation")
    reporter.start("Checking conda environment")
    reporter.success("Environment validated")
    reporter.start("Building compiler")
    reporter.error("Build failed: missing libz")
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from sniff.cli.styles import (
    console,
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
    print_warning,
)

__all__ = [
    "progress_bar",
    "spinner",
    "StatusReporter",
]


@contextmanager
def progress_bar(
    description: str,
    total: int | None = None,
) -> Generator[Progress, None, None]:
    """Context manager for deterministic progress with spinner, bar, %, and time.

    Creates a :class:`rich.progress.Progress` bar pre-configured with a spinner,
    description text, a bar column, percentage, and elapsed time.  A task is
    automatically added using *description* and *total* so callers can
    immediately retrieve it via ``progress.tasks[0]``.

    Args:
        description: Human-readable label displayed next to the bar.
        total: Total number of work units.  Pass ``None`` for indeterminate
            progress (the bar will pulse).

    Yields:
        The :class:`~rich.progress.Progress` instance.  Use
        ``progress.update(task_id, advance=N)`` to advance.

    Example::

        with progress_bar("Building...", total=100) as progress:
            task = progress.tasks[0]
            for i in range(100):
                progress.update(task.id, advance=1)
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(description, total=total)
        yield progress


@contextmanager
def spinner(description: str) -> Generator[None, None, None]:
    """Context manager for an indeterminate spinner.

    Displays an animated dots spinner with *description* text.  Useful for
    operations whose duration is unknown (network calls, dependency resolution,
    etc.).  The spinner is removed from the terminal when the block exits.

    Args:
        description: Text displayed next to the spinner animation.

    Yields:
        ``None``.  The spinner runs automatically for the duration of the
        ``with`` block.

    Example::

        with spinner("Resolving dependencies..."):
            resolve_all()
    """
    with console.status(description, spinner="dots"):
        yield


class StatusReporter:
    """Sequential step tracker for multi-step operations.

    Prints a header on creation, then lets callers report the start and
    outcome of each step using the project's semantic output functions
    (:func:`print_step`, :func:`print_success`, etc.) so that all output
    uses a consistent style.

    Args:
        title: Header text printed when the reporter is created.

    Example::

        reporter = StatusReporter("Deployment")
        reporter.start("Checking prerequisites")
        reporter.success("All prerequisites met")
        reporter.start("Uploading artifacts")
        reporter.warning("Slow network detected")
        reporter.success("Upload complete")
    """

    def __init__(self, title: str) -> None:
        self.title = title
        print_header(title)

    def start(self, msg: str) -> None:
        """Report the start of a new step.

        Args:
            msg: Description of the step being started.
        """
        print_step(msg)

    def success(self, msg: str) -> None:
        """Mark the current step as successful.

        Args:
            msg: Success message.
        """
        print_success(msg)

    def error(self, msg: str) -> None:
        """Mark the current step as failed.

        Args:
            msg: Error message.
        """
        print_error(msg)

    def warning(self, msg: str) -> None:
        """Issue a warning for the current step.

        Args:
            msg: Warning message.
        """
        print_warning(msg)

    def info(self, msg: str) -> None:
        """Provide additional information about the current step.

        Args:
            msg: Informational message.
        """
        print_info(msg)
