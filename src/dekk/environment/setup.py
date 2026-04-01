"""Project environment setup from the configured runtime provider."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dekk.environment.resolver import resolve_environment
from dekk.environment.spec import EnvironmentSpec
from dekk.environment.types import EnvironmentKind


@dataclass
class SetupResult:
    """Summary of what was set up."""

    environment_created: bool = False
    environment_prefix: Path | None = None
    environment_kind: EnvironmentKind | None = None
    environment_packages: list[str] = field(default_factory=list)
    npm_installed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def run_setup(
    project_root: Path,
    force: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> SetupResult:
    """Set up the complete project environment from .dekk.toml.

    Args:
        on_progress: Optional callback receiving sub-status messages
            (e.g. ``"Solving environment..."``).
    """
    spec_file = project_root / ".dekk.toml"
    spec = EnvironmentSpec.from_file(spec_file)
    result = SetupResult()

    resolved = resolve_environment(spec, project_root=project_root)
    if resolved:
        provider_result = resolved.setup(
            project_root=project_root, force=force, on_progress=on_progress,
        )
        result.environment_kind = resolved.kind
        result.environment_prefix = provider_result.prefix
        result.environment_created = provider_result.created
        result.environment_packages = provider_result.packages
        result.errors.extend(provider_result.errors)

        if provider_result.prefix and spec.npm and spec.npm.packages:
            installed, npm_errors = resolved.install_npm_packages(spec.npm.packages)
            result.npm_installed = installed
            result.errors.extend(npm_errors)
        elif spec.npm and spec.npm.packages and not provider_result.prefix:
            result.errors.append(
                "Cannot install npm packages: runtime environment not available"
            )
    elif spec.npm and spec.npm.packages:
        result.errors.append(
            "Cannot install npm packages: no runtime environment configured"
        )

    return result


__all__ = ["SetupResult", "run_setup"]
