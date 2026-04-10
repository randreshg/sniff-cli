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

from dekk.detection.build import BuildSystem, BuildSystemDetector
from dekk.detection.scaffold import ProjectLanguage, ProjectTypeDetector
from dekk.environment.spec import RESERVED_COMMAND_KEYS
from dekk.skills.constants import (
    DEFAULT_SOURCE_DIR,
    DEKK_TOML,
    PROJECT_MD,
    RULES_DIR_NAME,
    SKILL_FILENAME,
    SKILLS_DIR_NAME,
    TOML_COMMANDS_KEY,
    TOML_DESCRIPTION_KEY,
    TOML_NAME_KEY,
    TOML_PROJECT_KEY,
    TOML_RUN_KEY,
    TOML_SKILL_KEY,
    WORKTREE_SKILL_NAME,
)

BUILD_COMMAND_NAME = "build"
TEST_COMMAND_NAME = "test"
LANGUAGE_DISPLAY_NAMES = {
    ProjectLanguage.PYTHON: "Python",
    ProjectLanguage.RUST: "Rust",
    ProjectLanguage.JAVASCRIPT: "TypeScript/JavaScript",
    ProjectLanguage.TYPESCRIPT: "TypeScript/JavaScript",
    ProjectLanguage.GO: "Go",
    ProjectLanguage.JAVA: "Java",
    ProjectLanguage.CSHARP: "C#",
    ProjectLanguage.CPP: "C/C++",
    ProjectLanguage.C: "C/C++",
    ProjectLanguage.RUBY: "Ruby",
    ProjectLanguage.PHP: "PHP",
    ProjectLanguage.SWIFT: "Swift",
    ProjectLanguage.KOTLIN: "Kotlin",
    ProjectLanguage.SCALA: "Scala",
}
DETECTED_BUILD_COMMANDS = {
    BuildSystem.CARGO: "cargo build",
    BuildSystem.CMAKE: "cmake -B build && cmake --build build",
    BuildSystem.NPM: "npm run build",
    BuildSystem.PNPM: "pnpm run build",
    BuildSystem.YARN: "yarn build",
    BuildSystem.BUN: "bun run build",
    BuildSystem.POETRY: "poetry build",
    BuildSystem.PDM: "pdm build",
    BuildSystem.HATCH: "hatch build",
    BuildSystem.FLIT: "flit build",
    BuildSystem.SETUPTOOLS: "python -m build",
    BuildSystem.MATURIN: "maturin build",
    BuildSystem.UV: "uv build",
    BuildSystem.GO: "go build ./...",
    BuildSystem.MAVEN: "mvn package",
    BuildSystem.GRADLE: "gradle build",
    BuildSystem.MAKE: "make",
}
DETECTED_TEST_COMMANDS = {
    BuildSystem.CARGO: "cargo test",
    BuildSystem.CMAKE: "ctest --test-dir build",
    BuildSystem.NPM: "npm test",
    BuildSystem.PNPM: "pnpm test",
    BuildSystem.YARN: "yarn test",
    BuildSystem.BUN: "bun test",
    BuildSystem.POETRY: "pytest -q",
    BuildSystem.PDM: "pytest -q",
    BuildSystem.HATCH: "pytest -q",
    BuildSystem.FLIT: "pytest -q",
    BuildSystem.SETUPTOOLS: "pytest -q",
    BuildSystem.MATURIN: "pytest -q",
    BuildSystem.UV: "pytest -q",
    BuildSystem.GO: "go test ./...",
    BuildSystem.MAVEN: "mvn test",
    BuildSystem.GRADLE: "gradle test",
    BuildSystem.MAKE: "make test",
}


GIT_DIR = ".git"

WORKTREE_SKILL_BODY = """\
---
name: worktree
description: Create and manage isolated git worktrees for parallel work
user-invocable: true
---

# Worktree

Use `dekk worktree` to manage git worktrees with automatic environment setup.

## Commands

- `dekk worktree create <branch>` — create a new worktree with a fresh branch
- `dekk worktree create <branch> --base main` — branch from main
- `dekk worktree create <branch> --existing` — checkout an existing branch
- `dekk worktree create <branch> --no-setup` — skip automatic environment setup
- `dekk worktree list` — show all worktrees and their dekk status
- `dekk worktree remove <name>` — remove a worktree
- `dekk worktree remove <name> --force` — force-remove even with modifications
- `dekk worktree prune` — clean up stale references

## Project Integration

Worktrees are fully integrated with dekk's project command system:

1. Create a worktree: `dekk worktree create feature-x --base main`
2. Change to it: `cd ../$(basename $PWD)-worktrees/feature-x`
3. All project commands work immediately — `dekk` walks up to find `.dekk.toml`
4. The `.agents/` source of truth is shared across all worktrees (same repo)

## Key Behaviors

- Worktrees share the same `.dekk.toml` and `.agents/` (same git repo)
- Each worktree gets its own independent working directory for builds, tests, etc.
- `dekk worktree create` auto-runs `dekk setup` to prepare the environment
- By default worktrees are created at `../<repo>-worktrees/<branch>`
- Branch names with slashes (e.g., `feature/login`) become `feature-login` in the path

## When to Use

- Working on a feature while keeping main branch clean for reference
- Running tests on one branch while developing on another
- Reviewing a PR without stashing your current work
- Parallel builds or CI-like isolation
"""


@dataclass
class DiscoveredCommand:
    """A command discovered from Typer introspection or .dekk.toml."""

    name: str
    description: str
    run: str
    skill: bool = False


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
    """Read commands from a parsed EnvironmentSpec's ``commands`` dict.

    If any command has ``skill=True``, only skill commands are returned.
    If none do, all commands are returned (backward compat).

    Recursively walks command groups, emitting qualified names like ``llm/add``.
    """
    commands_dict = getattr(spec, TOML_COMMANDS_KEY, {})
    if not commands_dict:
        return []

    result: list[DiscoveredCommand] = []
    _collect_commands_recursive(commands_dict, "", result)

    # Filter to skill-only commands when at least one has skill=True.
    has_explicit_skills = any(cmd.skill for cmd in result)
    if has_explicit_skills:
        result = [cmd for cmd in result if cmd.skill]

    return result


def _collect_commands_recursive(
    commands_dict: dict[str, Any],
    prefix: str,
    result: list[DiscoveredCommand],
) -> None:
    """Walk a commands dict recursively, collecting DiscoveredCommand entries."""
    for name, cmd_spec in commands_dict.items():
        qualified = f"{prefix}/{name}" if prefix else name
        if hasattr(cmd_spec, "run"):
            # CommandSpec object (from EnvironmentSpec)
            run_cmd = cmd_spec.run
            desc = cmd_spec.description or name
            is_skill = cmd_spec.skill
            children = getattr(cmd_spec, "commands", {})
        elif isinstance(cmd_spec, dict):
            run_cmd = cmd_spec.get(TOML_RUN_KEY, name)
            desc = cmd_spec.get(TOML_DESCRIPTION_KEY, "") or name
            is_skill = cmd_spec.get(TOML_SKILL_KEY, False)
            children = {
                k: v for k, v in cmd_spec.items()
                if k not in RESERVED_COMMAND_KEYS
                and isinstance(v, (str, dict))
            }
        else:
            run_cmd = str(cmd_spec)
            desc = name
            is_skill = False
            children = {}

        if run_cmd:
            result.append(DiscoveredCommand(
                name=qualified,
                description=desc,
                run=run_cmd,
                skill=is_skill,
            ))

        if children:
            _collect_commands_recursive(children, qualified, result)


def _detect_project_info(project_root: Path) -> dict[str, str]:
    """Detect high-level project metadata for the scaffolded `project.md`."""
    info: dict[str, str] = {TOML_NAME_KEY: project_root.name}
    project_type = ProjectTypeDetector().detect(project_root)
    if project_type.language is not ProjectLanguage.UNKNOWN:
        info["language"] = LANGUAGE_DISPLAY_NAMES.get(
            project_type.language,
            project_type.language.value,
        )
    build_info = BuildSystemDetector().detect_first(project_root)
    if build_info is not None:
        if build_command := DETECTED_BUILD_COMMANDS.get(build_info.system):
            info["build"] = build_command
        if test_command := DETECTED_TEST_COMMANDS.get(build_info.system):
            info["test"] = test_command
    return info


def _apply_command_sections(
    project_info: dict[str, str],
    commands: list[DiscoveredCommand],
) -> None:
    """Populate build/test sections from discovered commands when present."""
    command_lookup = {command.name: command for command in commands}
    if BUILD_COMMAND_NAME in command_lookup:
        project_info["build"] = command_lookup[BUILD_COMMAND_NAME].run
    if TEST_COMMAND_NAME in command_lookup:
        project_info["test"] = command_lookup[TEST_COMMAND_NAME].run


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

    Handles hierarchical names like ``llm/add`` by creating nested directories.
    Only creates files that don't already exist (won't overwrite user customizations).

    Returns:
        List of created SKILL.md paths.
    """
    created: list[Path] = []
    for cmd in commands:
        # Support hierarchical names: "llm/add" -> skills/llm/add/SKILL.md
        skill_dir = skills_dir / cmd.name
        skill_file = skill_dir / SKILL_FILENAME
        if skill_file.exists():
            continue
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(_render_skill_md(cmd), encoding="utf-8")
        created.append(skill_file)
    return created


def _maybe_scaffold_worktree_skill(project_root: Path, skills_dir: Path) -> Path | None:
    """Auto-scaffold a worktree skill if the project is a git repo.

    Only creates the skill if the project has a ``.git`` directory and the
    worktree skill doesn't already exist.

    Returns:
        Path to the created SKILL.md, or None if skipped.
    """
    if not (project_root / GIT_DIR).exists():
        return None

    skill_dir = skills_dir / WORKTREE_SKILL_NAME
    skill_file = skill_dir / SKILL_FILENAME
    if skill_file.exists():
        return None

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(WORKTREE_SKILL_BODY, encoding="utf-8")
    return skill_file


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
        toml_project_name = data.get(TOML_PROJECT_KEY, {}).get(TOML_NAME_KEY)
        toml_commands = data.get(TOML_COMMANDS_KEY, {})
        # Use recursive discovery (handles hierarchical commands)
        toml_discovered: list[DiscoveredCommand] = []
        _collect_commands_recursive(toml_commands, "", toml_discovered)
        # Filter to skill-only when at least one has skill=True
        has_explicit_skills = any(cmd.skill for cmd in toml_discovered)
        for cmd in toml_discovered:
            if has_explicit_skills and not cmd.skill:
                continue
            if cmd.name not in seen_names:
                all_commands.append(cmd)
                seen_names.add(cmd.name)

    # Detect project info
    project_info = _detect_project_info(project_root)
    _apply_command_sections(project_info, all_commands)
    project_name = toml_project_name or project_info.get(TOML_NAME_KEY, project_root.name)

    # Generate skill templates from commands
    commands_to_skills(all_commands, skills_dir)

    # Auto-generate worktree skill if this is a git repo
    _maybe_scaffold_worktree_skill(project_root, skills_dir)

    # Generate project.md
    project_md = target / PROJECT_MD
    if not project_md.exists() or force:
        content = _render_project_md(project_name, project_info, all_commands)
        project_md.write_text(content, encoding="utf-8")

    return target
