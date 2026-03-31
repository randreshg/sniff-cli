"""Environment specification, resolution, activation, and setup."""

from .activation import ActivationResult, EnvironmentActivator
from .providers import CondaEnv, DekkEnv, DekkEnvSetupResult
from .resolver import resolve_environment
from .setup import SetupResult, run_setup
from .spec import (
    AgentsSpec,
    CommandSpec,
    EnvironmentSpec,
    NpmSpec,
    PythonSpec,
    RuntimeEnvironmentSpec,
    ToolSpec,
    find_envspec,
)
from .types import EnvironmentKind, normalize_environment_type

__all__ = [
    "ActivationResult",
    "AgentsSpec",
    "CommandSpec",
    "CondaEnv",
    "DekkEnv",
    "DekkEnvSetupResult",
    "EnvironmentActivator",
    "EnvironmentKind",
    "EnvironmentSpec",
    "NpmSpec",
    "PythonSpec",
    "RuntimeEnvironmentSpec",
    "SetupResult",
    "ToolSpec",
    "find_envspec",
    "normalize_environment_type",
    "resolve_environment",
    "run_setup",
]
