"""Run project commands via nearest `.dekk.toml` context."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from dekk.cli.errors import NotFoundError, ValidationError
from dekk.environment.activation import EnvironmentActivator
from dekk.environment.resolver import resolve_environment
from dekk.environment.spec import EnvironmentSpec, find_envspec
from dekk.project.subcommands import CLI_NAME, PROJECT_BUILTIN_DESCRIPTIONS
from dekk.project.subcommands import INSTALL as PROJECT_INSTALL_COMMAND
from dekk.project.subcommands import NAMES as BUILTIN_PROJECT_SUBCOMMANDS
from dekk.project.subcommands import SETUP as PROJECT_SETUP_COMMAND
from dekk.project.subcommands import UNINSTALL as PROJECT_UNINSTALL_COMMAND

PROJECT_HELP_COMMANDS = {"help", "--help", "-h"}
PREPEND_ENV_VARS = {
    "PATH",
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "PYTHONPATH",
    "PKG_CONFIG_PATH",
}


def run_project_command(app_name: str, argv: list[str]) -> int:
    """Run a command from `[commands]` or a built-in sub-command in the nearest project spec.

    Built-in project sub-commands (``agents``, ``worktree``) are routed
    directly without environment activation.  User-defined ``[commands]``
    entries are run via ``subprocess`` with the activated environment.
    """
    # Catch attempts to use sub-commands directly without an app name
    # e.g., `dekk agents init` instead of `dekk myapp agents init`
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
            _print_command_help(spec, command_args[0])
        else:
            _print_project_help(spec)
        return 0

    # Built-in project sub-commands (agents, worktree)
    if _is_builtin_project_command(spec, command_name):
        return _run_builtin_subcommand(command_name, command_args, project_root)

    if command_name not in spec.commands:
        available = _available_commands(spec)
        raise NotFoundError(
            f"Unknown command '{command_name}' for project '{app_name}'",
            hint=f"Available commands: {available}",
        )

    resolved = resolve_environment(spec, project_root=project_root)
    if resolved is not None and not resolved.exists():
        raise NotFoundError(
            f"Environment prefix not found: {resolved.prefix}",
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

    base = spec.commands[command_name].run
    full_cmd = f"{base} {shlex.join(command_args)}" if command_args else base
    result = subprocess.run(full_cmd, shell=True, cwd=project_root, env=env, check=False)
    return int(result.returncode)


def _available_commands(spec: EnvironmentSpec) -> str:
    """Return a comma-separated list of available commands including built-in sub-commands."""
    cmds = sorted(spec.commands.keys())
    cmds.extend(
        name for name in sorted(PROJECT_BUILTIN_DESCRIPTIONS) if name not in spec.commands
    )
    return ", ".join(cmds) or "<none>"


def _project_commands(spec: EnvironmentSpec) -> list[tuple[str, str]]:
    commands = [
        (name, PROJECT_BUILTIN_DESCRIPTIONS[name])
        for name in sorted(PROJECT_BUILTIN_DESCRIPTIONS)
        if name not in spec.commands
    ]
    commands.extend(
        (name, spec.commands[name].description or f"Run {name}")
        for name in sorted(spec.commands)
    )
    return commands


def _print_project_help(spec: EnvironmentSpec) -> None:
    lines = [
        f"Project commands for '{spec.project_name}'",
        "",
        "Usage:",
        f"  {CLI_NAME} {spec.project_name} <command> [args...]",
        f"  {CLI_NAME} {spec.project_name} help [command]",
        "",
        "Commands:",
    ]
    for name, description in _project_commands(spec):
        lines.append(f"  {name:<12} {description}")
    lines.extend(
        [
            "",
            "Notes:",
            f"  - Run `{CLI_NAME} {spec.project_name} <command> --help` for command-specific help.",
            "  - Built-in project tools: "
            + ", ".join(
                n for n in sorted(PROJECT_BUILTIN_DESCRIPTIONS) if n not in spec.commands
            )
            + ".",
        ]
    )
    print("\n".join(lines))


def _print_command_help(spec: EnvironmentSpec, command_name: str) -> None:
    if _is_builtin_project_command(spec, command_name):
        description = PROJECT_BUILTIN_DESCRIPTIONS[command_name]
    elif command_name in spec.commands:
        description = spec.commands[command_name].description or f"Run {command_name}"
    else:
        available = _available_commands(spec)
        raise NotFoundError(
            f"Unknown command '{command_name}' for project '{spec.project_name}'",
            hint=f"Available commands: {available}",
        )

    lines = [
        f"{spec.project_name}:{command_name}",
        f"  {description}",
        "",
        "Usage:",
        f"  {CLI_NAME} {spec.project_name} {command_name} [args...]",
        f"  {CLI_NAME} {spec.project_name} {command_name} --help",
    ]

    if _is_builtin_project_command(spec, command_name):
        lines.append("")
        lines.append("This is a dekk built-in project sub-command.")
    else:
        lines.append("")
        lines.append("This command is defined in `.dekk.toml` under `[commands]`.")

    print("\n".join(lines))


def _is_builtin_project_command(spec: EnvironmentSpec, command_name: str) -> bool:
    if command_name in BUILTIN_PROJECT_SUBCOMMANDS:
        return True
    if command_name == PROJECT_SETUP_COMMAND and command_name not in spec.commands:
        return True
    if command_name == PROJECT_INSTALL_COMMAND and command_name not in spec.commands:
        return True
    if command_name == PROJECT_UNINSTALL_COMMAND and command_name not in spec.commands:
        return True
    return False


def _run_builtin_subcommand(
    command_name: str, args: list[str], project_root: Path
) -> int:
    """Invoke a built-in project sub-command (agents or worktree).

    These sub-commands are Typer apps that run in-process.  ``cwd`` is
    temporarily changed to *project_root* so that path-walking helpers
    resolve correctly, and ``sys.argv`` is adjusted so Typer/Click parses
    the right arguments.
    """
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
    from dekk.cli.styles import print_info, print_success

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
    for msg in messages:
        if "nothing to remove" in msg.lower() or "not found" in msg.lower():
            print_info(msg)
        else:
            print_success(msg)

    return 0


__all__ = ["run_project_command"]
