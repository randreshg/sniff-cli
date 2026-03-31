"""Environment variable builder used by toolchain profiles."""

from __future__ import annotations

import os
from pathlib import Path

from dekk.shell import ActivationConfig, EnvVar


class EnvVarBuilder:
    """Accumulates environment variable declarations from toolchain profiles."""

    def __init__(self, app_name: str = "") -> None:
        self._app_name = app_name
        self._env_vars: list[EnvVar] = []
        self._path_prepends: list[str] = []
        self._banner: str | None = None

    def set_var(self, name: str, value: str) -> None:
        """Set an environment variable (unconditionally)."""
        env_var = EnvVar(name=name, value=value)
        if env_var not in self._env_vars:
            self._env_vars.append(env_var)

    def prepend_var(self, name: str, value: str) -> None:
        """Prepend *value* to *name* using ``os.pathsep`` semantics."""
        env_var = EnvVar(name=name, value=value, prepend_path=True)
        if env_var not in self._env_vars:
            self._env_vars.append(env_var)

    def prepend_path(self, directory: str | Path) -> None:
        """Prepend a directory to PATH."""
        path_str = str(directory)
        if path_str not in self._path_prepends:
            self._path_prepends.append(path_str)

    def set_banner(self, banner: str) -> None:
        """Set the activation banner message."""
        self._banner = banner

    def build(self) -> ActivationConfig:
        """Produce a frozen ``ActivationConfig`` from accumulated declarations."""
        return ActivationConfig(
            env_vars=tuple(self._env_vars),
            path_prepends=tuple(self._path_prepends),
            app_name=self._app_name,
            banner=self._banner,
        )

    def to_env_dict(self) -> dict[str, str]:
        """Produce a plain dict of env var name -> value (for subprocesses)."""
        result: dict[str, str] = {}
        prepends: dict[str, list[str]] = {}
        for var in self._env_vars:
            if var.prepend_path:
                prepends.setdefault(var.name, []).append(var.value)
            else:
                result[var.name] = var.value
        for name, values in prepends.items():
            result[name] = os.pathsep.join(values)
        if self._path_prepends:
            existing = result.get("PATH", "")
            path_val = os.pathsep.join(self._path_prepends)
            result["PATH"] = f"{path_val}{os.pathsep}{existing}" if existing else path_val
        return result

    @property
    def prepend_keys(self) -> frozenset[str]:
        """Names of environment variables that should be prepended."""
        keys = {var.name for var in self._env_vars if var.prepend_path}
        if self._path_prepends:
            keys.add("PATH")
        return frozenset(keys)


__all__ = ["EnvVarBuilder"]
