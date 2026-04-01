"""Built-in tools for dekk project sub-commands.

Each tool lives in its own package under ``dekk.tools``:

- ``dekk.tools.worktree`` — git worktree management
- ``dekk.agents``         — agent config generation (standalone package)

Downstream CLIs (e.g., apxm) can register additional tools by adding
entries to :data:`REGISTRY` before CLI construction.

Usage from the project runner::

    from dekk.tools import REGISTRY, create_tool_app

    if command_name in REGISTRY:
        app = create_tool_app(command_name, project_root)
        app()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

# ---------------------------------------------------------------------------
# CLI entry point name
# ---------------------------------------------------------------------------

CLI_NAME: Final = "dekk"

# ---------------------------------------------------------------------------
# Tool name constants
# ---------------------------------------------------------------------------

AGENTS: Final = "agents"
INSTALL: Final = "install"
SETUP: Final = "setup"
UNINSTALL: Final = "uninstall"
WORKTREE: Final = "worktree"
PROJECT_BUILTIN_DESCRIPTIONS: Final[dict[str, str]] = {
    AGENTS: "Manage agent configs for this project",
    INSTALL: "Set up environment, build, and optionally install CLI wrapper",
    SETUP: "Create or refresh the configured runtime environment",
    UNINSTALL: "Remove the runtime environment, wrappers, and dekk state",
    WORKTREE: "Manage git worktrees with dekk environment awareness",
}

# ---------------------------------------------------------------------------
# Registry: tool name → factory info
#
# Each entry maps a tool name to the module path and factory function
# that creates its Typer sub-app.  The factory receives (project_root,)
# as keyword arguments where applicable.
# ---------------------------------------------------------------------------

REGISTRY: Final[dict[str, dict[str, str]]] = {
    AGENTS: {
        "module": "dekk.agents.app",
        "factory": "create_agents_app",
    },
    WORKTREE: {
        "module": "dekk.tools.worktree.commands",
        "factory": "create_worktree_app",
    },
}

# Convenience frozenset for membership checks in the project runner.
NAMES: Final[frozenset[str]] = frozenset(REGISTRY.keys())


def create_tool_app(name: str, project_root: Path) -> Any:
    """Create the Typer app for a registered tool.

    Args:
        name: Tool name (must be in :data:`REGISTRY`).
        project_root: Resolved project root from ``.dekk.toml``.

    Returns:
        A ``typer.Typer`` sub-app ready to invoke.

    Raises:
        ValueError: If *name* is not registered.
    """
    import importlib

    entry = REGISTRY.get(name)
    if entry is None:
        raise ValueError(
            f"Unknown tool: {name!r}. Available: {', '.join(sorted(REGISTRY))}"
        )

    mod = importlib.import_module(entry["module"])
    factory = getattr(mod, entry["factory"])

    if name == AGENTS:
        from dekk.agents.constants import DEFAULT_SOURCE_DIR

        return factory(
            source_dir=DEFAULT_SOURCE_DIR,
            get_project_root=lambda: project_root,
        )

    # Default: call factory with no arguments (e.g., worktree)
    return factory()


__all__ = [
    "AGENTS",
    "CLI_NAME",
    "INSTALL",
    "NAMES",
    "PROJECT_BUILTIN_DESCRIPTIONS",
    "REGISTRY",
    "SETUP",
    "UNINSTALL",
    "WORKTREE",
    "create_tool_app",
]
