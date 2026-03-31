"""Shared helpers for OS-specific execution strategies."""

from __future__ import annotations

from datetime import UTC, datetime


def generated_timestamp() -> str:
    """Return a stable UTC timestamp for generated wrapper headers."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sh_quote(value: str) -> str:
    """Quote a string for POSIX shell single-quoted usage."""
    if not value:
        return "''"
    return "'" + value.replace("'", "'\\''") + "'"


def sh_escape_double(value: str) -> str:
    """Escape a string for inclusion inside POSIX double quotes."""
    result: list[str] = []
    for char in value:
        if char in ("$", "`", '"', "\\"):
            result.append("\\")
        result.append(char)
    return "".join(result)


def cmd_escape(value: str) -> str:
    """Escape a value for `set "NAME=value"` batch syntax."""
    return value.replace("^", "^^").replace("%", "%%").replace('"', '""')


__all__ = ["cmd_escape", "generated_timestamp", "sh_escape_double", "sh_quote"]
