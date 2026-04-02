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
    with pytest.raises(NotFoundError) as exc:
        run_project_command("demo", ["hello"])
    assert "dekk demo setup" in str(exc.value.hint)


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


# -- Built-in project sub-command routing ----------------------------------


def test_agents_without_appname_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``dekk agents init`` (no app name) raises with a helpful hint."""
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="project sub-command"):
        run_project_command("agents", ["init"])


def test_worktree_without_appname_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``dekk worktree list`` (no app name) raises with a helpful hint."""
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="project sub-command"):
        run_project_command("worktree", ["list"])


def test_agents_without_appname_hint_includes_project_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_spec(tmp_path, project="myapp")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as exc:
        run_project_command("agents", ["init"])
    assert "dekk myapp agents init" in str(exc.value.hint)


def test_missing_command_shows_agents_and_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``dekk demo`` (no command) should print project help."""
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)
    code = run_project_command("demo", [])
    assert code == 0


def test_missing_command_help_includes_agents_and_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)

    run_project_command("demo", [])

    out = capsys.readouterr().out
    assert "demo" in out
    assert "agents" in out
    assert "worktree" in out
    assert "setup" in out
    assert "hello" in out


def test_explicit_help_alias_prints_project_help(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)

    code = run_project_command("demo", ["help"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Usage" in out
    assert "dekk demo" in out


def test_help_flag_prints_project_help(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)

    code = run_project_command("demo", ["--help"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Commands" in out
    assert "hello" in out


def test_help_for_single_command_prints_command_help(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)

    code = run_project_command("demo", ["help", "hello"])

    assert code == 0
    out = capsys.readouterr().out
    assert "demo:hello" in out
    assert "Defined in `.dekk.toml`" in out


def test_help_for_builtin_subcommand_prints_command_help(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)

    code = run_project_command("demo", ["help", "agents"])

    assert code == 0
    out = capsys.readouterr().out
    assert "demo:agents" in out
    assert "built-in project sub-command" in out


def test_help_for_setup_prints_builtin_command_help(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)

    code = run_project_command("demo", ["help", "setup"])

    assert code == 0
    out = capsys.readouterr().out
    assert "demo:setup" in out
    assert "Create or refresh the configured runtime environment" in out


def test_project_setup_routes_to_runtime_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)

    with patch("dekk.environment.setup.run_setup") as setup_mock:
        setup_mock.return_value.environment_created = False
        setup_mock.return_value.environment_prefix = None
        setup_mock.return_value.environment_kind = None
        setup_mock.return_value.environment_packages = []
        setup_mock.return_value.npm_installed = []
        setup_mock.return_value.errors = []
        code = run_project_command("demo", ["setup"])

    assert code == 0
    setup_mock.assert_called_once_with(tmp_path, force=False)


def test_project_setup_is_hidden_when_project_defines_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = tmp_path / ".dekk.toml"
    spec.write_text(
        "[project]\n"
        'name = "demo"\n\n'
        "[commands]\n"
        'setup = { run = "echo custom", description = "custom setup" }\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    run_project_command("demo", ["help"])

    out = capsys.readouterr().out
    assert "custom setup" in out


def test_agents_subcommand_routing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``dekk demo agents list`` routes to the agents sub-app."""
    _write_spec(tmp_path, project="demo")
    # Create the .agents/ dir so agents list doesn't error
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    # agents list with no skills should complete without error
    code = run_project_command("demo", ["agents", "list"])
    assert code == 0
