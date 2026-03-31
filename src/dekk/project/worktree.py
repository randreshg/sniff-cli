"""Backward-compat re-exports from ``dekk.tools.worktree``."""

from dekk.tools.worktree.core import (
    WorktreeCreateResult,
    WorktreeInfo,
    _parse_porcelain,  # noqa: F401 (re-exported for tests)
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
    "find_git_root",
    "list_worktrees",
    "prune_worktrees",
    "remove_worktree",
]
