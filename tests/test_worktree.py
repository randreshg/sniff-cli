"""Tests for git worktree management."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from dekk.tools.worktree.core import (
    WorktreeCreateResult,
    WorktreeInfo,
    _parse_porcelain,
    create_worktree,
    find_git_root,
    list_worktrees,
    prune_worktrees,
    remove_worktree,
)

# ---------------------------------------------------------------------------
# WorktreeInfo
# ---------------------------------------------------------------------------


class TestWorktreeInfo:
    def test_frozen(self) -> None:
        info = WorktreeInfo(path=Path("/tmp/wt"), branch="main", commit="abc123")
        with pytest.raises(AttributeError):
            info.branch = "other"  # type: ignore[misc]

    def test_name_from_path(self) -> None:
        info = WorktreeInfo(
            path=Path("/tmp/repo-worktrees/feature-x"),
            branch="feature-x",
            commit="abc",
        )
        assert info.name == "feature-x"

    def test_defaults(self) -> None:
        info = WorktreeInfo(path=Path("/tmp/wt"), branch="main", commit="abc")
        assert not info.is_bare
        assert not info.is_detached
        assert not info.is_main
        assert not info.has_dekk_toml
        assert not info.prunable


class TestWorktreeCreateResult:
    def test_ok_when_created(self) -> None:
        r = WorktreeCreateResult(path=Path("/tmp/wt"), branch="feat", created=True)
        assert r.ok

    def test_not_ok_when_error(self) -> None:
        r = WorktreeCreateResult(path=Path("/tmp/wt"), branch="feat", created=True, error="oops")
        assert not r.ok

    def test_not_ok_when_not_created(self) -> None:
        r = WorktreeCreateResult(path=Path("/tmp/wt"), branch="feat", created=False)
        assert not r.ok


# ---------------------------------------------------------------------------
# find_git_root
# ---------------------------------------------------------------------------


class TestFindGitRoot:
    def test_finds_root(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        assert find_git_root(tmp_path) == tmp_path

    def test_finds_root_from_subdirectory(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "src" / "pkg"
        subdir.mkdir(parents=True)
        assert find_git_root(subdir) == tmp_path

    def test_returns_none_when_no_git(self, tmp_path: Path) -> None:
        assert find_git_root(tmp_path) is None


# ---------------------------------------------------------------------------
# _parse_porcelain
# ---------------------------------------------------------------------------


class TestParsePorcelain:
    def test_single_worktree(self) -> None:
        output = (
            "worktree /home/user/repo\n"
            "HEAD abc123def456\n"
            "branch refs/heads/main\n"
            "\n"
        )
        result = _parse_porcelain(output, Path("/home/user/repo"))
        assert len(result) == 1
        assert result[0].path == Path("/home/user/repo")
        assert result[0].branch == "main"
        assert result[0].commit == "abc123def456"
        assert result[0].is_main  # first entry

    def test_multiple_worktrees(self) -> None:
        output = (
            "worktree /home/user/repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /home/user/repo-worktrees/feat\n"
            "HEAD def456\n"
            "branch refs/heads/feature/x\n"
            "\n"
        )
        result = _parse_porcelain(output, Path("/home/user/repo"))
        assert len(result) == 2
        assert result[0].is_main
        assert not result[1].is_main
        assert result[1].branch == "feature/x"

    def test_detached_head(self) -> None:
        output = (
            "worktree /tmp/wt\n"
            "HEAD abc123\n"
            "detached\n"
            "\n"
        )
        result = _parse_porcelain(output, Path("/tmp/repo"))
        assert result[0].is_detached
        assert result[0].branch == ""

    def test_bare_repo(self) -> None:
        output = (
            "worktree /tmp/bare.git\n"
            "HEAD abc123\n"
            "bare\n"
            "\n"
        )
        result = _parse_porcelain(output, Path("/tmp/bare.git"))
        assert result[0].is_bare

    def test_prunable(self) -> None:
        output = (
            "worktree /tmp/stale\n"
            "HEAD abc123\n"
            "branch refs/heads/old\n"
            "prunable\n"
            "\n"
        )
        result = _parse_porcelain(output, Path("/tmp/repo"))
        assert result[0].prunable

    def test_empty_output(self) -> None:
        assert _parse_porcelain("", Path("/tmp/repo")) == []

    def test_no_trailing_newline(self) -> None:
        output = (
            "worktree /tmp/wt\n"
            "HEAD abc123\n"
            "branch refs/heads/main"
        )
        result = _parse_porcelain(output, Path("/tmp/repo"))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# list_worktrees
# ---------------------------------------------------------------------------


class TestListWorktrees:
    def test_returns_empty_if_no_git_root(self, tmp_path: Path) -> None:
        assert list_worktrees(tmp_path) == []

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=1, stdout="", stderr=""
        )
        assert list_worktrees(tmp_path) == []

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_parses_output(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[],
            returncode=0,
            stdout=f"worktree {tmp_path}\nHEAD abc123\nbranch refs/heads/main\n\n",
            stderr="",
        )
        result = list_worktrees(tmp_path)
        assert len(result) == 1
        assert result[0].branch == "main"

    @patch("dekk.tools.worktree.core.subprocess.run", side_effect=FileNotFoundError)
    def test_git_not_found(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        assert list_worktrees(tmp_path) == []


# ---------------------------------------------------------------------------
# create_worktree
# ---------------------------------------------------------------------------


class TestCreateWorktree:
    def test_not_a_git_repo(self, tmp_path: Path) -> None:
        result = create_worktree("feat", git_root=tmp_path)
        assert not result.ok
        assert result.error is not None

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_success(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=0, stdout="", stderr=""
        )
        result = create_worktree("feat", git_root=tmp_path)
        assert result.ok
        assert result.branch == "feat"

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_failure(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=128, stdout="", stderr="fatal: branch already exists"
        )
        result = create_worktree("feat", git_root=tmp_path)
        assert not result.ok
        assert "branch already exists" in (result.error or "")

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_custom_path(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        custom = tmp_path / "custom-wt"
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=0, stdout="", stderr=""
        )
        result = create_worktree("feat", path=custom, git_root=tmp_path)
        assert result.ok

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_existing_branch(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=0, stdout="", stderr=""
        )
        result = create_worktree("feat", git_root=tmp_path, new_branch=False)
        assert result.ok
        # Verify -b was NOT in the command
        call_args = mock_run.call_args[0][0]  # type: ignore[union-attr]
        assert "-b" not in call_args


# ---------------------------------------------------------------------------
# remove_worktree
# ---------------------------------------------------------------------------


class TestRemoveWorktree:
    def test_not_a_git_repo(self, tmp_path: Path) -> None:
        ok, msg = remove_worktree("/tmp/wt", git_root=tmp_path)
        assert not ok

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_success(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=0, stdout="", stderr=""
        )
        ok, msg = remove_worktree("/tmp/wt", git_root=tmp_path)
        assert ok

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_force_flag(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=0, stdout="", stderr=""
        )
        remove_worktree("/tmp/wt", git_root=tmp_path, force=True)
        call_args = mock_run.call_args[0][0]  # type: ignore[union-attr]
        assert "--force" in call_args


# ---------------------------------------------------------------------------
# prune_worktrees
# ---------------------------------------------------------------------------


class TestPruneWorktrees:
    def test_not_a_git_repo(self, tmp_path: Path) -> None:
        ok, msg = prune_worktrees(git_root=tmp_path)
        assert not ok

    @patch("dekk.tools.worktree.core.subprocess.run")
    def test_success(self, mock_run: object, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[attr-defined]
            args=[], returncode=0, stdout="", stderr=""
        )
        ok, msg = prune_worktrees(git_root=tmp_path)
        assert ok


# ---------------------------------------------------------------------------
# Worktree skill auto-scaffold
# ---------------------------------------------------------------------------


class TestWorktreeSkillScaffold:
    def test_scaffold_creates_worktree_skill(self, tmp_path: Path) -> None:
        """When a git repo is detected, scaffold_agents_dir should create worktree skill."""
        from dekk.skills.scaffold import scaffold_agents_dir

        (tmp_path / ".git").mkdir()
        result = scaffold_agents_dir(tmp_path)
        skill_file = result / "skills" / "worktree" / "SKILL.md"
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "dekk worktree" in content
        assert "name: worktree" in content

    def test_scaffold_skips_worktree_if_no_git(self, tmp_path: Path) -> None:
        """No .git dir means no worktree skill."""
        from dekk.skills.scaffold import scaffold_agents_dir

        result = scaffold_agents_dir(tmp_path)
        skill_file = result / "skills" / "worktree" / "SKILL.md"
        assert not skill_file.exists()

    def test_scaffold_does_not_overwrite_worktree_skill(self, tmp_path: Path) -> None:
        """Existing worktree skill should not be overwritten."""
        from dekk.skills.scaffold import scaffold_agents_dir

        (tmp_path / ".git").mkdir()
        # Pre-create a custom worktree skill
        skill_dir = tmp_path / ".agents" / "skills" / "worktree"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("custom content")

        scaffold_agents_dir(tmp_path)
        assert (skill_dir / "SKILL.md").read_text() == "custom content"
