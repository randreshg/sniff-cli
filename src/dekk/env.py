"""Environment variable snapshot and builder -- capture, compose, and produce env dicts.

EnvSnapshot is a frozen, immutable capture of environment variables at a point
in time.  EnvVarBuilder provides a composable builder pattern for constructing
environment variable sets from multiple sources (explicit values, defaults,
PATH-style concatenation, merges from other builders/snapshots).

Pure data + logic -- no mutations to ``os.environ``, no subprocesses.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# EnvSnapshot -- frozen capture
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvSnapshot:
    """Immutable snapshot of environment variables.

    Typically created via ``EnvSnapshot.capture()`` (grabs the live
    ``os.environ``) or ``EnvVarBuilder.build()``.
    """

    vars: tuple[tuple[str, str], ...] = ()

    # -- construction helpers --

    @classmethod
    def capture(cls) -> EnvSnapshot:
        """Capture the current ``os.environ`` as a frozen snapshot."""
        return cls(vars=tuple(sorted(os.environ.items())))

    @classmethod
    def from_dict(cls, d: Mapping[str, str]) -> EnvSnapshot:
        """Create a snapshot from an arbitrary mapping."""
        return cls(vars=tuple(sorted(d.items())))

    # -- query helpers --

    def get(self, name: str, default: str | None = None) -> str | None:
        """Get a variable by name."""
        for k, v in self.vars:
            if k == name:
                return v
        return default

    def to_dict(self) -> dict[str, str]:
        """Convert to a plain ``dict``."""
        return dict(self.vars)

    def __contains__(self, name: str) -> bool:
        return any(k == name for k, _ in self.vars)

    def __len__(self) -> int:
        return len(self.vars)

    def names(self) -> tuple[str, ...]:
        """Return sorted variable names."""
        return tuple(k for k, _ in self.vars)


# ---------------------------------------------------------------------------
# EnvVarBuilder -- composable builder
# ---------------------------------------------------------------------------


class EnvVarBuilder:
    """Composable builder for constructing environment variable sets.

    All mutating methods return ``self`` so calls can be chained::

        env = (
            EnvVarBuilder()
            .set("CC", "gcc")
            .set_default("JOBS", "4")
            .set_from_path("LD_LIBRARY_PATH", ["/opt/lib", "/usr/lib"])
            .build()
        )
    """

    def __init__(self) -> None:
        self._vars: dict[str, str] = {}
        self._unset: set[str] = set()

    # -- setters --

    def set(self, name: str, value: str) -> EnvVarBuilder:
        """Set a variable, overwriting any previous value."""
        self._unset.discard(name)
        self._vars[name] = value
        return self

    def set_default(self, name: str, value: str) -> EnvVarBuilder:
        """Set a variable only if it has not already been set in this builder."""
        if name not in self._vars and name not in self._unset:
            self._vars[name] = value
        return self

    def set_from_path(
        self,
        name: str,
        paths: list[str] | list[Path],
        sep: str = os.pathsep,
    ) -> EnvVarBuilder:
        """Set a variable by joining *paths* with *sep* (default ``os.pathsep``).

        Useful for PATH, LD_LIBRARY_PATH, etc.
        """
        self._unset.discard(name)
        self._vars[name] = sep.join(str(p) for p in paths)
        return self

    def unset(self, name: str) -> EnvVarBuilder:
        """Mark a variable for removal.

        The variable will not appear in the built snapshot, even if a
        subsequent ``merge`` or ``set_default`` tries to add it.
        """
        self._vars.pop(name, None)
        self._unset.add(name)
        return self

    # -- composition --

    def merge(self, other: EnvVarBuilder | EnvSnapshot | Mapping[str, str]) -> EnvVarBuilder:
        """Merge variables from *other* into this builder.

        Existing values in *this* builder take precedence -- ``merge`` only
        fills in variables not already set (and not explicitly unset).
        """
        if isinstance(other, EnvVarBuilder):
            source = other._vars
        elif isinstance(other, EnvSnapshot):
            source = other.to_dict()
        else:
            source = dict(other)

        for k, v in source.items():
            if k not in self._vars and k not in self._unset:
                self._vars[k] = v
        return self

    # -- terminal operations --

    def build(self) -> EnvSnapshot:
        """Produce a frozen ``EnvSnapshot`` from the current builder state."""
        return EnvSnapshot.from_dict(self._vars)

    def to_dict(self) -> dict[str, str]:
        """Return the current builder state as a plain ``dict``."""
        return dict(self._vars)
