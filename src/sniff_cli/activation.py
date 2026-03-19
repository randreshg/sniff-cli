"""Environment activation from .sniff-cli.toml specifications."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .cli.errors import NotFoundError
from .conda import CondaDetector
from .envspec import EnvironmentSpec, find_envspec
from .shell import ActivationScriptBuilder, ShellDetector, ShellKind
from .toolchain import CMakeToolchain, CondaToolchain, EnvVarBuilder
from .validation_cache import get_cache


@dataclass
class ActivationResult:
    """Result of environment activation."""

    env_vars: dict[str, str] = field(default_factory=dict)
    missing_tools: list[str] = field(default_factory=list)
    activation_script: Optional[str] = None


class EnvironmentActivator:
    """Activate project environment from .sniff-cli.toml specification."""

    def __init__(self, spec: EnvironmentSpec, project_root: Path):
        self.spec = spec
        self.project_root = project_root

    def activate(self, shell: Optional[str | ShellKind] = None, use_cache: bool = True) -> ActivationResult:
        """Activate environment and return result.

        Args:
            shell: Shell type for activation script
            use_cache: Use cached results for speed
        """
        # Try cache first
        if use_cache and self.spec.conda:
            if cached := get_cache().get(self.project_root, self.spec.conda.name):
                return ActivationResult(
                    env_vars=cached.env_vars,
                    missing_tools=cached.missing_tools,
                )

        # Detect conda environment
        conda_env = None
        conda_prefix = None
        if self.spec.conda:
            conda_env = CondaDetector().find_environment(self.spec.conda.name)
            if conda_env:
                conda_prefix = conda_env.prefix

        # Build environment variables
        builder = EnvVarBuilder()

        # Add conda toolchain
        if conda_prefix:
            CondaToolchain(conda_prefix, self.spec.project_name).configure(builder)
            if any(k.lower() == "cmake" for k in self.spec.tools):
                CMakeToolchain(conda_prefix).configure(builder)

        # Add custom env vars and paths from .sniff-cli.toml
        for key, value in self.spec.expand_placeholders(self.project_root, conda_prefix).items():
            if key.upper() in ("PATH", "BIN"):
                for path in value.split(os.pathsep):
                    builder.prepend_path(path)
            elif key.upper() in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
                for path in value.split(os.pathsep):
                    builder.prepend_var(key, path)
            else:
                builder.set_var(key, value)

        env_vars = builder.to_env_dict()

        # Validate tools
        effective_path = os.environ.get("PATH", "")
        if path_prefix := env_vars.get("PATH"):
            effective_path = f"{path_prefix}{os.pathsep}{effective_path}" if effective_path else path_prefix

        missing_tools = [
            name
            for name, spec in self.spec.tools.items()
            if not spec.optional and not shutil.which(spec.command, path=effective_path)
        ]

        # Generate shell script if requested
        activation_script = None
        if shell:
            shell_kind = shell if isinstance(shell, ShellKind) else ShellDetector().detect(shell_override=shell).kind
            activation_script = ActivationScriptBuilder().build(builder.build(), shell_kind)

        # Cache for next time
        if use_cache and self.spec.conda:
            get_cache().set(
                self.project_root,
                self.spec.conda.name,
                conda_prefix,
                env_vars,
                missing_tools,
            )

        return ActivationResult(
            env_vars=env_vars,
            missing_tools=missing_tools,
            activation_script=activation_script,
        )

    @classmethod
    def from_cwd(cls) -> EnvironmentActivator:
        """Create activator by finding .sniff-cli.toml from current directory."""
        spec_file = find_envspec()
        if not spec_file:
            raise NotFoundError(
                "No .sniff-cli.toml found",
                hint="Run 'sniff init' to create one, or navigate to a project directory",
            )

        spec = EnvironmentSpec.from_file(spec_file)
        project_root = spec_file.parent

        return cls(spec, project_root)
