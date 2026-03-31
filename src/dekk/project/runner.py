"""Run project commands via nearest `.dekk.toml` context."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from dekk.cli.errors import NotFoundError, ValidationError
from dekk.environment.activation import EnvironmentActivator
from dekk.environment.resolver import resolve_environment
from dekk.environment.spec import EnvironmentSpec, find_envspec

PREPEND_ENV_VARS = {
    "PATH",
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "PYTHONPATH",
    "PKG_CONFIG_PATH",
}


def run_project_command(app_name: str, argv: list[str]) -> int:
    """Run a command from `[commands]` in the nearest project spec."""
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
            hint=f"Use 'dekk {spec.project_name} ...' from this worktree",
        )

    resolved = resolve_environment(spec, project_root=project_root)
    if resolved is not None and not resolved.exists():
        raise NotFoundError(
            f"Environment prefix not found: {resolved.prefix}",
            hint="Run `dekk setup` to create the runtime environment",
        )

    if not argv:
        available = ", ".join(sorted(spec.commands.keys())) or "<none>"
        raise ValidationError(
            "Missing project command",
            hint=f"Usage: dekk {app_name} <command> [args...] (available: {available})",
        )

    command_name, *command_args = argv
    if command_name not in spec.commands:
        available = ", ".join(sorted(spec.commands.keys())) or "<none>"
        raise NotFoundError(
            f"Unknown command '{command_name}' for project '{app_name}'",
            hint=f"Available commands: {available}",
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


__all__ = ["run_project_command"]
