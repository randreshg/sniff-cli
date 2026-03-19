"""CLI entry point for the dekk command-line tool.

All command imports are deferred to their handler functions so that
``dekk --help`` does not trigger loading Rich, detection modules, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final


CLI_APP_NAME: Final = "dekk"
CLI_HELP_TEXT: Final = "One config. Zero activation. Any project."
PYTHON_SCRIPT_SUFFIX: Final = ".py"
DEFAULT_INIT_DIRECTORY: Final = "."
DEFAULT_EXAMPLE_TEMPLATE: Final = "quickstart"
FILESYSTEM_RETRY_HINT: Final = "Retry the command after fixing the filesystem or PATH issue."


def _make_app():
    import typer
    globals()["typer"] = typer

    app = typer.Typer(
        name=CLI_APP_NAME,
        help=CLI_HELP_TEXT,
        no_args_is_help=True,
    )

    @app.command()
    def doctor() -> None:
        """Run comprehensive system health check."""
        from dekk.context import ExecutionContext
        from dekk.cli_commands import run_doctor

        context = ExecutionContext.capture()
        run_doctor(context)

    @app.command()
    def version() -> None:
        """Show dekk version and platform information."""
        from dekk import __version__
        from dekk.context import ExecutionContext
        from dekk.cli_commands import run_version

        context = ExecutionContext.capture()
        run_version(CLI_APP_NAME, __version__, context)

    @app.command()
    def env() -> None:
        """Show complete environment details."""
        from dekk.context import ExecutionContext
        from dekk.cli_commands import run_env

        context = ExecutionContext.capture()
        run_env(context)

    @app.command()
    def init(
        directory: str = typer.Argument(DEFAULT_INIT_DIRECTORY, help="Directory to initialize"),
        name: str | None = typer.Option(None, "--name", "-n", help="Project name"),
        example: str | None = typer.Option(None, "--example", help="Start from a built-in template"),
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing .dekk.toml"),
    ) -> None:
        """Initialize a new .dekk.toml configuration."""
        from dekk.cli.commands import init as _init

        _init(directory=Path(directory), name=name, example=example, force=force)

    @app.command()
    def example(
        template: str = typer.Argument(DEFAULT_EXAMPLE_TEMPLATE, help="Built-in template name"),
        output: str | None = typer.Option(None, "--output", "-o", help="Write example to a file"),
        name: str | None = typer.Option(None, "--name", "-n", help="Project name to inject"),
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite output file"),
    ) -> None:
        """Print or write a built-in .dekk.toml example."""
        from dekk.cli.commands import example as _example

        _example(
            template=template,
            output=Path(output) if output else None,
            name=name,
            force=force,
        )

    @app.command()
    def activate(
        shell: str | None = typer.Option(
            None,
            "--shell",
            help="Target shell for activation output (bash, zsh, fish, tcsh, powershell, pwsh)",
        ),
    ) -> None:
        """Print environment activation commands."""
        from dekk.cli.commands import activate as _activate

        _activate(shell=shell)

    @app.command()
    def install(
        target: str = typer.Argument(..., help="Script or binary to install"),
        name: str | None = typer.Option(None, "--name", "-n", help="Installed command name"),
        python: str | None = typer.Option(None, "--python", help="Python interpreter for script targets"),
        install_dir: str | None = typer.Option(None, "--install-dir", help="Installation directory"),
        spec: str | None = typer.Option(None, "--spec", "-s", help="Path to .dekk.toml"),
    ) -> None:
        """Install a project command with automatic environment setup."""
        from dekk.cli.commands import install as _install

        _install(
            target=Path(target),
            name=name,
            python=Path(python) if python else None,
            install_dir=Path(install_dir) if install_dir else None,
            spec_file=Path(spec) if spec else None,
        )

    @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
    def test(
        ctx: typer.Context,
    ) -> None:
        """Run the default project test command."""
        from dekk.cli.commands import test as _test

        _test(extra_args=list(ctx.args))

    @app.command()
    def wrap(
        name: str = typer.Argument(..., help="Wrapper name"),
        target: str = typer.Argument(..., help="Target script/binary"),
        python: str | None = typer.Option(None, "--python", help="Python interpreter for script targets"),
        install_dir: str | None = typer.Option(None, "--install-dir", help="Installation directory"),
        spec: str | None = typer.Option(None, "--spec", "-s", help="Path to .dekk.toml"),
    ) -> None:
        """Generate a self-contained wrapper binary."""
        from dekk.cli.commands import wrap as _wrap

        _wrap(
            name=name,
            target=Path(target),
            python=Path(python) if python else None,
            install_dir=Path(install_dir) if install_dir else None,
            spec_file=Path(spec) if spec else None,
        )

    @app.command()
    def uninstall(
        name: str = typer.Argument(..., help="Wrapper name to uninstall"),
        install_dir: str | None = typer.Option(None, "--install-dir", help="Installation directory"),
        remove_path: bool = typer.Option(False, "--remove-path", help="Also remove the PATH export for this project"),
    ) -> None:
        """Remove an installed wrapper."""
        from dekk.cli.commands import uninstall as _uninstall

        _uninstall(
            name=name,
            install_dir=Path(install_dir) if install_dir else None,
            remove_path=remove_path,
        )

    return app


# Build the app lazily on first access
_app = None


def main() -> None:
    """Entry point for dekk CLI."""
    import sys

    try:
        # If first arg is a .py script, run it with auto-bootstrapped venv
        if len(sys.argv) > 1 and sys.argv[1].endswith(PYTHON_SCRIPT_SUFFIX):
            from dekk.runner import run_script

            run_script(sys.argv[1], sys.argv[2:])
            return

        global _app
        if _app is None:
            _app = _make_app()
        _app()
    except KeyboardInterrupt:
        from dekk.cli.errors import ExitCodes

        raise SystemExit(int(ExitCodes.INTERRUPTED)) from None
    except OSError as exc:
        from dekk.cli.errors import ExitCodes
        from dekk.cli.styles import print_error, print_info

        print_error(str(exc))
        print_info(FILESYSTEM_RETRY_HINT)
        raise SystemExit(int(ExitCodes.RUNTIME_ERROR)) from exc
    except Exception as exc:
        from click.exceptions import Exit as ClickExit
        from dekk.cli.errors import DekkError
        from dekk.cli.styles import print_error, print_info

        if isinstance(exc, ClickExit):
            raise
        if isinstance(exc, DekkError):
            print_error(exc.message)
            if exc.hint:
                print_info(f"Hint: {exc.hint}")
            raise SystemExit(int(exc.exit_code)) from exc
        raise


if __name__ == "__main__":
    main()
