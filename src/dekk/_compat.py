"""Shared compatibility utilities for dekk internals."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# -- TOML compatibility -------------------------------------------------------
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

__all__ = ["deep_merge", "load_json", "load_toml", "tomllib", "walk_up"]


def load_toml(path: Path) -> dict[str, Any] | None:
    """Load a TOML file, returning None on failure or if tomllib unavailable."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        return None


def load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None on failure."""
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Recursively merge override into base (returns new dict)."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def walk_up(start: Path, marker: str) -> Path | None:
    """Walk up from *start* looking for a named marker file or directory."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        candidate = parent / marker
        if candidate.exists():
            return candidate
    return None
