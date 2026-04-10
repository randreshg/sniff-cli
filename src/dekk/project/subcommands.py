"""Re-exports from ``dekk.tools``.

All constants and the ``create_app`` factory now live in
``dekk.tools``.  This module re-exports them so existing imports
from ``dekk.project.subcommands`` continue to work.
"""

from dekk.tools import (
    CLI_NAME,
    DOCTOR,
    INSTALL,
    NAMES,
    PROJECT_BUILTIN_DESCRIPTIONS,
    SETUP,
    SKILLS,
    UNINSTALL,
    WORKTREE,
)
from dekk.tools import (
    create_tool_app as create_app,
)

__all__ = [
    "CLI_NAME",
    "DOCTOR",
    "INSTALL",
    "NAMES",
    "PROJECT_BUILTIN_DESCRIPTIONS",
    "SETUP",
    "SKILLS",
    "UNINSTALL",
    "WORKTREE",
    "create_app",
]
