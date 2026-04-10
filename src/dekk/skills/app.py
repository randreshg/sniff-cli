"""Factory for creating reusable ``skills`` Typer sub-apps.

``create_agents_app()`` returns a Typer sub-app with init, generate, sync,
view, clean, status, and list commands. It can be used standalone
(``dekk skills``) or embedded in a dekk-based CLI (``carts skills``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from dekk.skills.constants import (
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

    Looks for the source directory (e.g., ``.skills/``) or ``.dekk.toml``
    by walking up from the current working directory. Falls back to cwd
    if neither is found (``init`` will create the source dir there).
    """
    from dekk._compat import walk_up

    # Try to find the source directory itself (e.g., .skills/)
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
    """Create a reusable Typer sub-app for skill / agent config management.

    Args:
        source_dir: Path to the SSOT directory (default ".skills", CARTS uses ".carts").
        parent_app: If provided, ``init`` introspects this app's registered commands.
        get_project_root: Callback that returns the project root directory.
            For dekk-based CLIs (e.g., CARTS), this should return the repo root
            (e.g., ``lambda: get_config().carts_dir``). If None, walks up from
            cwd to find ``.skills/`` or ``.dekk.toml``.

    Returns:
        Typer sub-app with: init, generate, sync, view, clean, status, list commands.
    """
    import typer

    def _resolve_root() -> Path:
        if get_project_root is not None:
            return get_project_root()
        return _find_project_root(source_dir)

    agents_app = typer.Typer(
        help="Manage skills and agent configs (Claude Code, Codex, Cursor, Copilot).",
        no_args_is_help=True,
    )

    @agents_app.command("init")
    def init(
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files"),
    ) -> None:
        """Scaffold the source-of-truth directory from project detection + commands."""
        from dekk.cli.styles import print_info, print_success, print_warning
        from dekk.environment.bootstrap import ensure_envspec
        from dekk.skills.scaffold import scaffold_agents_dir

        project_root = _resolve_root()
        cli_name = None
        if parent_app is not None:
            cli_name = getattr(parent_app, "_name", None)

        # Guard against accidentally re-scaffolding a curated .skills/ directory.
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
        from dekk.cli.styles import print_error, print_info, print_success
        from dekk.environment.spec import EnvironmentSpec, SkillsSpec, find_envspec
        from dekk.skills.generators import AgentConfigManager

        project_root = _resolve_root()
        cli_name = None
        if parent_app is not None:
            cli_name = getattr(parent_app, "_name", None)

        # Load [agents] spec from .dekk.toml if available.
        agents_spec: SkillsSpec | None = None
        env_spec: EnvironmentSpec | None = None
        envspec_path = find_envspec(project_root)
        if envspec_path:
            try:
                env_spec = EnvironmentSpec.from_file(envspec_path)
                agents_spec = env_spec.skills
            except Exception:
                pass  # Fall back to defaults when the spec is unparseable.

        # Use [agents].source from .dekk.toml if available, otherwise
        # fall back to the static source_dir parameter.
        effective_source = (
            agents_spec.source if agents_spec and agents_spec.source else source_dir
        )

        manager = AgentConfigManager(
            project_root=project_root,
            source_dir=effective_source,
            cli_name=cli_name,
            agents_spec=agents_spec,
            env_spec=env_spec,
        )

        try:
            result = manager.generate(target=target)
        except FileNotFoundError as exc:
            print_error(str(exc))
            cmd_prefix = cli_name or f"{DEFAULT_CLI_NAME} <appname>"
            hint = (
                f"Run `{cmd_prefix} skills init` "
                f"to scaffold the source directory"
            )
            print_info(f"Hint: {hint}")
            raise typer.Exit(1) from exc
        except Exception as exc:
            _handle_dekk_error(exc)

        for item in result.generated:
            print_success(f"Generated {item}")

    @agents_app.command("sync")
    def sync(
        target: str = typer.Option(
            "all",
            "--target",
            "-t",
            help="Target: claude, codex, copilot, cursor, all",
        ),
    ) -> None:
        """Sync skills to agent configs (alias for generate)."""
        generate(target=target)

    @agents_app.command("view")
    def view(
        skill_name: str = typer.Argument(None, help="Skill name (omit for project.md)"),
    ) -> None:
        """Show skill or project.md content."""
        from dekk.cli.styles import _get_console, print_error

        project_root = _resolve_root()
        source = project_root / source_dir
        if skill_name:
            path = source / SKILLS_DIR_NAME / skill_name / "SKILL.md"
        else:
            path = source / PROJECT_MD
        if not path.is_file():
            print_error(f"Not found: {path}")
            raise typer.Exit(1)
        from rich.markdown import Markdown

        _get_console().print(Markdown(path.read_text(encoding="utf-8")))

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
        from dekk.cli.styles import print_info, print_success
        from dekk.skills.generators import AgentConfigManager

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
    def status() -> None:
        """Show agent config and skill status."""
        from rich.text import Text

        from dekk.cli.styles import Colors, console
        from dekk.skills.discovery import discover_skills
        from dekk.skills.installer import check_skill_state

        project_root = _resolve_root()
        source = project_root / source_dir
        claude_dir = project_root / CLAUDE_SKILLS_DIR

        skills = discover_skills(source)

        # Source status
        project_md = source / PROJECT_MD
        label = Text()
        label.append("Source of truth:", style=Colors.INFO)
        label.append(f" {source_dir}/")
        console.print(label)
        pm_ok = project_md.is_file()
        pm_state = Text()
        pm_state.append(f"  {PROJECT_MD}: ")
        pm_state.append(
            "present" if pm_ok else "missing",
            style=Colors.SUCCESS if pm_ok else Colors.WARNING,
        )
        console.print(pm_state)
        skill_count = len(skills)
        sk_line = Text()
        sk_line.append(f"  {SKILLS_DIR_NAME}/: ")
        sk_line.append(f"{skill_count} skill(s)", style=Colors.SUCCESS)
        console.print(sk_line)
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
        console.print(Text("Agent config files:", style=Colors.INFO))
        for cfg_label, path in config_files:
            exists = path.is_file()
            line = Text(f"  {cfg_label}: ")
            line.append(
                "present" if exists else "missing",
                style=Colors.SUCCESS if exists else Colors.WARNING,
            )
            console.print(line)

        console.print()
        console.print(Text("Skills:", style=Colors.INFO))
        for skill in skills:
            claude_state = check_skill_state(skill, claude_dir)
            line = Text("  ")
            line.append(skill.name, style=Colors.INFO)
            line.append("  claude=")
            line.append(
                claude_state,
                style=Colors.SUCCESS if claude_state == "ok" else Colors.WARNING,
            )
            console.print(line)

    @agents_app.command("list")
    def list_skills() -> None:
        """List available skills from the source-of-truth directory."""
        from rich.text import Text

        from dekk.cli.styles import Colors, console, print_warning
        from dekk.skills.discovery import discover_skills

        project_root = _resolve_root()
        source = project_root / source_dir
        skills = discover_skills(source)
        if not skills:
            print_warning("No skills found")
            return

        src_line = Text()
        src_line.append("Source:", style=Colors.INFO)
        src_line.append(f" {source}")
        console.print(src_line)
        console.print()
        for skill in skills:
            console.print(Text(skill.name, style=Colors.INFO))
            console.print(f"  {skill.description}")

    return agents_app
