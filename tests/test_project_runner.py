from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from dekk.cli.errors import NotFoundError, ValidationError
from dekk.project.runner import run_project_command


def _write_spec(root: Path, *, project: str = "demo") -> Path:
    spec = root / ".dekk.toml"
    spec.write_text(
        "[project]\n"
        f'name = "{project}"\n\n'
        "[environment]\n"
        'type = "conda"\n'
        'path = "{project}/.dekk/env"\n'
        'file = "environment.yaml"\n\n'
        "[commands]\n"
        'hello = { run = "echo hi", description = "test" }\n',
        encoding="utf-8",
    )
    return spec


def test_requires_spec_in_cwd_hierarchy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(NotFoundError):
        run_project_command("demo", ["hello"])


def test_project_name_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError):
        run_project_command("other", ["hello"])


def test_nested_cwd_walkup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_spec(tmp_path, project="demo")
    env_prefix = tmp_path / ".dekk" / "env"
    env_prefix.mkdir(parents=True)
    (env_prefix / "conda-meta").mkdir()

    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    with patch("subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        with patch("dekk.project.runner.EnvironmentActivator.activate") as activate_mock:
            activate_mock.return_value.env_vars = {"PATH": str(env_prefix / "bin")}
            code = run_project_command("demo", ["hello"])

    assert code == 0
    run_mock.assert_called_once()


def test_unknown_registered_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_spec(tmp_path, project="demo")
    env_prefix = tmp_path / ".dekk" / "env"
    env_prefix.mkdir(parents=True)
    (env_prefix / "conda-meta").mkdir()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(NotFoundError):
        run_project_command("demo", ["missing"])


def test_missing_environment_prefix_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(NotFoundError):
        run_project_command("demo", ["hello"])


def test_worktree_specific_spec_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wt1 = tmp_path / "wt1"
    wt2 = tmp_path / "wt2"
    wt1.mkdir()
    wt2.mkdir()
    _write_spec(wt1, project="app1")
    _write_spec(wt2, project="app2")
    for root in (wt1, wt2):
        env_prefix = root / ".dekk" / "env"
        env_prefix.mkdir(parents=True)
        (env_prefix / "conda-meta").mkdir()

    with patch("subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        with patch("dekk.project.runner.EnvironmentActivator.activate") as activate_mock:
            activate_mock.return_value.env_vars = {"PATH": os.environ.get("PATH", "")}
            monkeypatch.chdir(wt1)
            assert run_project_command("app1", ["hello"]) == 0
            monkeypatch.chdir(wt2)
            assert run_project_command("app2", ["hello"]) == 0

    assert run_mock.call_count == 2
