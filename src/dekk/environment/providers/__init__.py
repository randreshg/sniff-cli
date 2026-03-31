"""Runtime environment providers."""

from __future__ import annotations

from collections.abc import Callable

from dekk.environment.providers.base import DekkEnv, DekkEnvSetupResult
from dekk.environment.providers.conda import CondaEnv, create_conda_env
from dekk.environment.types import EnvironmentKind

EnvironmentFactory = Callable[..., DekkEnv]

_PROVIDER_FACTORIES: dict[EnvironmentKind, EnvironmentFactory] = {
    EnvironmentKind.CONDA: create_conda_env,
}


def get_environment_factory(kind: EnvironmentKind) -> EnvironmentFactory | None:
    """Return the provider factory registered for *kind*."""
    return _PROVIDER_FACTORIES.get(kind)

__all__ = [
    "CondaEnv",
    "DekkEnv",
    "DekkEnvSetupResult",
    "EnvironmentFactory",
    "create_conda_env",
    "get_environment_factory",
]
