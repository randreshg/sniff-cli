"""dekk CLI framework - styling, output, errors, progress, and configuration.

All symbols are lazily loaded to avoid pulling in Rich/Typer at import time.
"""

from __future__ import annotations

from typing import Any

_MODULE_ATTRS: dict[str, list[str]] = {
    "dekk.cli.styles": [
        "console",
        "err_console",
        "CLI_THEME",
        "Colors",
        "Symbols",
        "print_success",
        "print_error",
        "print_warning",
        "print_info",
        "print_debug",
        "print_header",
        "print_step",
        "print_section",
        "print_blank",
        "print_table",
        "print_numbered_list",
        "print_next_steps",
    ],
    "dekk.cli.typer_app": ["Typer", "Option", "Argument", "Exit", "Context"],
    "dekk.cli.cli_commands": ["run_doctor", "run_version", "run_env"],
}

_ATTR_TO_MODULE: dict[str, str] = {
    name: mod for mod, names in _MODULE_ATTRS.items() for name in names
}


def __getattr__(name: str) -> Any:  # noqa: N807
    if name in _ATTR_TO_MODULE:
        import importlib

        mod_path = _ATTR_TO_MODULE[name]
        module = importlib.import_module(mod_path)
        for attr_name in _MODULE_ATTRS[mod_path]:
            try:
                globals()[attr_name] = getattr(module, attr_name)
            except AttributeError:
                pass
        return globals()[name]
    raise AttributeError(f"module 'dekk.cli' has no attribute {name!r}")


def __dir__() -> list[str]:  # noqa: N807
    return list(_ATTR_TO_MODULE.keys())


__all__ = list(_ATTR_TO_MODULE)
