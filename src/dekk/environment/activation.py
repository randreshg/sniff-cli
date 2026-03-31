"""Environment activation from .dekk.toml specifications."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dekk.cli.errors import NotFoundError
from dekk.environment.resolver import resolve_environment
from dekk.environment.spec import EnvironmentSpec, find_envspec
from dekk.shell import ActivationScriptBuilder, ShellDetector, ShellKind
from dekk.execution.toolchain import EnvVarBuilder
from dekk.diagnostics.validation_cache import get_cache


@dataclass
class ActivationResult:
    """Result of environment activation."""

    env_vars: dict[str, str] = field(default_factory=dict)
    missing_tools: list[str] = field(default_factory=list)
    activation_script: str | None = None


class EnvironmentActivator:
    """Activate project environment from .dekk.toml specification."""

    def __init__(self, spec: EnvironmentSpec, project_root: Path):
        self.spec = spec
        self.project_root = project_root

    def activate(
        self, shell: str | ShellKind | None = None, use_cache: bool = True
    ) -> ActivationResult:
        """Activate environment and return result."""
        resolved = resolve_environment(self.spec, project_root=self.project_root)
        cache_key = str(resolved.prefix) if resolved else "no-environment"
        if use_cache and resolved:
            if cached := get_cache().get(self.project_root, cache_key):
                return ActivationResult(
                    env_vars=cached.env_vars,
                    missing_tools=cached.missing_tools,
                )

        environment_prefix = None
        if resolved and resolved.exists():
            environment_prefix = resolved.prefix

        builder = EnvVarBuilder()

        if resolved and environment_prefix:
            resolved.configure(builder, project_name=self.spec.project_name, tools=self.spec.tools)

        for key, value in self.spec.expand_placeholders(self.project_root, environment_prefix).items():
            if key.upper() in ("PATH", "BIN"):
                for path in value.split(os.pathsep):
                    builder.prepend_path(path)
            elif key.upper() in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
                for path in value.split(os.pathsep):
                    builder.prepend_var(key, path)
            else:
                builder.set_var(key, value)

        env_vars = builder.to_env_dict()

        effective_path = os.environ.get("PATH", "")
        if path_prefix := env_vars.get("PATH"):
            effective_path = (
                f"{path_prefix}{os.pathsep}{effective_path}" if effective_path else path_prefix
            )

        missing_tools = [
            name
            for name, spec in self.spec.tools.items()
            if not spec.optional and not shutil.which(spec.command, path=effective_path)
        ]

        activation_script = None
        if shell:
            shell_kind = (
                shell
                if isinstance(shell, ShellKind)
                else ShellDetector().detect(shell_override=shell).kind
            )
            activation_script = ActivationScriptBuilder().build(builder.build(), shell_kind)

        if use_cache and resolved:
            get_cache().set(
                self.project_root,
                cache_key,
                environment_prefix,
                env_vars,
                missing_tools,
            )

        return ActivationResult(
            env_vars=env_vars,
            missing_tools=missing_tools,
            activation_script=activation_script,
        )

    @classmethod
    def from_path(cls, start_dir: Path) -> EnvironmentActivator:
        """Create an activator by locating .dekk.toml from *start_dir* upward."""
        spec_file = find_envspec(start_dir)
        if not spec_file:
            raise NotFoundError(
                "No .dekk.toml found",
                hint="Run 'dekk init' to create one, or navigate to a project directory",
            )

        spec = EnvironmentSpec.from_file(spec_file)
        return cls(spec, spec_file.parent)

    @classmethod
    def from_cwd(cls) -> EnvironmentActivator:
        """Create activator by finding .dekk.toml from current directory."""
        return cls.from_path(Path.cwd())


__all__ = ["ActivationResult", "EnvironmentActivator"]
