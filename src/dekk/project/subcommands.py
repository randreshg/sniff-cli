"""Backward-compat re-exports from ``dekk.tools``.

All constants and the ``create_app`` factory now live in
``dekk.tools``.  This module re-exports them so existing imports
from ``dekk.project.subcommands`` continue to work.
"""

from dekk.tools import (
    AGENTS,
    CLI_NAME,
    NAMES,
    PROJECT_BUILTIN_DESCRIPTIONS,
    SETUP,
    WORKTREE,
)
from dekk.tools import (
    create_tool_app as create_app,
)

__all__ = [
    "AGENTS",
    "CLI_NAME",
    "NAMES",
    "PROJECT_BUILTIN_DESCRIPTIONS",
    "SETUP",
    "WORKTREE",
    "create_app",
]
