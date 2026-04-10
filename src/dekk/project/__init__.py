"""Project-scoped command routing and execution."""

from dekk.tools.worktree.core import (
    WorktreeCreateResult,
    WorktreeInfo,
    create_worktree,
    find_git_root,
    list_worktrees,
    prune_worktrees,
    remove_worktree,
)

from .runner import run_project_command
from .subcommands import CLI_NAME, NAMES, SKILLS, WORKTREE, create_app

__all__ = [
    "CLI_NAME",
    "NAMES",
    "SKILLS",
    "WORKTREE",
    "WorktreeCreateResult",
    "WorktreeInfo",
    "create_app",
    "create_worktree",
    "find_git_root",
    "list_worktrees",
    "prune_worktrees",
    "remove_worktree",
    "run_project_command",
]
