"""Toolchain profiles -- high-level abstractions for environment setup.

A toolchain profile knows which environment variables, PATH entries, and
library paths are needed for a particular toolchain (CMake/MLIR, conda, etc.).

The central abstraction is the `ToolchainProfile` protocol: any frozen
dataclass that implements `configure(builder)` can be used as a toolchain.
The `EnvVarBuilder` collects the declarations and produces an
`ActivationConfig` suitable for the existing `ActivationScriptBuilder`.

Usage (APXM replacing setup_mlir_environment):

    from sniff.toolchain import CMakeToolchain, CondaToolchain, EnvVarBuilder
    from sniff.shell import ActivationScriptBuilder, ShellKind

    conda = CondaToolchain(prefix=Path("/opt/conda/envs/apxm"))
    cmake = CMakeToolchain(prefix=Path("/opt/conda/envs/apxm"))

    builder = EnvVarBuilder(app_name="apxm")
    conda.configure(builder)
    cmake.configure(builder)

    config = builder.build()
    script = ActivationScriptBuilder().build(config, ShellKind.BASH)
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from sniff.shell import ActivationConfig, EnvVar


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
        self._env_vars.append(EnvVar(name=name, value=value))

    def prepend_var(self, name: str, value: str) -> None:
        """Prepend *value* to the existing value of *name* (colon-separated)."""
        self._env_vars.append(EnvVar(name=name, value=value, prepend_path=True))

    def prepend_path(self, directory: str | Path) -> None:
        """Prepend a directory to PATH."""
        self._path_prepends.append(str(directory))

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

        For prepend-style variables the value is just the new prefix; callers
        should merge with ``os.environ`` themselves. PATH prepends are added
        under the key ``"PATH"``.
        """
        result: dict[str, str] = {}
        for var in self._env_vars:
            result[var.name] = var.value
        if self._path_prepends:
            result["PATH"] = ":".join(self._path_prepends)
        return result


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
    - ``LD_LIBRARY_PATH`` (Linux) or ``DYLD_LIBRARY_PATH`` (macOS) prepended
      with ``<prefix>/lib``
    - ``<prefix>/bin`` prepended to ``PATH``
    """

    prefix: Path
    extra_lib_dirs: tuple[str, ...] = ()

    @property
    def mlir_dir(self) -> Path:
        return self.prefix / "lib" / "cmake" / "mlir"

    @property
    def llvm_dir(self) -> Path:
        return self.prefix / "lib" / "cmake" / "llvm"

    @property
    def lib_dir(self) -> Path:
        return self.prefix / "lib"

    @property
    def bin_dir(self) -> Path:
        return self.prefix / "bin"

    def configure(self, builder: EnvVarBuilder) -> None:
        builder.set_var("MLIR_DIR", str(self.mlir_dir))
        builder.set_var("LLVM_DIR", str(self.llvm_dir))
        builder.set_var("MLIR_PREFIX", str(self.prefix))
        builder.set_var("LLVM_PREFIX", str(self.prefix))

        # Library path (platform-aware)
        lib_var = "DYLD_LIBRARY_PATH" if platform.system() == "Darwin" else "LD_LIBRARY_PATH"
        for d in self.extra_lib_dirs:
            builder.prepend_var(lib_var, d)
        builder.prepend_var(lib_var, str(self.lib_dir))

        builder.prepend_path(self.bin_dir)


@dataclass(frozen=True)
class CondaToolchain:
    """Conda environment toolchain.

    Sets ``CONDA_PREFIX`` and prepends ``<prefix>/bin`` to ``PATH``.
    """

    prefix: Path
    env_name: str = ""

    def configure(self, builder: EnvVarBuilder) -> None:
        builder.set_var("CONDA_PREFIX", str(self.prefix))
        if self.env_name:
            builder.set_var("CONDA_DEFAULT_ENV", self.env_name)
        builder.prepend_path(self.prefix / "bin")
