"""CLI commands for ``dekk worktree`` sub-app."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dekk.tools import CLI_NAME
from dekk.tools import SETUP as PROJECT_SETUP_COMMAND

if TYPE_CHECKING:
    import typer


def create_worktree_app() -> typer.Typer:
    """Build the ``dekk worktree`` Typer sub-application."""
    import typer

    app = typer.Typer(
        name="worktree",
        help="Manage git worktrees with dekk environment awareness.",
        no_args_is_help=True,
    )

    @app.command("list")
    def list_cmd() -> None:
        """List all git worktrees for this project."""
        from dekk.cli.styles import print_info, print_warning
        from dekk.tools.worktree.core import find_git_root, list_worktrees

        root = find_git_root()
        if root is None:
            print_warning("Not inside a git repository.")
            raise typer.Exit(1)

        worktrees = list_worktrees(root)
        if not worktrees:
            print_info("No worktrees found.")
            return

        for wt in worktrees:
            tag_parts: list[str] = []
            if wt.is_main:
                tag_parts.append("main")
            if wt.is_detached:
                tag_parts.append("detached")
            if wt.has_dekk_toml:
                tag_parts.append("dekk")
            if wt.prunable:
                tag_parts.append("prunable")
            tags = f" ({', '.join(tag_parts)})" if tag_parts else ""

            branch_display = wt.branch or wt.commit[:8]
            print_info(f"  {wt.path}  [{branch_display}]{tags}")

    @app.command()
    def create(
        branch: str = typer.Argument(..., help="Branch name for the new worktree"),
        path: str | None = typer.Option(
            None, "--path", "-p",
            help="Directory for the worktree (default: ../<repo>-worktrees/<branch>)"
        ),
        base: str = typer.Option("HEAD", "--base", "-b", help="Base commit or branch"),
        existing: bool = typer.Option(
            False, "--existing", "-e", help="Use an existing branch instead of creating one"
        ),
        setup: bool = typer.Option(
            True, "--setup/--no-setup", help="Run dekk setup in the new worktree"
        ),
    ) -> None:
        """Create a new git worktree with dekk environment support."""
        from dekk.cli.styles import print_error, print_info, print_success
        from dekk.tools.worktree.core import create_worktree as _create

        result = _create(
            branch=branch,
            path=Path(path) if path else None,
            new_branch=not existing,
            base=base,
        )

        if not result.ok:
            print_error(f"Failed to create worktree: {result.error}")
            raise typer.Exit(1)

        print_success(f"Created worktree: {result.path}")
        print_info(f"  Branch: {result.branch}")

        if setup and (result.path / ".dekk.toml").exists():
            import subprocess

            setup_cmd = [CLI_NAME, PROJECT_SETUP_COMMAND]
            try:
                from dekk.environment.spec import EnvironmentSpec

                project_name = EnvironmentSpec.from_file(result.path / ".dekk.toml").project_name
                setup_cmd = [CLI_NAME, project_name, PROJECT_SETUP_COMMAND]
            except Exception:
                pass

            print_info(f"Running {' '.join(setup_cmd)} in worktree...")
            setup_result = subprocess.run(
                setup_cmd,
                cwd=result.path,
                check=False,
            )
            if setup_result.returncode == 0:
                print_success("Environment ready.")
            else:
                print_info(
                    "Setup had issues. Run the project-scoped dekk setup command manually in the worktree."
                )

        print_info(f"  cd {result.path}")

    @app.command()
    def remove(
        name: str = typer.Argument(..., help="Worktree path or directory name"),
        force: bool = typer.Option(
            False, "--force", "-f",
            help="Force removal even with modifications",
        ),
    ) -> None:
        """Remove a git worktree."""
        from dekk.cli.styles import print_error, print_success
        from dekk.tools.worktree.core import remove_worktree as _remove

        ok, message = _remove(name, force=force)
        if ok:
            print_success(message)
        else:
            print_error(f"Failed: {message}")
            raise typer.Exit(1)

    @app.command()
    def prune() -> None:
        """Clean up stale worktree references."""
        from dekk.cli.styles import print_error, print_success
        from dekk.tools.worktree.core import prune_worktrees

        ok, message = prune_worktrees()
        if ok:
            print_success(message)
        else:
            print_error(message)
            raise typer.Exit(1)

    return app


__all__ = ["create_worktree_app"]
