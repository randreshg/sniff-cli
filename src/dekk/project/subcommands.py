"""Backward-compat re-exports from ``dekk.tools``.

All constants and the ``create_app`` factory now live in
``dekk.tools``.  This module re-exports them so existing imports
from ``dekk.project.subcommands`` continue to work.
"""

from dekk.tools import AGENTS, CLI_NAME, NAMES, WORKTREE, create_tool_app as create_app

__all__ = ["AGENTS", "CLI_NAME", "NAMES", "WORKTREE", "create_app"]
