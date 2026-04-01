"""Runtime environment provider abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from dekk.environment.types import EnvironmentKind

if TYPE_CHECKING:
    from dekk.environment.spec import ToolSpec
    from dekk.execution.os import DekkOS
    from dekk.execution.toolchain import EnvVarBuilder

ProgressCallback = Callable[[str], None]


@dataclass
class DekkEnvSetupResult:
    """Provider-specific environment setup summary."""

    created: bool = False
    prefix: Path | None = None
    packages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DekkEnv(ABC):
    """Runtime environment contract consumed by activation/setup/install flows."""

    def __init__(
        self,
        *,
        kind: EnvironmentKind,
        prefix: Path,
        file: str | None = None,
        name: str | None = None,
    ) -> None:
        self.kind = kind
        self.prefix = prefix
        self.file = file
        self.name = name

    @property
    def type_name(self) -> str:
        """Canonical provider name used in config and reporting."""
        return self.kind.value

    @abstractmethod
    def exists(self) -> bool:
        """Whether the resolved runtime environment is present on disk."""

    @abstractmethod
    def runtime_paths(self, os_strategy: DekkOS) -> tuple[Path, ...]:
        """Return provider runtime search paths for the current OS strategy."""

    @abstractmethod
    def configure(
        self,
        builder: EnvVarBuilder,
        *,
        project_name: str,
        tools: Mapping[str, ToolSpec],
    ) -> None:
        """Apply provider-specific environment variables to a builder."""

    @abstractmethod
    def setup(
        self,
        *,
        project_root: Path,
        force: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> DekkEnvSetupResult:
        """Create or update the runtime environment.

        Args:
            on_progress: Optional callback receiving sub-status messages
                (e.g. ``"Solving environment..."``). Used by the install
                runner to update the spinner text in real time.
        """

    def install_npm_packages(self, packages: Mapping[str, str]) -> tuple[list[str], list[str]]:
        """Install npm packages into the runtime environment if supported."""
        return [], [f"npm installation is not supported for {self.type_name} environments"]


__all__ = ["DekkEnv", "DekkEnvSetupResult"]
