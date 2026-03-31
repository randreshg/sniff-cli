"""Conda-specific toolchain profile."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dekk.execution.os import get_dekk_os
from dekk.execution.toolchain.builder import EnvVarBuilder

CONDA_PREFIX_ENV = "CONDA_PREFIX"
CONDA_DEFAULT_ENV = "CONDA_DEFAULT_ENV"


@dataclass(frozen=True)
class CondaToolchain:
    """Conda environment toolchain."""

    prefix: Path
    env_name: str = ""

    @property
    def path_dirs(self) -> tuple[Path, ...]:
        return get_dekk_os().conda_runtime_paths(self.prefix)

    def configure(self, builder: EnvVarBuilder) -> None:
        builder.set_var(CONDA_PREFIX_ENV, str(self.prefix))
        if self.env_name:
            builder.set_var(CONDA_DEFAULT_ENV, self.env_name)
        for path in self.path_dirs:
            builder.prepend_path(path)


__all__ = ["CondaToolchain"]
