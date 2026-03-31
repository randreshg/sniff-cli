"""Focused tests for the enhanced Typer wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer as base_typer
from typer.testing import CliRunner

from dekk.cli import typer_app
from dekk.cli.errors import DekkError, ExitCodes, NotFoundError, ValidationError
from dekk.cli.typer_app import Typer, _get_typer

runner = CliRunner()


def _make_fake_context(**overrides: object) -> MagicMock:
    ctx = MagicMock(name="ExecutionContext")
    ctx.platform = overrides.get("platform", MagicMock(os="Linux", arch="x86_64"))
    ctx.conda_env = overrides.get("conda_env", None)
    ctx.ci_info = overrides.get("ci_info", MagicMock(is_ci=False))
    ctx.workspace = overrides.get(
        "workspace",
        MagicMock(root=Path("/fake/project"), git_info=None),
    )
    ctx.to_dict.return_value = overrides.get("to_dict", {"platform": "linux"})
    return ctx


def _make_group_app(fake_ctx: MagicMock, **app_kwargs: object) -> Typer:
    app = Typer(**app_kwargs)
    app._context = fake_ctx

    @app.command()
    def _noop() -> None:
        pass

    return app


def test_get_typer_lazy_loads_and_wraps_base_typer():
    _get_typer()
    app = Typer()

    assert typer_app._TYPER_AVAILABLE is True
    assert isinstance(app._app, base_typer.Typer)


@patch("dekk.cli.typer_app._TYPER_AVAILABLE", False)
def test_get_typer_raises_when_dependency_is_missing():
    with pytest.raises(ImportError, match="typer is required"):
        _get_typer()


def test_construction_stores_configuration_and_passthrough_options():
    app = Typer(
        name="demo",
        enable_tracking=True,
        tully_db_path=Path("/tmp/tully.db"),
        tully_experiment_name="exp",
        auto_capture_env=False,
        auto_activate=True,
        fail_fast=False,
        project_version="1.2.3",
        help="CLI help",
        no_args_is_help=True,
    )

    assert app._name == "demo"
    assert app._enable_tracking is True
    assert app._tully_db_path == Path("/tmp/tully.db")
    assert app._tully_experiment_name == "exp"
    assert app._auto_capture_env is False
    assert app._auto_activate is True
    assert app._fail_fast is False
    assert app._project_version == "1.2.3"
    assert app.info.help == "CLI help"
    assert app.info.no_args_is_help is True
    assert app._before_hooks == [app._auto_activation_hook]


def test_context_is_captured_once_and_shortcuts_proxy_to_it():
    app = Typer()
    fake_ctx = _make_fake_context(conda_env=MagicMock(name="conda"))

    with patch("dekk.core.context.ExecutionContext.capture", return_value=fake_ctx) as capture:
        assert app.context is fake_ctx
        assert app.context is fake_ctx
        assert app.platform is fake_ctx.platform
        assert app.conda_env is fake_ctx.conda_env
        assert app.ci_info is fake_ctx.ci_info
        assert app.workspace is fake_ctx.workspace

    capture.assert_called_once()


def test_lazy_exports_delegate_to_typer_module():
    assert typer_app.Option is base_typer.Option
    assert typer_app.Argument is base_typer.Argument
    assert typer_app.Exit is base_typer.Exit


def test_hooks_run_in_order_and_after_hook_runs_on_failure():
    fake_ctx = _make_fake_context()
    app = _make_group_app(fake_ctx)
    events: list[str] = []

    app.before_command(lambda ctx: events.append(f"before:{ctx is fake_ctx}"))
    app.after_command(lambda ctx: events.append(f"after:{ctx is fake_ctx}"))

    @app.command()
    def success() -> None:
        events.append("command")

    @app.command()
    def fail() -> None:
        raise RuntimeError("boom")

    success_result = runner.invoke(app, ["success"])
    fail_result = runner.invoke(app, ["fail"])

    assert success_result.exit_code == 0
    assert fail_result.exit_code != 0
    assert events == [
        "before:True",
        "command",
        "after:True",
        "before:True",
        "after:True",
    ]


def test_command_preserves_function_name_for_cli_routing():
    fake_ctx = _make_fake_context()
    app = _make_group_app(fake_ctx)

    @app.command()
    def my_fancy_func() -> None:
        pass

    result = runner.invoke(app, ["my-fancy-func"])
    assert result.exit_code == 0


def test_single_command_app_invokes_default_command():
    app = Typer()
    app._context = _make_fake_context()

    @app.command()
    def hello() -> None:
        print("solo")

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "solo" in result.output


def test_capture_env_default_and_override_are_honored():
    fake_ctx = _make_fake_context()
    default_app = _make_group_app(fake_ctx)
    override_app = _make_group_app(fake_ctx, auto_capture_env=False)
    default_calls: list[object] = []
    override_calls: list[object] = []

    default_app.before_command(lambda ctx: default_calls.append(ctx))
    override_app.before_command(lambda ctx: override_calls.append(ctx))

    @default_app.command()
    def default_cmd() -> None:
        pass

    @override_app.command(capture_env=True)
    def override_cmd() -> None:
        pass

    runner.invoke(default_app, ["default-cmd"])
    runner.invoke(override_app, ["override-cmd"])

    assert default_calls == [fake_ctx]
    assert override_calls == [fake_ctx]


def test_tracking_starts_with_context_payload_and_completes():
    fake_ctx = _make_fake_context(to_dict={"platform": "linux", "nested": {"a": 1}})
    app = Typer(enable_tracking=True, tully_experiment_name="exp")
    app._context = fake_ctx
    mock_client = MagicMock()
    mock_client.start_run.return_value = "run-123"
    app._tully_client = mock_client

    run_id = app._start_tracking("cmd_name", fake_ctx)
    app._complete_tracking(run_id, "success")

    assert run_id == "run-123"
    mock_client.start_run.assert_called_once_with(
        command_name="cmd_name",
        experiment_name="exp",
        environment={"platform": "linux", "nested": {"a": 1}},
    )
    mock_client.complete_run.assert_called_once_with("run-123", "success", error=None)
    assert app._current_run_id is None


def test_tracking_returns_none_without_tully_client():
    app = Typer(enable_tracking=True)

    with patch("dekk.cli.typer_app.Typer._get_tully_client", return_value=None):
        assert app._start_tracking("cmd", _make_fake_context()) is None


def test_tracking_wraps_command_success_and_failure():
    success_ctx = _make_fake_context()
    success_app = _make_group_app(success_ctx, enable_tracking=True)
    success_client = MagicMock()
    success_client.start_run.return_value = "run-success"
    success_app._tully_client = success_client

    @success_app.command()
    def ok() -> None:
        print("ok")

    fail_ctx = _make_fake_context()
    fail_app = _make_group_app(fail_ctx, enable_tracking=True)
    fail_client = MagicMock()
    fail_client.start_run.return_value = "run-fail"
    fail_app._tully_client = fail_client

    @fail_app.command()
    def boom() -> None:
        raise ValueError("broken")

    success_result = runner.invoke(success_app, ["ok"])
    fail_result = runner.invoke(fail_app, ["boom"])

    assert success_result.exit_code == 0
    success_client.complete_run.assert_called_once_with("run-success", "success", error=None)
    assert fail_result.exit_code != 0
    fail_client.complete_run.assert_called_once_with("run-fail", "failed", error="broken")


@pytest.mark.parametrize(
    "method_name, expected_call",
    [("log_metric", ("loss", 0.5, 1)), ("log_artifact", ("model", Path("/tmp/model.pt")))],
)
def test_log_methods_only_emit_when_tracking_is_active(method_name, expected_call):
    active = Typer(enable_tracking=True)
    active._current_run_id = "run-1"
    active._tully_client = MagicMock()

    inactive = Typer(enable_tracking=False)
    inactive._current_run_id = "run-2"
    inactive._tully_client = MagicMock()

    if method_name == "log_metric":
        active.log_metric(expected_call[0], expected_call[1], step=expected_call[2])
        inactive.log_metric(expected_call[0], expected_call[1], step=expected_call[2])
        active._tully_client.log_metric.assert_called_once_with("run-1", "loss", 0.5, 1)
        inactive._tully_client.log_metric.assert_not_called()
    else:
        active.log_artifact(expected_call[0], expected_call[1])
        inactive.log_artifact(expected_call[0], expected_call[1])
        active._tully_client.log_artifact.assert_called_once_with(
            "run-1", "model", Path("/tmp/model.pt")
        )
        inactive._tully_client.log_artifact.assert_not_called()


def test_get_tully_client_caches_instance_and_handles_missing_package():
    app = Typer(tully_db_path=Path("/tmp/tully.db"))
    fake_module = MagicMock()
    fake_client = MagicMock()
    fake_module.TullyClient.return_value = fake_client

    with patch.dict("sys.modules", {"tully": fake_module}):
        assert app._get_tully_client() is fake_client
        assert app._get_tully_client() is fake_client
    fake_module.TullyClient.assert_called_once_with(db_path=Path("/tmp/tully.db"))

    app = Typer()
    with patch.dict("sys.modules", {"tully": None}):
        assert app._get_tully_client() is None


@pytest.mark.parametrize(
    ("app_kwargs", "command_name", "patch_target", "expected_args"),
    [
        (
            {"add_doctor_command": True},
            "doctor",
            "dekk.cli.cli_commands.run_doctor",
            lambda ctx: (ctx,),
        ),
        (
            {"add_version_command": True, "project_version": "3.4.5", "name": "demo"},
            "version",
            "dekk.cli.cli_commands.run_version",
            lambda ctx: ("demo", "3.4.5", ctx),
        ),
        ({"add_env_command": True}, "env", "dekk.cli.cli_commands.run_env", lambda ctx: (ctx,)),
    ],
)
def test_built_in_commands_register_and_dispatch(
    app_kwargs, command_name, patch_target, expected_args
):
    fake_ctx = _make_fake_context()
    app = Typer(**app_kwargs)
    app._context = fake_ctx

    @app.command()
    def _noop() -> None:
        pass

    with patch(patch_target) as handler:
        result = runner.invoke(app, [command_name])

    assert result.exit_code == 0
    handler.assert_called_once_with(*expected_args(fake_ctx))


def test_parent_hooks_do_not_leak_into_child_apps():
    parent = Typer()
    parent._context = _make_fake_context()
    child = Typer()
    child._context = _make_fake_context()
    parent.add_typer(child, name="child")
    events: list[str] = []
    parent.before_command(lambda ctx: events.append("parent-before"))

    @child.command()
    def nested() -> None:
        print("nested")

    result = runner.invoke(parent, ["child", "nested"])

    assert result.exit_code == 0
    assert events == []


@pytest.mark.parametrize(
    ("exc", "exit_code", "hint"),
    [
        (ValidationError("Bad input", hint="Check your config"), ExitCodes.VALIDATION_ERROR, True),
        (NotFoundError("Missing file"), ExitCodes.NOT_FOUND, False),
        (DekkError("Generic error", hint="Try again"), ExitCodes.GENERAL_ERROR, True),
    ],
)
def test_catch_errors_converts_dekk_errors_to_typer_exit(exc, exit_code, hint):
    fake_ctx = _make_fake_context()
    app = _make_group_app(fake_ctx)

    @app.command()
    def fail() -> None:
        raise exc

    result = runner.invoke(app, ["fail"])

    assert result.exit_code == exit_code
    assert exc.message in result.output
    assert ("Hint:" in result.output) is hint


def test_catch_errors_false_and_non_dekk_errors_propagate():
    fake_ctx = _make_fake_context()
    propagate_app = _make_group_app(fake_ctx)
    raw_app = _make_group_app(fake_ctx)

    @propagate_app.command(catch_errors=False)
    def dekk_failure() -> None:
        raise ValidationError("Bad input")

    @raw_app.command()
    def value_failure() -> None:
        raise ValueError("boom")

    dekk_result = runner.invoke(propagate_app, ["dekk-failure"])
    raw_result = runner.invoke(raw_app, ["value-failure"])

    assert isinstance(dekk_result.exception, ValidationError)
    assert isinstance(raw_result.exception, ValueError)


def test_caught_dekk_errors_still_run_after_hooks_and_complete_tracking():
    fake_ctx = _make_fake_context()
    app = _make_group_app(fake_ctx, enable_tracking=True)
    app._tully_client = MagicMock()
    app._tully_client.start_run.return_value = "run-err"
    hooks: list[bool] = []
    app.after_command(lambda ctx: hooks.append(ctx is fake_ctx))

    @app.command()
    def fail() -> None:
        raise ValidationError("tracked error")

    result = runner.invoke(app, ["fail"])

    assert result.exit_code == ExitCodes.VALIDATION_ERROR
    assert hooks == [True]
    app._tully_client.complete_run.assert_called_once_with(
        "run-err",
        "failed",
        error="tracked error",
    )
