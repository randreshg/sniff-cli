"""CMake/LLVM/MLIR toolchain profile."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dekk.execution.os import get_dekk_os
from dekk.execution.toolchain.builder import EnvVarBuilder

CMAKE_PREFIX_PATH_ENV = "CMAKE_PREFIX_PATH"


@dataclass(frozen=True)
class CMakeToolchain:
    """CMake / MLIR / LLVM toolchain rooted at a runtime prefix."""

    prefix: Path
    extra_lib_dirs: tuple[str, ...] = ()

    @property
    def mlir_dir(self) -> Path:
        return get_dekk_os().cmake_package_dir(self.prefix, "mlir")

    @property
    def llvm_dir(self) -> Path:
        return get_dekk_os().cmake_package_dir(self.prefix, "llvm")

    @property
    def lib_dir(self) -> Path:
        return get_dekk_os().cmake_library_dir(self.prefix)

    @property
    def runtime_lib_dir(self) -> Path:
        return get_dekk_os().cmake_runtime_dir(self.prefix)

    @property
    def bin_dirs(self) -> tuple[Path, ...]:
        return get_dekk_os().conda_runtime_paths(self.prefix)

    @property
    def bin_dir(self) -> Path:
        return self.bin_dirs[0]

    def configure(self, builder: EnvVarBuilder) -> None:
        builder.prepend_var(CMAKE_PREFIX_PATH_ENV, str(self.prefix))

        library_path_var = get_dekk_os().shared_library_path_var()
        if library_path_var is None:
            for directory in (*self.extra_lib_dirs, str(self.runtime_lib_dir)):
                builder.prepend_path(directory)
        else:
            for directory in self.extra_lib_dirs:
                builder.prepend_var(library_path_var, directory)
            builder.prepend_var(library_path_var, str(self.lib_dir))

        for bin_dir in self.bin_dirs:
            builder.prepend_path(bin_dir)


__all__ = ["CMakeToolchain"]
