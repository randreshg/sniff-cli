"""Git worktree management with dekk project awareness.

Provides discovery, creation, and cleanup of git worktrees that are
automatically integrated with the project's dekk environment.

Pure operations -- all git interaction goes through subprocess so failures
are explicit and recoverable.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

WORKTREE_DEFAULT_DIR: Final = "../{name}-worktrees"
GIT_DIR: Final = ".git"


@dataclass(frozen=True)
class WorktreeInfo:
    """A discovered git worktree."""

    path: Path
    branch: str
    commit: str
    is_bare: bool = False
    is_detached: bool = False
    is_main: bool = False
    has_dekk_toml: bool = False
    prunable: bool = False

    @property
    def name(self) -> str:
        """Short name derived from the worktree path."""
        return self.path.name


@dataclass(frozen=True)
class WorktreeCreateResult:
    """Result of creating a git worktree."""

    path: Path
    branch: str
    created: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.created and self.error is None


def find_git_root(start: Path | None = None) -> Path | None:
    """Find the git repository root from a starting directory."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / GIT_DIR).exists():
            return parent
    return None


def list_worktrees(git_root: Path | None = None) -> list[WorktreeInfo]:
    """List all git worktrees for the repository.

    Returns:
        List of WorktreeInfo, main worktree first. Empty list if not a git repo.
    """
    root = git_root or find_git_root()
    if root is None:
        return []

    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=root,
            check=False,
        )
    except FileNotFoundError:
        return []

    if result.returncode != 0:
        return []

    return _parse_porcelain(result.stdout, root)


def _parse_porcelain(output: str, git_root: Path) -> list[WorktreeInfo]:
    """Parse ``git worktree list --porcelain`` output."""
    worktrees: list[WorktreeInfo] = []
    current: dict[str, str] = {}

    for line in output.splitlines():
        if not line.strip():
            if current:
                worktrees.append(_build_worktree_info(current, git_root, len(worktrees) == 0))
                current = {}
            continue

        if line.startswith("worktree "):
            current["path"] = line[len("worktree "):]
        elif line.startswith("HEAD "):
            current["commit"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):]
        elif line == "bare":
            current["bare"] = "true"
        elif line == "detached":
            current["detached"] = "true"
        elif line == "prunable":
            current["prunable"] = "true"

    if current:
        worktrees.append(_build_worktree_info(current, git_root, len(worktrees) == 0))

    return worktrees


def _build_worktree_info(data: dict[str, str], git_root: Path, is_first: bool) -> WorktreeInfo:
    """Build a WorktreeInfo from parsed porcelain data."""
    wt_path = Path(data.get("path", str(git_root)))
    branch_ref = data.get("branch", "")
    # Strip refs/heads/ prefix for display
    branch = branch_ref.removeprefix("refs/heads/") if branch_ref else ""

    return WorktreeInfo(
        path=wt_path,
        branch=branch,
        commit=data.get("commit", ""),
        is_bare="bare" in data,
        is_detached="detached" in data,
        is_main=is_first,
        has_dekk_toml=(wt_path / ".dekk.toml").exists(),
        prunable="prunable" in data,
    )


def create_worktree(
    branch: str,
    path: Path | None = None,
    git_root: Path | None = None,
    new_branch: bool = True,
    base: str = "HEAD",
) -> WorktreeCreateResult:
    """Create a new git worktree.

    Args:
        branch: Branch name for the worktree.
        path: Directory for the worktree. Defaults to ``../<repo>-worktrees/<branch>``.
        git_root: Git repository root. Auto-detected if None.
        new_branch: Create a new branch (``-b``). If False, the branch must exist.
        base: Base commit/branch for the new branch.

    Returns:
        WorktreeCreateResult with the created path and status.
    """
    root = git_root or find_git_root()
    if root is None:
        return WorktreeCreateResult(
            path=path or Path("."),
            branch=branch,
            created=False,
            error="Not a git repository",
        )

    if path is None:
        worktrees_dir = root.parent / f"{root.name}-worktrees"
        # Sanitize branch name for directory use
        safe_branch = branch.replace("/", "-")
        path = worktrees_dir / safe_branch

    cmd = ["git", "worktree", "add"]
    if new_branch:
        cmd.extend(["-b", branch, str(path), base])
    else:
        cmd.extend([str(path), branch])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=root,
            check=False,
        )
    except FileNotFoundError:
        return WorktreeCreateResult(
            path=path,
            branch=branch,
            created=False,
            error="git not found",
        )

    if result.returncode != 0:
        error = result.stderr.strip() or f"git worktree add failed (exit {result.returncode})"
        return WorktreeCreateResult(
            path=path,
            branch=branch,
            created=False,
            error=error,
        )

    return WorktreeCreateResult(
        path=path.resolve(),
        branch=branch,
        created=True,
    )


def remove_worktree(
    path_or_name: str,
    git_root: Path | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    """Remove a git worktree.

    Args:
        path_or_name: Path to the worktree or its directory name.
        git_root: Git repository root. Auto-detected if None.
        force: Force removal even if worktree has modifications.

    Returns:
        Tuple of (success, message).
    """
    root = git_root or find_git_root()
    if root is None:
        return False, "Not a git repository"

    # Resolve path_or_name: could be an absolute path, relative path, or just a name
    target = Path(path_or_name)
    if not target.is_absolute():
        # Try as a worktree name — search existing worktrees
        existing = list_worktrees(root)
        for wt in existing:
            if wt.name == path_or_name or str(wt.path) == path_or_name:
                target = wt.path
                break
        else:
            # Try as a relative path from cwd
            target = Path.cwd() / path_or_name

    cmd = ["git", "worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(str(target))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=root,
            check=False,
        )
    except FileNotFoundError:
        return False, "git not found"

    if result.returncode != 0:
        return False, (
            result.stderr.strip()
            or f"git worktree remove failed (exit {result.returncode})"
        )

    return True, f"Removed worktree: {target}"


def prune_worktrees(git_root: Path | None = None) -> tuple[bool, str]:
    """Prune stale worktree references.

    Returns:
        Tuple of (success, message).
    """
    root = git_root or find_git_root()
    if root is None:
        return False, "Not a git repository"

    try:
        result = subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
            cwd=root,
            check=False,
        )
    except FileNotFoundError:
        return False, "git not found"

    if result.returncode != 0:
        return False, result.stderr.strip()

    return True, "Pruned stale worktree references"


__all__ = [
    "WorktreeCreateResult",
    "WorktreeInfo",
    "create_worktree",
    "find_git_root",
    "list_worktrees",
    "prune_worktrees",
    "remove_worktree",
]
