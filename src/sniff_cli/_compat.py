"""Shared compatibility utilities for sniff-cli internals."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# -- TOML compatibility -------------------------------------------------------
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore[assignment]


def load_toml(path: Path) -> dict[str, Any] | None:
    """Load a TOML file, returning None on failure or if tomllib unavailable."""
    if tomllib is None:
        return None
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        return None


def load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None on failure."""
    import json
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (returns new dict)."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def walk_up(start: Path, marker: str) -> Path | None:
    """Walk up from start looking for a file/directory named marker. Returns the marker path or None."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        candidate = parent / marker
        if candidate.exists():
            return candidate
    return None
