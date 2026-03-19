"""Toolchain profiles -- high-level abstractions for environment setup.

A toolchain profile knows which environment variables, PATH entries, and
library paths are needed for a particular toolchain (CMake/MLIR, conda, etc.).

The central abstraction is the `ToolchainProfile` protocol: any frozen
dataclass that implements `configure(builder)` can be used as a toolchain.
The `EnvVarBuilder` collects the declarations and produces an
`ActivationConfig` suitable for the existing `ActivationScriptBuilder`.

Usage (APXM replacing setup_mlir_environment):

    from sniff_cli.toolchain import CMakeToolchain, CondaToolchain, EnvVarBuilder
    from sniff_cli.shell import ActivationScriptBuilder, ShellKind

    conda = CondaToolchain(prefix=Path("/opt/conda/envs/apxm"))
    cmake = CMakeToolchain(prefix=Path("/opt/conda/envs/apxm"))

    builder = EnvVarBuilder(app_name="apxm")
    conda.configure(builder)
    cmake.configure(builder)

    config = builder.build()
    script = ActivationScriptBuilder().build(config, ShellKind.BASH)
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from sniff_cli.shell import ActivationConfig, EnvVar
from sniff_cli.sniff_os import get_sniff_os


@runtime_checkable
class ToolchainProfile(Protocol):
    """Protocol for toolchain environment configuration.

    Implementors declare what environment variables and paths they need
    by calling methods on the provided `EnvVarBuilder`.
    """

    def configure(self, builder: EnvVarBuilder) -> None:
        """Populate *builder* with the env vars and paths this toolchain needs."""
        ...


class EnvVarBuilder:
    """Accumulates environment variable declarations from toolchain profiles.

    This is a mutable builder. Call `configure` on one or more
    `ToolchainProfile` instances, then call `build()` to get a frozen
    `ActivationConfig`.
    """

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
        """Prepend *value* to the existing value of *name* using ``os.pathsep`` semantics."""
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
        """Produce a frozen `ActivationConfig` from accumulated declarations."""
        return ActivationConfig(
            env_vars=tuple(self._env_vars),
            path_prepends=tuple(self._path_prepends),
            app_name=self._app_name,
            banner=self._banner,
        )

    def to_env_dict(self) -> dict[str, str]:
        """Produce a plain dict of env var name -> value (for subprocess.Popen).

        Prepend-style variables are joined with ``os.pathsep``. PATH prepends are
        merged into the ``"PATH"`` key. Callers should merge the result
        with ``os.environ`` themselves (prepending path-like values).
        """
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
        """Names of environment variables that should be prepended, not replaced."""
        keys = {var.name for var in self._env_vars if var.prepend_path}
        if self._path_prepends:
            keys.add("PATH")
        return frozenset(keys)


# ---------------------------------------------------------------------------
# Concrete toolchain profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CMakeToolchain:
    """CMake / MLIR / LLVM toolchain rooted at a conda (or system) prefix.

    Given a *prefix* such as ``/home/user/miniforge3/envs/apxm``, sets:

    - ``MLIR_DIR``  -> ``<prefix>/lib/cmake/mlir``
    - ``LLVM_DIR``  -> ``<prefix>/lib/cmake/llvm``
    - ``MLIR_PREFIX`` -> ``<prefix>``
    - ``LLVM_PREFIX`` -> ``<prefix>``
    - On Unix, ``LD_LIBRARY_PATH`` or ``DYLD_LIBRARY_PATH`` prepended with
      the runtime library directory
    - On Windows, the relevant runtime directories prepended to ``PATH``
    """

    prefix: Path
    extra_lib_dirs: tuple[str, ...] = ()

    @property
    def mlir_dir(self) -> Path:
        return get_sniff_os().cmake_package_dir(self.prefix, "mlir")

    @property
    def llvm_dir(self) -> Path:
        return get_sniff_os().cmake_package_dir(self.prefix, "llvm")

    @property
    def lib_dir(self) -> Path:
        base = self.prefix / "Library" if platform.system() == "Windows" else self.prefix
        return base / "lib"

    @property
    def runtime_lib_dir(self) -> Path:
        return get_sniff_os().cmake_runtime_dir(self.prefix)

    @property
    def bin_dirs(self) -> tuple[Path, ...]:
        return get_sniff_os().conda_runtime_paths(self.prefix)

    @property
    def bin_dir(self) -> Path:
        return self.bin_dirs[0]

    def configure(self, builder: EnvVarBuilder) -> None:
        builder.set_var("MLIR_DIR", str(self.mlir_dir))
        builder.set_var("LLVM_DIR", str(self.llvm_dir))
        builder.set_var("MLIR_PREFIX", str(self.prefix))
        builder.set_var("LLVM_PREFIX", str(self.prefix))

        system = platform.system()
        if system == "Windows":
            for d in (*self.extra_lib_dirs, str(self.runtime_lib_dir)):
                builder.prepend_path(d)
        else:
            lib_var = "DYLD_LIBRARY_PATH" if system == "Darwin" else "LD_LIBRARY_PATH"
            for d in self.extra_lib_dirs:
                builder.prepend_var(lib_var, d)
            builder.prepend_var(lib_var, str(self.lib_dir))

        for bin_dir in self.bin_dirs:
            builder.prepend_path(bin_dir)


@dataclass(frozen=True)
class CondaToolchain:
    """Conda environment toolchain.

    Sets ``CONDA_PREFIX`` and prepends the platform-appropriate runtime
    directories to ``PATH``.
    """

    prefix: Path
    env_name: str = ""

    @property
    def path_dirs(self) -> tuple[Path, ...]:
        return get_sniff_os().conda_runtime_paths(self.prefix)

    def configure(self, builder: EnvVarBuilder) -> None:
        builder.set_var("CONDA_PREFIX", str(self.prefix))
        if self.env_name:
            builder.set_var("CONDA_DEFAULT_ENV", self.env_name)
        for path in self.path_dirs:
            builder.prepend_path(path)
