"""Smart project scaffolding for the .agents/ source-of-truth directory.

Discovers commands from two sources:
  1. Typer app introspection (``parent_app``) -- for dekk-based CLIs
  2. ``.dekk.toml`` ``[commands]`` section -- for plain projects

Generates ``.agents/project.md`` and ``skills/<name>/SKILL.md`` templates
from discovered commands and project detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dekk.agents.constants import (
    BUILD_SYSTEM_MARKERS,
    DEFAULT_SOURCE_DIR,
    DEKK_TOML,
    PROJECT_MD,
    RULES_DIR_NAME,
    SKILL_FILENAME,
    SKILLS_DIR_NAME,
)

# TOML keys
_TOML_PROJECT_KEY = "project"
_TOML_NAME_KEY = "name"
_TOML_COMMANDS_KEY = "commands"
_TOML_RUN_KEY = "run"
_TOML_DESCRIPTION_KEY = "description"


@dataclass
class DiscoveredCommand:
    """A command discovered from Typer introspection or .dekk.toml."""

    name: str
    description: str
    run: str


def discover_commands_from_typer(parent_app: Any, cli_name: str) -> list[DiscoveredCommand]:
    """Introspect a dekk Typer app for commands marked as agent skills.

    Only yields commands where the callback has ``_dekk_agent_skill = True``
    set by dekk's enhanced ``command()`` decorator.
    """
    commands: list[DiscoveredCommand] = []

    # Access the underlying typer.Typer app
    inner_app = getattr(parent_app, "_app", parent_app)
    registered = getattr(inner_app, "registered_commands", [])

    for cmd_info in registered:
        callback = getattr(cmd_info, "callback", None)
        if callback is None:
            continue

        if not getattr(callback, "_dekk_agent_skill", False):
            continue

        cmd_name = getattr(cmd_info, "name", None) or callback.__name__
        cmd_help = getattr(cmd_info, "help", None) or callback.__doc__ or ""
        cmd_help = cmd_help.strip().split("\n")[0] if cmd_help else cmd_name

        commands.append(DiscoveredCommand(
            name=cmd_name,
            description=cmd_help,
            run=f"{cli_name} {cmd_name}",
        ))

    return commands


def discover_commands_from_toml(spec: Any) -> list[DiscoveredCommand]:
    """Read commands from a parsed EnvironmentSpec's ``commands`` dict."""
    commands_dict = getattr(spec, _TOML_COMMANDS_KEY, {})
    if not commands_dict:
        return []

    result: list[DiscoveredCommand] = []
    for name, cmd_spec in commands_dict.items():
        if isinstance(cmd_spec, dict):
            run_cmd = cmd_spec.get(_TOML_RUN_KEY, name)
            desc = cmd_spec.get(_TOML_DESCRIPTION_KEY, "")
        else:
            run_cmd = str(cmd_spec)
            desc = ""

        result.append(DiscoveredCommand(
            name=name,
            description=desc or name,
            run=run_cmd,
        ))

    return result


def _detect_project_info(project_root: Path) -> dict[str, str]:
    """Auto-detect project language, build system, and test framework."""
    info: dict[str, str] = {_TOML_NAME_KEY: project_root.name}

    for marker, (language, build_cmd, test_cmd) in BUILD_SYSTEM_MARKERS.items():
        if (project_root / marker).exists():
            info["language"] = language
            info["build"] = build_cmd
            info["test"] = test_cmd
            break

    return info


def _render_skill_md(cmd: DiscoveredCommand) -> str:
    """Render a SKILL.md template from a discovered command."""
    return (
        "---\n"
        f"name: {cmd.name}\n"
        f"description: {cmd.description}\n"
        "user-invocable: true\n"
        "---\n\n"
        f"# {cmd.name.replace('-', ' ').title()}\n\n"
        f"Run: `{cmd.run}`\n"
    )


def _render_project_md(
    project_name: str,
    project_info: dict[str, str],
    commands: list[DiscoveredCommand],
) -> str:
    """Render a project.md template from detected project info."""
    lines = [f"# {project_name}", ""]

    if "language" in project_info:
        lines.append(f"Language: {project_info['language']}")
        lines.append("")

    if commands:
        lines.append("## Commands")
        lines.append("")
        for cmd in commands:
            lines.append(f"- **{cmd.name}**: `{cmd.run}` -- {cmd.description}")
        lines.append("")

    if "build" in project_info:
        lines.append("## Build")
        lines.append("")
        lines.append(f"```bash\n{project_info['build']}\n```")
        lines.append("")

    if "test" in project_info:
        lines.append("## Test")
        lines.append("")
        lines.append(f"```bash\n{project_info['test']}\n```")
        lines.append("")

    return "\n".join(lines)


def commands_to_skills(commands: list[DiscoveredCommand], skills_dir: Path) -> list[Path]:
    """Convert discovered commands into ``skills/<name>/SKILL.md`` template files.

    Only creates files that don't already exist (won't overwrite user customizations).

    Returns:
        List of created SKILL.md paths.
    """
    created: list[Path] = []
    for cmd in commands:
        skill_dir = skills_dir / cmd.name
        skill_file = skill_dir / SKILL_FILENAME
        if skill_file.exists():
            continue
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(_render_skill_md(cmd), encoding="utf-8")
        created.append(skill_file)
    return created


def scaffold_agents_dir(
    project_root: Path,
    source_dir: str = DEFAULT_SOURCE_DIR,
    parent_app: Any | None = None,
    cli_name: str | None = None,
    force: bool = False,
) -> Path:
    """Auto-generate the source-of-truth directory from project detection + commands.

    Merges commands from:
      1. Typer app introspection (if ``parent_app`` provided)
      2. ``.dekk.toml`` ``[commands]`` section
      3. Project detection (build system, test framework)

    Args:
        project_root: Root directory of the project.
        source_dir: Name of the source directory to create (default: ".agents").
        parent_app: Optional dekk Typer app to introspect for commands.
        cli_name: CLI command name (e.g., "carts") for run commands.
        force: Overwrite existing project.md if True.

    Returns:
        Path to the created source directory.
    """
    target = project_root / source_dir
    skills_dir = target / SKILLS_DIR_NAME
    rules_dir = target / RULES_DIR_NAME

    target.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)
    rules_dir.mkdir(parents=True, exist_ok=True)

    # Collect commands from all sources
    all_commands: list[DiscoveredCommand] = []
    seen_names: set[str] = set()

    # Source 1: Typer app introspection
    if parent_app is not None and cli_name:
        for cmd in discover_commands_from_typer(parent_app, cli_name):
            if cmd.name not in seen_names:
                all_commands.append(cmd)
                seen_names.add(cmd.name)

    # Source 2: .dekk.toml [commands] + project name
    toml_project_name: str | None = None
    dekk_toml = project_root / DEKK_TOML
    if dekk_toml.is_file():
        from dekk._compat import tomllib

        with open(dekk_toml, "rb") as f:
            data = tomllib.load(f)
        toml_project_name = data.get(_TOML_PROJECT_KEY, {}).get(_TOML_NAME_KEY)
        toml_commands = data.get(_TOML_COMMANDS_KEY, {})
        for name, spec in toml_commands.items():
            if name not in seen_names:
                if isinstance(spec, dict):
                    run_cmd = spec.get(_TOML_RUN_KEY, name)
                    desc = spec.get(_TOML_DESCRIPTION_KEY, "")
                else:
                    run_cmd = str(spec)
                    desc = ""
                all_commands.append(DiscoveredCommand(
                    name=name,
                    description=desc or name,
                    run=run_cmd,
                ))
                seen_names.add(name)

    # Detect project info
    project_info = _detect_project_info(project_root)
    project_name = toml_project_name or project_info.get(_TOML_NAME_KEY, project_root.name)

    # Generate skill templates from commands
    commands_to_skills(all_commands, skills_dir)

    # Generate project.md
    project_md = target / PROJECT_MD
    if not project_md.exists() or force:
        content = _render_project_md(project_name, project_info, all_commands)
        project_md.write_text(content, encoding="utf-8")

    return target
