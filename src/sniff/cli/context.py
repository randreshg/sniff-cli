"""Shared CLI context pattern for sniff-based applications.

Provides a :class:`CLIContext` dataclass that bundles the common state
every CLI command needs -- configuration, output formatting, and
verbosity flags -- into a single object that can be attached to
a Typer ``ctx.obj``.

Usage::

    from sniff.cli.context import CLIContext
    from sniff.cli.config import ConfigManager
    from sniff.cli.output import OutputFormatter

    @app.callback()
    def main(ctx: typer.Context, verbose: bool = False, quiet: bool = False):
        ctx.obj = CLIContext(
            config=ConfigManager("myapp"),
            output=OutputFormatter(verbose=verbose, quiet=quiet),
            verbose=verbose,
            quiet=quiet,
        )

    @app.command()
    def build(ctx: typer.Context):
        cli: CLIContext = ctx.obj
        cli.output.info("Starting build...")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sniff.cli.config import ConfigManager
    from sniff.cli.output import OutputFormatter


@dataclass
class CLIContext:
    """Shared context for CLI commands.

    Designed to be stored on ``typer.Context.obj`` so that every
    sub-command has access to configuration, output formatting, and
    global flags without repeating boilerplate.

    Attributes:
        config: Application configuration manager.
        output: Multi-format output handler.
        verbose: Whether verbose output is enabled.
        quiet: Whether output should be suppressed.
    """

    config: ConfigManager
    output: OutputFormatter
    verbose: bool = False
    quiet: bool = False

    def __post_init__(self) -> None:
        """Hook for lazy initialization of expensive resources.

        Override in a subclass to set up database connections,
        API clients, or other heavy objects that should only be
        created once per CLI invocation.
        """
