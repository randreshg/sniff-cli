"""Run project commands via nearest `.dekk.toml` context."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from dekk.cli.errors import NotFoundError, ValidationError
from dekk.environment.activation import EnvironmentActivator
from dekk.environment.resolver import resolve_environment
from dekk.environment.spec import (
    PREPEND_ENV_VARS,
    CommandSpec,
    EnvironmentSpec,
    find_envspec,
)
from dekk.project.subcommands import CLI_NAME, PROJECT_BUILTIN_DESCRIPTIONS
from dekk.project.subcommands import DOCTOR as PROJECT_DOCTOR_COMMAND
from dekk.project.subcommands import INSTALL as PROJECT_INSTALL_COMMAND
from dekk.project.subcommands import NAMES as BUILTIN_PROJECT_SUBCOMMANDS
from dekk.project.subcommands import SETUP as PROJECT_SETUP_COMMAND
from dekk.project.subcommands import UNINSTALL as PROJECT_UNINSTALL_COMMAND

PROJECT_HELP_COMMANDS = {"help", "--help", "-h"}


# ---------------------------------------------------------------------------
# Command tree resolution
# ---------------------------------------------------------------------------


def _resolve_command(
    spec: EnvironmentSpec, argv: list[str]
) -> tuple[CommandSpec | None, list[str], list[str]]:
    """Walk the command tree consuming argv tokens that match child names.

    Returns:
        (resolved_command_spec, remaining_argv, command_path)

    ``command_path`` is the list of names consumed (e.g., ["llm", "add"]).
    Returns ``(None, argv, [])`` when the first token doesn't match.
    """
    commands = spec.commands
    path: list[str] = []

    if not argv or argv[0] not in commands:
        return None, argv, path

    node = commands[argv[0]]
    path.append(argv[0])
    rest = argv[1:]

    while rest and node.is_group and rest[0] in node.commands:
        node = node.commands[rest[0]]
        path.append(rest[0])
        rest = rest[1:]

    return node, rest, path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_project_command(app_name: str, argv: list[str]) -> int:
    """Run a command from `[commands]` or a built-in sub-command in the nearest project spec.

    Built-in project sub-commands (``skills``, ``worktree``) are routed
    directly without environment activation.  User-defined ``[commands]``
    entries are run via ``subprocess`` with the activated environment.
    """
    # Catch attempts to use sub-commands directly without an app name
    # e.g., `dekk skills init` instead of `dekk myapp skills init`
    if app_name in BUILTIN_PROJECT_SUBCOMMANDS:
        spec_file = find_envspec(Path.cwd())
        project_name = "<appname>"
        if spec_file is not None:
            spec = EnvironmentSpec.from_file(spec_file)
            project_name = spec.project_name or "<appname>"
        full_cmd = " ".join([app_name] + argv)
        raise ValidationError(
            f"'{app_name}' is a project sub-command, not an app name",
            hint=f"Use '{CLI_NAME} {project_name} {full_cmd}'",
        )

    spec_file = find_envspec(Path.cwd())
    if spec_file is None:
        raise NotFoundError(
            "No .dekk.toml found in current directory hierarchy",
            hint="Run from inside a project directory or pass through a dekk command",
        )

    spec = EnvironmentSpec.from_file(spec_file)
    project_root = spec_file.parent

    if spec.project_name != app_name:
        raise ValidationError(
            f"App '{app_name}' does not match project '{spec.project_name}'",
            hint=f"Use '{CLI_NAME} {spec.project_name} ...' from this worktree",
        )

    if not argv:
        _print_project_help(spec)
        return 0

    command_name, *command_args = argv

    if command_name in PROJECT_HELP_COMMANDS:
        if command_args:
            _print_command_help(spec, command_args)
        else:
            _print_project_help(spec)
        return 0

    # Built-in project sub-commands (skills, worktree)
    if _is_builtin_project_command(spec, command_name):
        return _run_builtin_subcommand(command_name, command_args, project_root)

    # Resolve through the command tree
    resolved, remaining_args, cmd_path = _resolve_command(spec, argv)
    if resolved is None:
        available = _available_commands(spec)
        raise NotFoundError(
            f"Unknown command '{command_name}' for project '{app_name}'",
            hint=f"Available commands: {available}",
        )

    # If resolved node is a group with no run and no further match, show group help
    if resolved.is_group and not resolved.run and not remaining_args:
        _print_group_help(spec, resolved, cmd_path)
        return 0

    # If they asked for help on a group subcommand
    if remaining_args and remaining_args[0] in PROJECT_HELP_COMMANDS:
        if resolved.is_group:
            _print_group_help(spec, resolved, cmd_path)
        else:
            _print_leaf_help(spec, resolved, cmd_path)
        return 0

    # Leaf command must have a run field
    if not resolved.run:
        if resolved.is_group:
            _print_group_help(spec, resolved, cmd_path)
            return 0
        qualified = " ".join(cmd_path)
        raise ValidationError(
            f"Command '{qualified}' has no 'run' field",
            hint=f"Add 'run = \"...\"' to [commands.{'.'.join(cmd_path)}] in .dekk.toml",
        )

    # Activate environment and run
    resolved_env = resolve_environment(spec, project_root=project_root)
    if resolved_env is not None and not resolved_env.exists():
        raise NotFoundError(
            f"Environment prefix not found: {resolved_env.prefix}",
            hint=(
                f"Run `{CLI_NAME} {spec.project_name} {PROJECT_SETUP_COMMAND}` "
                "to create the runtime environment"
            ),
        )

    activation = EnvironmentActivator(spec, project_root).activate()
    env = dict(os.environ)
    for key, value in activation.env_vars.items():
        if key in PREPEND_ENV_VARS:
            current = env.get(key, "")
            env[key] = f"{value}{os.pathsep}{current}" if current else value
        else:
            env[key] = value

    base = resolved.run
    full_cmd = f"{base} {shlex.join(remaining_args)}" if remaining_args else base
    result = subprocess.run(full_cmd, shell=True, cwd=project_root, env=env, check=False)

    qualified_name = " ".join(cmd_path)

    if result.returncode == 127:
        raise NotFoundError(
            f"Command '{qualified_name}' failed: '{base}' not found",
            hint=(
                f"Check the 'run' field in .dekk.toml or ensure the binary is on PATH. "
                f"Run `{CLI_NAME} {spec.project_name} doctor` to check dependencies."
            ),
        )

    if result.returncode == 0:
        # Show skill hint for the leaf command name
        leaf_name = cmd_path[-1] if cmd_path else command_name
        skill_path = "/".join(cmd_path) if len(cmd_path) > 1 else leaf_name
        skill_file = project_root / ".agents" / "skills" / skill_path / "SKILL.md"
        if skill_file.exists():
            from rich.text import Text

            from dekk.cli.styles import _get_console

            _get_console().print(
                Text(f"skill: .agents/skills/{skill_path}/SKILL.md", style="dim")
            )

    return int(result.returncode)


# ---------------------------------------------------------------------------
# Available commands (for error hints)
# ---------------------------------------------------------------------------


def _available_commands(spec: EnvironmentSpec) -> str:
    """Return a comma-separated list of available commands including built-in sub-commands."""
    cmds = sorted(spec.commands.keys())
    cmds.extend(
        name for name in sorted(PROJECT_BUILTIN_DESCRIPTIONS) if name not in spec.commands
    )
    return ", ".join(cmds) or "<none>"


# ---------------------------------------------------------------------------
# Help: grouped project help
# ---------------------------------------------------------------------------


def _collect_grouped_commands(
    spec: EnvironmentSpec,
) -> list[tuple[str, list[tuple[str, str, bool, bool]]]]:
    """Collect commands organized by group.

    Returns list of (group_name, [(name, description, is_skill, is_group), ...]).
    Empty group name means ungrouped.
    """
    groups: dict[str, list[tuple[str, str, bool, bool]]] = defaultdict(list)

    for name in sorted(spec.commands):
        cmd = spec.commands[name]
        group_key = cmd.group or ""
        groups[group_key].append((name, cmd.description or f"Run {name}", cmd.skill, cmd.is_group))

    # Built-in commands go in their own "Built-in" group
    builtin_entries: list[tuple[str, str, bool, bool]] = []
    for name in sorted(PROJECT_BUILTIN_DESCRIPTIONS):
        if name not in spec.commands:
            builtin_entries.append((name, PROJECT_BUILTIN_DESCRIPTIONS[name], False, False))

    # Build ordered output: ungrouped first, then named groups alphabetically, then built-in
    result: list[tuple[str, list[tuple[str, str, bool, bool]]]] = []
    if "" in groups:
        result.append(("", groups.pop("")))
    for group_name in sorted(groups):
        result.append((group_name, groups[group_name]))
    if builtin_entries:
        result.append(("Built-in", builtin_entries))

    return result


def _print_help_header(title: str, description: str = "") -> None:
    """Print a standard help header with title, optional description, and separator."""
    from dekk.cli.styles import print_header

    print_header(title, subtitle=description or None)


def _format_command_entry(
    name: str, description: str, is_skill: bool, is_group: bool
) -> object:
    """Format a single command entry line for help output."""
    from rich.text import Text

    from dekk.cli.styles import Colors

    line = Text("  ")
    line.append(f"{name:<14}", style=Colors.INFO)
    line.append(f" {description}")
    if is_group:
        line.append(" \u2192")
    if is_skill:
        line.append(" [skill]", style="dim")
    return line


def _print_usage(prefix: str, patterns: list[str]) -> None:
    """Print a polished Usage: block with aligned continuation lines."""
    from rich.text import Text

    from dekk.cli.styles import Colors, _get_console

    c = _get_console()
    for i, pat in enumerate(patterns):
        line = Text()
        if i == 0:
            line.append("Usage: ", style=Colors.STEP)
        else:
            line.append(" " * 7)  # align with first pattern
        line.append(f"{prefix} ")
        line.append(pat, style="dim")
        c.print(line)


def _print_project_help(spec: EnvironmentSpec) -> None:
    from rich.text import Text

    from dekk.cli.styles import Colors, _get_console

    c = _get_console()
    _print_help_header(spec.project_name)
    _print_usage(f"{CLI_NAME} {spec.project_name}", ["<COMMAND> [ARGS]...", "help [COMMAND]"])

    grouped = _collect_grouped_commands(spec)
    for group_name, entries in grouped:
        c.print()
        c.print(Text(group_name or "Commands", style=Colors.STEP))

        for name, description, is_skill, is_group in entries:
            c.print(_format_command_entry(name, description, is_skill, is_group))


def _print_group_help(
    spec: EnvironmentSpec,
    group: CommandSpec,
    cmd_path: list[str],
) -> None:
    """Print help for a command group (e.g., ``dekk app llm``)."""
    from rich.text import Text

    from dekk.cli.styles import Colors, _get_console

    c = _get_console()
    breadcrumb = " > ".join(cmd_path)
    _print_help_header(f"{spec.project_name} > {breadcrumb}", group.description)
    path_str = " ".join(cmd_path)
    _print_usage(f"{CLI_NAME} {spec.project_name} {path_str}", ["<COMMAND> [ARGS]..."])
    c.print()
    c.print(Text("Commands", style=Colors.STEP))

    for name in sorted(group.commands):
        child = group.commands[name]
        desc = child.description or f"Run {name}"
        c.print(_format_command_entry(name, desc, child.skill, child.is_group))


def _print_leaf_help(
    spec: EnvironmentSpec,
    cmd: CommandSpec,
    cmd_path: list[str],
) -> None:
    """Print help for a leaf command."""
    from rich.text import Text

    from dekk.cli.styles import _get_console

    qualified = ":".join(cmd_path)
    desc = cmd.description or f"Run {cmd_path[-1]}"
    _print_help_header(f"{spec.project_name}:{qualified}", desc)
    path_str = " ".join(cmd_path)
    _print_usage(f"{CLI_NAME} {spec.project_name} {path_str}", ["[ARGS]...", "--help"])
    _get_console().print(Text("Defined in `.dekk.toml` under [commands].", style="dim"))


def _print_command_help(spec: EnvironmentSpec, args: list[str]) -> None:
    """Print help for a command, supporting dotted paths (e.g., ``help llm add``)."""
    command_name = args[0]

    if _is_builtin_project_command(spec, command_name):
        from rich.text import Text

        from dekk.cli.styles import _get_console

        description = PROJECT_BUILTIN_DESCRIPTIONS[command_name]
        _print_help_header(f"{spec.project_name}:{command_name}", description)
        _print_usage(
            f"{CLI_NAME} {spec.project_name} {command_name}",
            ["[ARGS]...", "--help"],
        )
        _get_console().print(Text("dekk built-in project sub-command.", style="dim"))
        return

    # Walk the command tree with the help args
    resolved, _, cmd_path = _resolve_command(spec, args)
    if resolved is None:
        available = _available_commands(spec)
        raise NotFoundError(
            f"Unknown command '{command_name}' for project '{spec.project_name}'",
            hint=f"Available commands: {available}",
        )

    if resolved.is_group:
        _print_group_help(spec, resolved, cmd_path)
    else:
        _print_leaf_help(spec, resolved, cmd_path)


# ---------------------------------------------------------------------------
# Built-in command routing
# ---------------------------------------------------------------------------


_OVERRIDABLE_BUILTINS = frozenset({
    PROJECT_DOCTOR_COMMAND,
    PROJECT_SETUP_COMMAND,
    PROJECT_INSTALL_COMMAND,
    PROJECT_UNINSTALL_COMMAND,
})


def _is_builtin_project_command(spec: EnvironmentSpec, command_name: str) -> bool:
    if command_name in BUILTIN_PROJECT_SUBCOMMANDS:
        return True
    return command_name in _OVERRIDABLE_BUILTINS and command_name not in spec.commands


def _run_builtin_subcommand(
    command_name: str, args: list[str], project_root: Path
) -> int:
    """Invoke a built-in project sub-command (skills or worktree).

    These sub-commands are Typer apps that run in-process.  ``cwd`` is
    temporarily changed to *project_root* so that path-walking helpers
    resolve correctly, and ``sys.argv`` is adjusted so Typer/Click parses
    the right arguments.
    """
    if command_name == PROJECT_DOCTOR_COMMAND:
        return _run_project_doctor(args, project_root)

    if command_name == PROJECT_SETUP_COMMAND:
        return _run_project_setup(args, project_root)

    if command_name == PROJECT_INSTALL_COMMAND:
        return _run_project_install(args, project_root)

    if command_name == PROJECT_UNINSTALL_COMMAND:
        return _run_project_uninstall(args, project_root)

    from dekk.project.subcommands import create_app

    sub = create_app(command_name, project_root)

    saved_argv = sys.argv
    saved_cwd = Path.cwd()
    sys.argv = [f"{CLI_NAME} {command_name}"] + args
    try:
        os.chdir(project_root)
        sub()
        return 0
    except SystemExit as exc:
        return int(exc.code) if exc.code else 0
    finally:
        sys.argv = saved_argv
        os.chdir(saved_cwd)


def _run_project_doctor(args: list[str], project_root: Path) -> int:
    """Run `dekk <app> doctor` — check project tool dependencies."""
    from dekk.cli.output import check_tool_specs
    from dekk.cli.styles import print_blank, print_error, print_section, print_success

    spec = EnvironmentSpec.from_file(project_root / ".dekk.toml")

    # Activate environment so env-provided tools are on PATH
    activated_path: str | None = None
    if spec.environment:
        try:
            activation = EnvironmentActivator(spec, project_root).activate()
            env = dict(os.environ)
            for key, value in activation.env_vars.items():
                if key in PREPEND_ENV_VARS:
                    current = env.get(key, "")
                    env[key] = f"{value}{os.pathsep}{current}" if current else value
                else:
                    env[key] = value
            activated_path = env.get("PATH")
        except Exception:
            pass  # check tools with current PATH

    has_issues = False

    # Project-wide [tools]
    if spec.tools:
        print_section("Project Tools")
        missing = check_tool_specs(spec.tools, path=activated_path)
        if missing:
            has_issues = True

    # Per-component requires
    if spec.install and spec.install.components:
        comps_with_requires = [c for c in spec.install.components if c.requires]
        if comps_with_requires:
            print_section("Component Requirements")
            import shutil

            for comp in comps_with_requires:
                comp_missing = [
                    r for r in comp.requires
                    if not shutil.which(r, path=activated_path)
                ]
                if comp_missing:
                    print_error(f"{comp.label}: missing {', '.join(comp_missing)}")
                    has_issues = True
                else:
                    print_success(f"{comp.label}: all requirements met")

    print_blank()
    if has_issues:
        print_error("Some tools are missing or need upgrading.")
        return 1
    else:
        print_success("All project dependencies satisfied.")
        return 0


def _run_project_setup(args: list[str], project_root: Path) -> int:
    """Run `dekk <app> setup` from the resolved project root."""
    from dekk.cli.styles import print_error, print_info, print_success
    from dekk.environment.setup import run_setup

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} <appname> {PROJECT_SETUP_COMMAND}",
        description=PROJECT_BUILTIN_DESCRIPTIONS[PROJECT_SETUP_COMMAND],
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Recreate the runtime environment even if it exists",
    )
    parsed = parser.parse_args(args)

    result = run_setup(project_root, force=parsed.force)

    env_label = result.environment_kind.value if result.environment_kind else "environment"
    if result.environment_created and result.environment_prefix:
        print_success(f"Created {env_label}: {result.environment_prefix.name}")
        if result.environment_packages:
            print_info(f"  Packages: {', '.join(result.environment_packages)}")
    elif result.environment_prefix:
        print_info(f"{env_label.capitalize()} already exists: {result.environment_prefix.name}")

    for pkg in result.npm_installed:
        print_success(f"  npm: {pkg}")
    if result.npm_installed:
        print_info(f"Installed {len(result.npm_installed)} npm package(s)")

    for err in result.errors:
        print_error(err)

    if not result.ok:
        return 1

    if result.environment_prefix:
        print_info(f"Runtime available at: {result.environment_prefix}")
        print_info(f"Run `{CLI_NAME} <appname> doctor` or your project command next.")

    return 0


def _run_project_install(args: list[str], project_root: Path) -> int:
    """Run `dekk <app> install` from the resolved project root."""
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} <appname> {PROJECT_INSTALL_COMMAND}",
        description=PROJECT_BUILTIN_DESCRIPTIONS[PROJECT_INSTALL_COMMAND],
    )
    parser.add_argument(
        "--force", "-f", action="store_true",
        help="Recreate environment even if it exists",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show log tail on error (for humans; agents prefer reading the log file)",
    )
    parser.add_argument(
        "--wrap", action="store_true",
        help="Also install a global CLI wrapper (not worktree-safe)",
    )
    parser.add_argument(
        "--all", action="store_true", dest="install_all",
        help="Install all optional components (no prompt)",
    )
    parser.add_argument(
        "--components", type=str, default=None,
        help="Comma-separated list of components to install (no prompt)",
    )
    parser.add_argument(
        "--no-interactive", action="store_true",
        help="Use defaults without prompting (for agents/CI)",
    )
    parsed = parser.parse_args(args)

    # Determine component selection mode
    comp_list: list[str] | None = None
    interactive = not parsed.no_interactive
    if parsed.install_all:
        spec = EnvironmentSpec.from_file(project_root / ".dekk.toml")
        if spec.install and spec.install.components:
            comp_list = [c.name for c in spec.install.components]
        interactive = False
    elif parsed.components:
        comp_list = [c.strip() for c in parsed.components.split(",")]
        interactive = False

    from dekk.environment.install import run_install

    result = run_install(
        project_root,
        force=parsed.force,
        verbose=parsed.verbose,
        wrap=parsed.wrap,
        interactive=interactive,
        components=comp_list,
    )
    return 0 if result.ok else 1


def _run_project_uninstall(args: list[str], project_root: Path) -> int:
    """Run `dekk <app> uninstall` to remove environment, wrappers, and dekk state."""
    from dekk.cli.styles import print_info

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} <appname> {PROJECT_UNINSTALL_COMMAND}",
        description=PROJECT_BUILTIN_DESCRIPTIONS[PROJECT_UNINSTALL_COMMAND],
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip confirmation prompt",
    )
    parsed = parser.parse_args(args)

    dekk_dir = project_root / ".dekk"
    env_dir = dekk_dir / "env"
    install_dir = project_root / ".install"
    spec = EnvironmentSpec.from_file(project_root / ".dekk.toml")

    has_env = env_dir.is_dir()
    has_log = (dekk_dir / "install.log").is_file()
    has_wrapper = (
        spec.install is not None
        and spec.install.wrap is not None
        and (install_dir / spec.install.wrap.name).exists()
    )

    if not has_env and not has_log and not has_wrapper:
        print_info("Nothing to uninstall.")
        return 0

    if not parsed.yes:
        print_info("This will remove:")
        if has_env:
            print_info(f"  - Runtime environment: {env_dir}")
        if has_wrapper and spec.install and spec.install.wrap:
            print_info(f"  - CLI wrapper: {install_dir / spec.install.wrap.name}")
            print_info("  - Shell PATH entry (if added by dekk)")
        if has_log:
            print_info(f"  - Install log: {dekk_dir / 'install.log'}")
        try:
            answer = input("\nContinue? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            print_info("Cancelled.")
            return 1
        if answer not in ("y", "yes"):
            print_info("Cancelled.")
            return 1

    from dekk.environment.install import run_uninstall

    messages = run_uninstall(project_root)
    if not messages or all("nothing" in m.lower() for m in messages):
        print_info("Nothing to remove.")

    return 0


__all__ = ["run_project_command"]
