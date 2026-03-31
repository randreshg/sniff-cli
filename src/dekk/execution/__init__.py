"""Execution, wrapping, installation, and launch helpers."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "BinaryInstaller": "dekk.execution.install",
    "CMakeToolchain": "dekk.execution.toolchain",
    "CondaToolchain": "dekk.execution.toolchain",
    "DekkOS": "dekk.execution.os",
    "EnvSnapshot": "dekk.execution.env",
    "EnvVarBuilder": "dekk.execution.toolchain",
    "InstallResult": "dekk.execution.install",
    "PosixDekkOS": "dekk.execution.os",
    "TestPlan": "dekk.execution.test_runner",
    "ToolchainProfile": "dekk.execution.toolchain",
    "WindowsDekkOS": "dekk.execution.os",
    "WrapperGenerator": "dekk.execution.wrapper",
    "get_dekk_os": "dekk.execution.os",
    "resolve_test_plan": "dekk.execution.test_runner",
    "run_script": "dekk.execution.runner",
    "run_test_plan": "dekk.execution.test_runner",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module 'dekk.execution' has no attribute {name!r}")
    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value
