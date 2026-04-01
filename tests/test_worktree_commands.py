from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from dekk.project.worktree import WorktreeCreateResult
from dekk.tools.worktree.commands import create_worktree_app

runner = CliRunner()


def test_worktree_create_uses_project_scoped_setup(tmp_path: Path) -> None:
    app = create_worktree_app()
    worktree_path = tmp_path / "wt"
    worktree_path.mkdir()
    (worktree_path / ".dekk.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

    result_obj = WorktreeCreateResult(path=worktree_path, branch="feat", created=True)

    with patch("dekk.tools.worktree.core.create_worktree", return_value=result_obj):
        with patch("dekk.environment.spec.EnvironmentSpec.from_file") as from_file:
            from_file.return_value = SimpleNamespace(project_name="demo")
            with patch("subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0)
                result = runner.invoke(app, ["create", "feat"])

    assert result.exit_code == 0
    run_mock.assert_called_once_with(["dekk", "demo", "setup"], cwd=worktree_path, check=False)


def test_worktree_create_falls_back_to_global_setup_when_spec_parse_fails(tmp_path: Path) -> None:
    app = create_worktree_app()
    worktree_path = tmp_path / "wt"
    worktree_path.mkdir()
    (worktree_path / ".dekk.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

    result_obj = WorktreeCreateResult(path=worktree_path, branch="feat", created=True)

    with patch("dekk.tools.worktree.core.create_worktree", return_value=result_obj):
        spec_patch = "dekk.environment.spec.EnvironmentSpec.from_file"
        with patch(spec_patch, side_effect=RuntimeError("boom")):
            with patch("subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0)
                result = runner.invoke(app, ["create", "feat"])

    assert result.exit_code == 0
    run_mock.assert_called_once_with(["dekk", "setup"], cwd=worktree_path, check=False)
