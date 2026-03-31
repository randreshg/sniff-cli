"""Multi-format output handler for dekk CLI applications.

Provides :class:`OutputFormatter` which supports TABLE, JSON, YAML, and TEXT
output formats with quiet/verbose support, and :func:`print_dep_results` for
displaying dependency check results in a consistent style.

Usage::

    from dekk.cli.output import OutputFormatter, OutputFormat, print_dep_results

    fmt = OutputFormatter(format=OutputFormat.TABLE, verbose=True)
    fmt.print_result({"name": "dekk", "version": "3.0.0"}, title="Package Info")
    fmt.success("Build completed")
    fmt.error("Compilation failed")

    # Dep-check display:
    from dekk import DependencyChecker, DependencySpec
    results = DependencyChecker().check_all([...])
    missing = print_dep_results(results)
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from dekk.cli.styles import (
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)

if TYPE_CHECKING:
    from dekk.detection.deps import DependencyResult


class OutputFormat(StrEnum):
    """Output format options for CLI commands.

    Attributes:
        TABLE: Rich-formatted table output (default, human-friendly).
        JSON: Machine-readable JSON output.
        YAML: Machine-readable YAML output.
        TEXT: Plain key-value text output (no Rich markup).
    """

    TABLE = "table"
    JSON = "json"
    YAML = "yaml"
    TEXT = "text"


class OutputFormatter:
    """Multi-format output handler with quiet/verbose support.

    The formatter routes output through the appropriate serialisation
    backend based on the configured :class:`OutputFormat`.  In ``TABLE``
    mode, styled helpers from :mod:`dekk.cli.styles` are used for status
    messages; in ``JSON`` / ``YAML`` mode, data is emitted as structured
    documents to stdout so that downstream tools can parse them.

    Args:
        format: The output format to use.
        quiet: When ``True``, suppress non-essential output.
        verbose: When ``True``, show additional informational messages.
    """

    def __init__(
        self,
        format: OutputFormat = OutputFormat.TABLE,
        quiet: bool = False,
        verbose: bool = False,
    ) -> None:
        self.format = format
        self.quiet = quiet
        self.verbose = verbose

    # ------------------------------------------------------------------
    # Primary output method
    # ------------------------------------------------------------------

    def print_result(self, data: dict[str, Any], title: str | None = None) -> None:
        """Print a result dictionary in the configured format.

        Args:
            data: Key-value data to display.
            title: Optional title shown above the result (TABLE mode only).
        """
        if self.quiet:
            return

        if self.format == OutputFormat.JSON:
            print(json.dumps(data, indent=2, default=str))
        elif self.format == OutputFormat.YAML:
            import yaml

            print(yaml.dump(data, default_flow_style=False, sort_keys=False), end="")
        elif self.format == OutputFormat.TABLE:
            if title:
                print_header(title)
            self._print_table(data)
        else:  # TEXT
            for key, value in data.items():
                print(f"{key}: {value}")

    # ------------------------------------------------------------------
    # Table helper
    # ------------------------------------------------------------------

    def _print_table(self, data: dict[str, Any]) -> None:
        """Render *data* as a two-column Rich key-value table.

        Nested structures (dicts, lists) are serialised to JSON strings
        for readability.

        Args:
            data: Key-value mapping to display.
        """
        from rich.table import Table

        table = Table(show_header=False)
        table.add_column("Key", style="bold")
        table.add_column("Value", style="cyan")
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, indent=2, default=str)
            else:
                value_str = str(value)
            table.add_row(str(key), value_str)
        from dekk.cli.styles import _get_console

        _get_console().print(table)

    # ------------------------------------------------------------------
    # Delegating status methods
    # ------------------------------------------------------------------

    def success(self, msg: str) -> None:
        """Print a success message (suppressed in quiet mode or non-TABLE formats).

        Args:
            msg: The success message to display.
        """
        if not self.quiet and self.format == OutputFormat.TABLE:
            print_success(msg)

    def error(self, msg: str) -> None:
        """Print an error message (always shown unless quiet, regardless of format).

        Args:
            msg: The error message to display.
        """
        if not self.quiet:
            print_error(msg)

    def warning(self, msg: str) -> None:
        """Print a warning message (suppressed in quiet mode or non-TABLE formats).

        Args:
            msg: The warning message to display.
        """
        if not self.quiet and self.format == OutputFormat.TABLE:
            print_warning(msg)

    def info(self, msg: str) -> None:
        """Print an informational message (only shown in verbose TABLE mode).

        Args:
            msg: The informational message to display.
        """
        if not self.quiet and self.verbose and self.format == OutputFormat.TABLE:
            print_info(msg)


# ---------------------------------------------------------------------------
# Dependency check display
# ---------------------------------------------------------------------------


def print_dep_results(
    results: list[DependencyResult],
    *,
    skip_names: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Print dependency check results and return a list of blocking issues.

    Iterates over a list of :class:`~dekk.detection.deps.DependencyResult` objects,
    prints a success/warning/error line for each one, and collects the names
    of required dependencies that are missing or need upgrading so the caller
    can include them in an action-required summary.

    Args:
        results: Iterable of ``DependencyResult`` objects (from
            :class:`~dekk.detection.deps.DependencyChecker`).
        skip_names: Optional set of dependency *names* whose failures should
            not be added to the returned missing list. Use this when a later
            install stage will handle those deps in detail in a consumer CLI.

    Returns:
        List of human-readable strings describing missing or broken
        dependencies, ready to pass to :func:`~dekk.cli.styles.print_numbered_list`.

    Example::

        from dekk import DependencyChecker, print_dep_results

        results = DependencyChecker().check_all(specs)
        missing = print_dep_results(results, skip_names={"Mamba/Conda", "Rust"})
        if missing:
            print_numbered_list(missing)
    """
    skip = skip_names or set()
    missing: list[str] = []

    for r in results:
        v = f" ({r.version})" if r.version else ""
        if r.found:
            if r.meets_minimum:
                print_success(f"{r.name}{v}")
            else:
                print_warning(f"{r.name}{v} -- needs upgrade")
                if r.name not in skip:
                    missing.append(f"{r.name} (upgrade required)")
        else:
            if r.required:
                print_error(f"{r.name} -- not found")
                if r.name not in skip:
                    missing.append(r.name)
            else:
                print_warning(f"{r.name} -- not found (optional)")

    return missing
