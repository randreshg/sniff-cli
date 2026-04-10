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


def test_skills_without_appname_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``dekk skills init`` (no app name) raises with a helpful hint."""
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="project sub-command"):
        run_project_command("skills", ["init"])


def test_worktree_without_appname_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``dekk worktree list`` (no app name) raises with a helpful hint."""
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="project sub-command"):
        run_project_command("worktree", ["list"])


def test_skills_without_appname_hint_includes_project_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_spec(tmp_path, project="myapp")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as exc:
        run_project_command("skills", ["init"])
    assert "dekk myapp skills init" in str(exc.value.hint)


def test_missing_command_shows_skills_and_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``dekk demo`` (no command) should print project help."""
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)
    code = run_project_command("demo", [])
    assert code == 0


def test_missing_command_help_includes_skills_and_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_spec(tmp_path, project="demo")
    monkeypatch.chdir(tmp_path)

    run_project_command("demo", [])

    out = capsys.readouterr().out
    assert "demo" in out
    assert "skills" in out
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

    code = run_project_command("demo", ["help", "skills"])

    assert code == 0
    out = capsys.readouterr().out
    assert "demo:skills" in out
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


def test_skills_subcommand_routing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``dekk demo skills list`` routes to the skills sub-app."""
    _write_spec(tmp_path, project="demo")
    # Create the .agents/ dir so skills list doesn't error
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    # skills list with no skills should complete without error
    code = run_project_command("demo", ["skills", "list"])
    assert code == 0


def test_skill_tag_in_help_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Commands with skill=true show [skill] tag in help."""
    spec = tmp_path / ".dekk.toml"
    spec.write_text(
        "[project]\n"
        'name = "demo"\n\n'
        "[commands]\n"
        'build = { run = "make", description = "Build", skill = true }\n'
        'clean = { run = "rm -rf", description = "Clean" }\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    run_project_command("demo", [])

    out = capsys.readouterr().out
    # build should have [skill] tag, clean should not
    for line in out.split("\n"):
        if "build" in line and "Build" in line:
            assert "skill" in line
        if "clean" in line and "Clean" in line:
            assert "skill" not in line


def test_skill_hint_after_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """After successful command, skill hint is printed if SKILL.md exists."""
    _write_spec(tmp_path, project="demo")
    env_prefix = tmp_path / ".dekk" / "env"
    env_prefix.mkdir(parents=True)
    (env_prefix / "conda-meta").mkdir()

    # Create a skill file
    skill_dir = tmp_path / ".agents" / "skills" / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: hello\ndescription: test\n---\n")

    monkeypatch.chdir(tmp_path)

    with patch("subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        with patch("dekk.project.runner.EnvironmentActivator.activate") as activate_mock:
            activate_mock.return_value.env_vars = {"PATH": str(env_prefix / "bin")}
            run_project_command("demo", ["hello"])

    out = capsys.readouterr().out
    assert ".agents/skills/hello/SKILL.md" in out


# -- Hierarchical commands + groups -----------------------------------------


def _write_hierarchical_spec(root: Path) -> Path:
    spec = root / ".dekk.toml"
    spec.write_text(
        '[project]\nname = "demo"\n\n'
        "[commands]\n"
        'build = { run = "make", description = "Build", skill = true, group = "Dev" }\n'
        'clean = { run = "rm -rf", description = "Clean", group = "Dev" }\n'
        'deploy = { run = "deploy.sh", description = "Deploy" }\n\n'
        "[commands.llm]\n"
        'description = "Manage LLM credentials"\n'
        'group = "Config"\n'
        'add = { run = "app llm add", description = "Add credential", skill = true }\n'
        'list = { run = "app llm list", description = "List credentials" }\n',
        encoding="utf-8",
    )
    return spec


def test_hierarchical_command_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hierarchical commands parse into nested CommandSpec."""
    from dekk.environment.spec import EnvironmentSpec

    _write_hierarchical_spec(tmp_path)
    monkeypatch.chdir(tmp_path)

    spec = EnvironmentSpec.from_file(tmp_path / ".dekk.toml")
    assert "llm" in spec.commands
    llm = spec.commands["llm"]
    assert llm.is_group
    assert "add" in llm.commands
    assert llm.commands["add"].run == "app llm add"
    assert llm.commands["add"].skill is True
    assert llm.description == "Manage LLM credentials"


def test_hierarchical_command_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``dekk demo llm add`` resolves through the tree and runs the leaf command."""
    _write_hierarchical_spec(tmp_path)
    env_prefix = tmp_path / ".dekk" / "env"
    env_prefix.mkdir(parents=True)
    (env_prefix / "conda-meta").mkdir()
    monkeypatch.chdir(tmp_path)

    with patch("subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        with patch("dekk.project.runner.EnvironmentActivator.activate") as activate_mock:
            activate_mock.return_value.env_vars = {"PATH": str(env_prefix / "bin")}
            code = run_project_command("demo", ["llm", "add", "--provider", "openai"])

    assert code == 0
    call_args = run_mock.call_args
    assert "app llm add --provider openai" in call_args[0][0]


def test_group_help_on_bare_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``dekk demo llm`` (no subcommand) shows group help."""
    _write_hierarchical_spec(tmp_path)
    monkeypatch.chdir(tmp_path)

    code = run_project_command("demo", ["llm"])

    assert code == 0
    out = capsys.readouterr().out
    assert "llm" in out
    assert "add" in out
    assert "list" in out
    assert "Manage LLM credentials" in out


def test_grouped_help_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Project help shows commands grouped by their group field."""
    _write_hierarchical_spec(tmp_path)
    monkeypatch.chdir(tmp_path)

    run_project_command("demo", [])

    out = capsys.readouterr().out
    assert "Dev" in out
    assert "Config" in out
    assert "Built-in" in out


def test_group_shows_arrow_indicator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Group commands show arrow indicator in help."""
    _write_hierarchical_spec(tmp_path)
    monkeypatch.chdir(tmp_path)

    run_project_command("demo", [])

    out = capsys.readouterr().out
    for line in out.split("\n"):
        if "llm" in line and "Manage" in line:
            assert "\u2192" in line  # → arrow
            break
    else:
        pytest.fail("llm group line with arrow not found in help output")


def test_leaf_command_without_run_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Leaf command with no run field raises ValidationError at parse time."""
    spec = tmp_path / ".dekk.toml"
    spec.write_text(
        '[project]\nname = "demo"\n\n'
        "[commands]\n"
        'broken = { description = "No run field" }\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError, match="no 'run' field"):
        from dekk.environment.spec import EnvironmentSpec
        EnvironmentSpec.from_file(tmp_path / ".dekk.toml")


def test_command_not_found_exit_127(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit code 127 gives a contextual error about binary not found."""
    _write_spec(tmp_path, project="demo")
    env_prefix = tmp_path / ".dekk" / "env"
    env_prefix.mkdir(parents=True)
    (env_prefix / "conda-meta").mkdir()
    monkeypatch.chdir(tmp_path)

    with patch("subprocess.run") as run_mock:
        run_mock.return_value.returncode = 127
        with patch("dekk.project.runner.EnvironmentActivator.activate") as activate_mock:
            activate_mock.return_value.env_vars = {"PATH": str(env_prefix / "bin")}
            with pytest.raises(NotFoundError, match="not found"):
                run_project_command("demo", ["hello"])


def test_help_for_nested_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``dekk demo help llm add`` shows help for nested command."""
    _write_hierarchical_spec(tmp_path)
    monkeypatch.chdir(tmp_path)

    code = run_project_command("demo", ["help", "llm", "add"])

    assert code == 0
    out = capsys.readouterr().out
    assert "demo:llm:add" in out
    assert "Add credential" in out


def test_help_for_group_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``dekk demo help llm`` shows group help."""
    _write_hierarchical_spec(tmp_path)
    monkeypatch.chdir(tmp_path)

    code = run_project_command("demo", ["help", "llm"])

    assert code == 0
    out = capsys.readouterr().out
    assert "llm" in out
    assert "add" in out
    assert "list" in out


def test_group_without_run_shows_help_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Group command with no run field shows group help instead of error."""
    _write_hierarchical_spec(tmp_path)
    monkeypatch.chdir(tmp_path)

    # llm has no run field, only children — should show help
    code = run_project_command("demo", ["llm"])
    assert code == 0


def test_ungrouped_commands_shown_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Commands without a group appear before grouped commands."""
    _write_hierarchical_spec(tmp_path)
    monkeypatch.chdir(tmp_path)

    run_project_command("demo", [])

    out = capsys.readouterr().out
    # deploy has no group, should appear under "Commands"
    assert "Commands" in out
    assert "deploy" in out
