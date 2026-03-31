"""Shared toolchain contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ToolchainProfile(Protocol):
    """Protocol for toolchain environment configuration."""

    def configure(self, builder: "EnvVarBuilder") -> None:
        """Populate *builder* with the env vars and paths this toolchain needs."""
        ...


__all__ = ["ToolchainProfile"]
