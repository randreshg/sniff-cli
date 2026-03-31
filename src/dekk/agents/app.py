"""Factory for creating reusable ``agents`` Typer sub-apps.

``create_agents_app()`` returns a Typer sub-app with init, generate, clean,
install, status, and list commands. It can be used standalone (``dekk agents``) or
embedded in a dekk-based CLI (``carts agents``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from dekk.agents.constants import (
    AGENTS_JSON,
    AGENTS_MD,
    CLAUDE_MD,
    CLAUDE_SKILLS_DIR,
    COPILOT_DIR,
    COPILOT_INSTRUCTIONS,
    CURSORRULES,
    DEFAULT_CLI_NAME,
    DEFAULT_SOURCE_DIR,
    DEKK_TOML,
    PROJECT_MD,
    SKILLS_DIR_NAME,
)


def _handle_dekk_error(exc: Exception) -> None:
    """Re-raise *exc* with formatted output if it is a ``DekkError``."""
    import typer

    from dekk.cli.errors import DekkError
    from dekk.cli.styles import print_error, print_info

    if isinstance(exc, DekkError):
        print_error(exc.message)
        if exc.hint:
            print_info(f"Hint: {exc.hint}")
        raise typer.Exit(exc.exit_code) from exc
    raise exc


def _find_project_root(source_dir: str) -> Path:
    """Walk up from cwd to find the project root.

    Looks for the source directory (e.g., ``.agents/``) or ``.dekk.toml``
    by walking up from the current working directory. Falls back to cwd
    if neither is found (``init`` will create the source dir there).
    """
    from dekk._compat import walk_up

    # Try to find the source directory itself (e.g., .agents/)
    found = walk_up(Path.cwd(), source_dir)
    if found and found.is_dir():
        return found.parent

    # Try to find .dekk.toml
    found = walk_up(Path.cwd(), DEKK_TOML)
    if found and found.is_file():
        return found.parent

    return Path.cwd()


def create_agents_app(
    source_dir: str = DEFAULT_SOURCE_DIR,
    parent_app: Any | None = None,
    get_project_root: Callable[[], Path] | None = None,
) -> Any:
    """Create a reusable Typer sub-app for agent config management.

    Args:
        source_dir: Path to the SSOT directory (default ".agents", CARTS uses ".carts").
        parent_app: If provided, ``init`` introspects this app's registered commands.
        get_project_root: Callback that returns the project root directory.
            For dekk-based CLIs (e.g., CARTS), this should return the repo root
            (e.g., ``lambda: get_config().carts_dir``). If None, walks up from
            cwd to find ``.agents/`` or ``.dekk.toml``.

    Returns:
        Typer sub-app with: init, generate, clean, install, status, list commands.
    """
    import typer

    def _resolve_root() -> Path:
        if get_project_root is not None:
            return get_project_root()
        return _find_project_root(source_dir)

    agents_app = typer.Typer(
        help="Manage agent configs (Claude Code, Codex, Cursor, Copilot).",
        no_args_is_help=True,
    )

    @agents_app.command("init")
    def init(
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files"),
    ) -> None:
        """Scaffold the source-of-truth directory from project detection + commands."""
        from dekk.agents.scaffold import scaffold_agents_dir
        from dekk.cli.styles import print_info, print_success, print_warning
        from dekk.environment.bootstrap import ensure_envspec

        project_root = _resolve_root()
        cli_name = None
        if parent_app is not None:
            cli_name = getattr(parent_app, "_name", None)

        # Guard against accidentally re-scaffolding a curated .agents/ directory.
        existing_source = project_root / source_dir
        if (
            existing_source.is_dir()
            and (existing_source / PROJECT_MD).is_file()
            and not force
        ):
            print_warning(
                f"{source_dir}/ already exists with {PROJECT_MD}"
            )
            print_info(
                "Re-running init may add new skill templates from "
                "newly discovered commands. Existing files are never overwritten "
                "without --force."
            )
            if not typer.confirm("Continue?"):
                raise typer.Exit(0)

        bootstrap = ensure_envspec(project_root)
        result_dir = scaffold_agents_dir(
            project_root=project_root,
            source_dir=source_dir,
            parent_app=parent_app,
            cli_name=cli_name,
            force=force,
        )
        if bootstrap.created:
            print_info(f"Created {DEKK_TOML} from {bootstrap.source}")
        print_success(f"Scaffolded {result_dir.relative_to(project_root)}/ in {project_root}")

    @agents_app.command("generate")
    def generate(
        target: str = typer.Option(
            "all",
            "--target",
            "-t",
            help="Target: claude, codex, copilot, cursor, all",
        ),
    ) -> None:
        """Generate agent configs from the source-of-truth directory."""
        from dekk.agents.generators import AgentConfigManager
        from dekk.cli.styles import print_error, print_info, print_success
        from dekk.environment.spec import AgentsSpec, EnvironmentSpec, find_envspec

        project_root = _resolve_root()
        cli_name = None
        if parent_app is not None:
            cli_name = getattr(parent_app, "_name", None)

        # Load [agents] spec from .dekk.toml if available.
        agents_spec: AgentsSpec | None = None
        envspec_path = find_envspec(project_root)
        if envspec_path:
            try:
                agents_spec = EnvironmentSpec.from_file(envspec_path).agents
            except Exception:
                pass  # Fall back to defaults when the spec is unparseable.

        manager = AgentConfigManager(
            project_root=project_root,
            source_dir=source_dir,
            cli_name=cli_name,
            agents_spec=agents_spec,
        )

        try:
            result = manager.generate(target=target)
        except FileNotFoundError as exc:
            print_error(str(exc))
            cmd_prefix = cli_name or f"{DEFAULT_CLI_NAME} <appname>"
            hint = (
                f"Run `{cmd_prefix} agents init` "
                f"to scaffold the source directory"
            )
            print_info(f"Hint: {hint}")
            raise typer.Exit(1) from exc
        except Exception as exc:
            _handle_dekk_error(exc)

        for item in result.generated:
            print_success(f"Generated {item}")

    @agents_app.command("install")
    def install(
        codex_dir: str | None = typer.Option(
            None,
            "--codex-dir",
            help="Codex skills directory (default: $CODEX_HOME/skills or ~/.codex/skills)",
        ),
        force: bool = typer.Option(
            True,
            "--force/--no-force",
            help="Replace existing skills in destination",
        ),
    ) -> None:
        """Install skills into ~/.codex/skills/ for Codex agent."""
        from dekk.agents.installer import install_codex_skills
        from dekk.cli.styles import print_info, print_success

        project_root = _resolve_root()
        effective_dir = Path(codex_dir).expanduser() if codex_dir else None
        source = project_root / source_dir

        installed = install_codex_skills(source, codex_dir=effective_dir, force=force)
        for name in installed:
            print_success(f"  codex: {name}")
        print_info(f"Installed {len(installed)} Codex skill(s)")

    @agents_app.command("clean")
    def clean(
        target: str = typer.Option(
            "all",
            "--target",
            "-t",
            help="Target: claude, codex, copilot, cursor, all",
        ),
    ) -> None:
        """Remove generated agent config files while keeping the source directory."""
        from dekk.agents.generators import AgentConfigManager
        from dekk.cli.styles import print_info, print_success

        project_root = _resolve_root()
        cli_name = None
        if parent_app is not None:
            cli_name = getattr(parent_app, "_name", None)

        manager = AgentConfigManager(
            project_root=project_root,
            source_dir=source_dir,
            cli_name=cli_name,
        )
        try:
            result = manager.clean(target=target)
        except Exception as exc:
            _handle_dekk_error(exc)
        if not result.removed:
            print_info("Nothing to clean")
            return

        for item in result.removed:
            print_success(f"Removed {item}")

    @agents_app.command("status")
    def status(
        codex_dir: str | None = typer.Option(
            None,
            "--codex-dir",
            help="Codex skills directory (default: $CODEX_HOME/skills or ~/.codex/skills)",
        ),
    ) -> None:
        """Show agent config and skill installation status."""
        from dekk.agents.discovery import discover_skills
        from dekk.agents.generators import render_codex_skill
        from dekk.agents.installer import check_skill_state, codex_skills_dir
        from dekk.cli.styles import Colors, console

        project_root = _resolve_root()
        source = project_root / source_dir
        claude_dir = project_root / CLAUDE_SKILLS_DIR
        effective_codex_dir = Path(codex_dir).expanduser() if codex_dir else codex_skills_dir()

        skills = discover_skills(source)

        # Source status
        project_md = source / PROJECT_MD
        console.print(f"[{Colors.INFO}]Source of truth:[/{Colors.INFO}] {source_dir}/")
        pm_ok = project_md.is_file()
        pm_color = Colors.SUCCESS if pm_ok else Colors.WARNING
        pm_state = "present" if pm_ok else "missing"
        console.print(f"  {PROJECT_MD}: [{pm_color}]{pm_state}[/{pm_color}]")
        skill_count = len(skills)
        console.print(
            f"  {SKILLS_DIR_NAME}/: [{Colors.SUCCESS}]"
            f"{skill_count} skill(s)[/{Colors.SUCCESS}]"
        )
        console.print()

        # Generated config files
        config_files = [
            (CLAUDE_MD, project_root / CLAUDE_MD),
            (AGENTS_MD, project_root / AGENTS_MD),
            (CURSORRULES, project_root / CURSORRULES),
            (
                f"{COPILOT_DIR}/{COPILOT_INSTRUCTIONS}",
                project_root / COPILOT_DIR / COPILOT_INSTRUCTIONS,
            ),
            (AGENTS_JSON, project_root / AGENTS_JSON),
        ]
        console.print(f"[{Colors.INFO}]Agent config files:[/{Colors.INFO}]")
        for label, path in config_files:
            exists = path.is_file()
            color = Colors.SUCCESS if exists else Colors.WARNING
            state = "present" if exists else "missing"
            console.print(f"  {label}: [{color}]{state}[/{color}]")

        console.print()
        console.print(f"[{Colors.INFO}]Skills:[/{Colors.INFO}]")
        for skill in skills:
            claude_state = check_skill_state(skill, claude_dir)
            codex_state = check_skill_state(skill, effective_codex_dir, renderer=render_codex_skill)

            def _color(s: str) -> str:
                return Colors.SUCCESS if s == "ok" else Colors.WARNING

            console.print(
                f"  [{Colors.INFO}]{skill.name}[/{Colors.INFO}]  "
                f"claude=[{_color(claude_state)}]{claude_state}[/{_color(claude_state)}]  "
                f"codex=[{_color(codex_state)}]{codex_state}[/{_color(codex_state)}]"
            )

    @agents_app.command("list")
    def list_skills() -> None:
        """List available skills from the source-of-truth directory."""
        from dekk.agents.discovery import discover_skills
        from dekk.cli.styles import Colors, console, print_warning

        project_root = _resolve_root()
        source = project_root / source_dir
        skills = discover_skills(source)
        if not skills:
            print_warning("No skills found")
            return

        console.print(f"[{Colors.INFO}]Source:[/{Colors.INFO}] {source}")
        console.print()
        for skill in skills:
            console.print(f"[{Colors.INFO}]{skill.name}[/{Colors.INFO}]")
            console.print(f"  {skill.description}")

    return agents_app
