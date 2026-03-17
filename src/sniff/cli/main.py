"""CLI entry point for sniff command-line tool.

All command imports are deferred to their handler functions so that
``sniff --help`` does not trigger loading Rich, detection modules, etc.
"""

from __future__ import annotations


def _make_app():
    import typer

    app = typer.Typer(
        name="sniff",
        help="One config. Zero activation. Any project.",
        no_args_is_help=True,
    )

    @app.command()
    def doctor() -> None:
        """Run comprehensive system health check."""
        from sniff.context import ExecutionContext
        from sniff.cli_commands import run_doctor

        context = ExecutionContext.capture()
        run_doctor(context)

    @app.command()
    def version() -> None:
        """Show sniff version and platform information."""
        from sniff.context import ExecutionContext
        from sniff.cli_commands import run_version

        context = ExecutionContext.capture()
        run_version("sniff", "3.2.0", context)

    @app.command()
    def env() -> None:
        """Show complete environment details."""
        from sniff.context import ExecutionContext
        from sniff.cli_commands import run_env

        context = ExecutionContext.capture()
        run_env(context)

    @app.command()
    def init(
        directory: str = typer.Argument(".", help="Directory to initialize"),
        name: str | None = typer.Option(None, "--name", "-n", help="Project name"),
    ) -> None:
        """Initialize a new .sniff.toml configuration."""
        from sniff.cli.commands import init as _init

        _init(directory=directory, name=name)

    @app.command()
    def activate(
        format: str = typer.Option("posix", "--format", "-f", help="Output format"),
    ) -> None:
        """Print environment activation commands."""
        from sniff.cli.commands import activate as _activate

        _activate(format=format)

    @app.command()
    def wrap(
        name: str = typer.Argument(..., help="Wrapper name"),
        target: str = typer.Argument(..., help="Target script/binary"),
        install_dir: str | None = typer.Option(None, "--install-dir", help="Installation directory"),
    ) -> None:
        """Generate a self-contained wrapper binary."""
        from sniff.cli.commands import wrap as _wrap

        _wrap(name=name, target=target, install_dir=install_dir)

    @app.command()
    def uninstall(
        name: str = typer.Argument(..., help="Wrapper name to uninstall"),
    ) -> None:
        """Remove an installed wrapper."""
        from sniff.cli.commands import uninstall as _uninstall

        _uninstall(name=name)

    return app


# Build the app lazily on first access
_app = None


def main() -> None:
    """Entry point for sniff CLI."""
    import sys

    # If first arg is a .py script, run it with auto-bootstrapped venv
    if len(sys.argv) > 1 and sys.argv[1].endswith('.py'):
        from sniff.runner import run_script
        run_script(sys.argv[1], sys.argv[2:])
        return

    global _app
    if _app is None:
        _app = _make_app()
    _app()


if __name__ == "__main__":
    main()
