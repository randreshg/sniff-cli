"""Resolve runtime environments from the `.dekk.toml` `[environment]` section."""

from __future__ import annotations

from pathlib import Path

from dekk.environment.providers import DekkEnv, get_environment_factory
from dekk.environment.spec import EnvironmentSpec


def _expand_path(template: str, *, project_root: Path) -> Path:
    value = template.replace("{project}", str(project_root)).replace("{home}", str(Path.home()))
    return Path(value).expanduser()


def resolve_environment(spec: EnvironmentSpec, *, project_root: Path) -> DekkEnv | None:
    """Resolve the configured runtime environment provider."""
    if spec.environment is None or spec.environment.kind is None:
        return None

    prefix = _expand_path(spec.environment.path, project_root=project_root)
    factory = get_environment_factory(spec.environment.kind)
    if factory is None:
        return None

    return factory(prefix=prefix, file=spec.environment.file, name=spec.environment.name)


__all__ = ["DekkEnv", "resolve_environment"]
