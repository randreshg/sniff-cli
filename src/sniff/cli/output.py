"""Multi-format output handler for sniff CLI applications.

Provides :class:`OutputFormatter` which supports TABLE, JSON, YAML, and TEXT
output formats with quiet/verbose support, and delegates styled messages to
the functions defined in :mod:`sniff.cli.styles`.

Usage::

    from sniff.cli.output import OutputFormatter, OutputFormat

    fmt = OutputFormatter(format=OutputFormat.TABLE, verbose=True)
    fmt.print_result({"name": "sniff", "version": "3.0.0"}, title="Package Info")
    fmt.success("Build completed")
    fmt.error("Compilation failed")
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from sniff.cli.styles import (
    console,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)


class OutputFormat(str, Enum):
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
    mode, styled helpers from :mod:`sniff.cli.styles` are used for status
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
        console.print(table)

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
        if not self.quiet and self.verbose:
            print_info(msg)
