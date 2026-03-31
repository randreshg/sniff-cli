"""Run project commands via nearest `.dekk.toml` context."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from dekk.cli.errors import NotFoundError, ValidationError
from dekk.environment.activation import EnvironmentActivator
from dekk.environment.resolver import resolve_environment
from dekk.environment.spec import EnvironmentSpec, find_envspec
from dekk.project.subcommands import CLI_NAME
from dekk.project.subcommands import NAMES as BUILTIN_PROJECT_SUBCOMMANDS

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
        available = _available_commands(spec)
        raise ValidationError(
            "Missing project command",
            hint=f"Usage: {CLI_NAME} {app_name} <command> [args...] (available: {available})",
        )

    command_name, *command_args = argv

    # Built-in project sub-commands (agents, worktree)
    if command_name in BUILTIN_PROJECT_SUBCOMMANDS:
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
            hint=f"Run `{CLI_NAME} setup` to create the runtime environment",
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
    cmds = sorted(spec.commands.keys()) + sorted(BUILTIN_PROJECT_SUBCOMMANDS)
    return ", ".join(cmds) or "<none>"


def _run_builtin_subcommand(
    command_name: str, args: list[str], project_root: Path
) -> int:
    """Invoke a built-in project sub-command (agents or worktree).

    These sub-commands are Typer apps that run in-process.  ``cwd`` is
    temporarily changed to *project_root* so that path-walking helpers
    resolve correctly, and ``sys.argv`` is adjusted so Typer/Click parses
    the right arguments.
    """
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


__all__ = ["run_project_command"]
