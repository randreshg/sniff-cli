"""Worktree management tool for dekk.

Provides git worktree operations with automatic dekk environment setup.
"""

from dekk.tools.worktree.commands import create_worktree_app
from dekk.tools.worktree.core import (
    WorktreeCreateResult,
    WorktreeInfo,
    create_worktree,
    find_git_root,
    list_worktrees,
    prune_worktrees,
    remove_worktree,
)

__all__ = [
    "WorktreeCreateResult",
    "WorktreeInfo",
    "create_worktree",
    "create_worktree_app",
    "find_git_root",
    "list_worktrees",
    "prune_worktrees",
    "remove_worktree",
]
