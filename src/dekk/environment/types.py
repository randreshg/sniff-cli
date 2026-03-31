"""Shared environment-type helpers."""

from __future__ import annotations

from enum import Enum


class EnvironmentKind(str, Enum):
    """Known runtime environment providers."""

    CONDA = "conda"

    @classmethod
    def from_value(cls, value: str) -> EnvironmentKind | None:
        """Return the known environment kind for *value*, if any."""
        normalized = normalize_environment_type(value)
        try:
            return cls(normalized)
        except ValueError:
            return None


def normalize_environment_type(value: str) -> str:
    """Canonicalize configured environment provider names."""
    return value.strip().lower()


__all__ = ["EnvironmentKind", "normalize_environment_type"]
