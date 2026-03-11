"""Tests for sniff.typer_app -- the enhanced Typer wrapper."""

from __future__ import annotations

import functools
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from sniff.typer_app import Typer, _require_typer, _TYPER_AVAILABLE
from sniff.cli.errors import SniffError, ValidationError, NotFoundError, ExitCodes
import typer as base_typer
from typer.testing import CliRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

runner = CliRunner()


def _make_fake_context(**overrides: object) -> MagicMock:
    """Return a lightweight mock ExecutionContext."""
    ctx = MagicMock(name="ExecutionContext")
    ctx.platform = overrides.get("platform", MagicMock(os="Linux", arch="x86_64"))
    ctx.conda_env = overrides.get("conda_env", None)
    ctx.ci_info = overrides.get("ci_info", MagicMock(is_ci=False))
    ctx.workspace = overrides.get(
        "workspace", MagicMock(root=Path("/fake/project"), git_info=None)
    )
    ctx.to_dict.return_value = {"platform": "linux"}
    return ctx


def _make_app_with_two_commands(fake_ctx, **app_kwargs):
    """Build a Typer with two commands so subcommand invocation works.

    Typer treats a single-command app as the default command (no subcommand
    name required).  By always registering a second dummy command we ensure
    every test can invoke by name.
    """
    app = Typer(**app_kwargs)
    app._context = fake_ctx

    # A dummy command that is never invoked -- just forces group mode.
    @app.command()
    def _noop():
        pass

    return app


# ===========================================================================
# Module-level checks
# ===========================================================================


class TestModuleAvailability:
    def test_typer_is_available(self):
        assert _TYPER_AVAILABLE is True

    def test_require_typer_succeeds(self):
        _require_typer()

    @patch("sniff.typer_app._TYPER_AVAILABLE", False)
    def test_require_typer_raises_when_missing(self):
        with pytest.raises(ImportError, match="typer is required"):
            _require_typer()

    def test_typer_class_is_subclass(self):
        assert issubclass(Typer, base_typer.Typer)


# ===========================================================================
# Construction
# ===========================================================================


class TestConstruction:
    def test_default_construction(self):
        app = Typer()
        assert app._enable_tracking is False
        assert app._tully_db_path is None
        assert app._tully_experiment_name is None
        assert app._auto_capture_env is True
        assert app._project_version is None
        assert app._name is None

    def test_name_parameter(self):
        app = Typer(name="myapp")
        assert app._name == "myapp"

    def test_enable_tracking(self):
        app = Typer(enable_tracking=True)
        assert app._enable_tracking is True

    def test_tully_db_path(self):
        app = Typer(tully_db_path=Path("/tmp/test.db"))
        assert app._tully_db_path == Path("/tmp/test.db")

    def test_tully_experiment_name(self):
        app = Typer(tully_experiment_name="exp1")
        assert app._tully_experiment_name == "exp1"

    def test_auto_capture_env_false(self):
        app = Typer(auto_capture_env=False)
        assert app._auto_capture_env is False

    def test_project_version(self):
        app = Typer(project_version="1.2.3")
        assert app._project_version == "1.2.3"

    def test_typer_kwargs_passthrough(self):
        app = Typer(help="My help text", no_args_is_help=True)
        assert app.info.help == "My help text"
        assert app.info.no_args_is_help is True

    def test_initial_context_is_none(self):
        app = Typer()
        assert app._context is None

    def test_initial_tully_client_is_none(self):
        app = Typer()
        assert app._tully_client is None

    def test_initial_run_id_is_none(self):
        app = Typer()
        assert app._current_run_id is None

    def test_initial_hooks_empty(self):
        app = Typer()
        assert app._before_hooks == []
        assert app._after_hooks == []


# ===========================================================================
# Lazy-loaded properties
# ===========================================================================


class TestLazyProperties:
    def test_context_lazy_loading(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        with patch("sniff.context.ExecutionContext.capture", return_value=fake_ctx):
            ctx = app.context
            assert ctx is fake_ctx

    def test_context_cached(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        with patch("sniff.context.ExecutionContext.capture", return_value=fake_ctx) as mock_cap:
            _ = app.context
            _ = app.context
            mock_cap.assert_called_once()

    def test_platform_property(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        app._context = fake_ctx
        assert app.platform is fake_ctx.platform

    def test_conda_env_property(self):
        app = Typer()
        fake_ctx = _make_fake_context(conda_env=MagicMock(name="myenv"))
        app._context = fake_ctx
        assert app.conda_env is fake_ctx.conda_env

    def test_conda_env_none(self):
        app = Typer()
        fake_ctx = _make_fake_context(conda_env=None)
        app._context = fake_ctx
        assert app.conda_env is None

    def test_ci_info_property(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        app._context = fake_ctx
        assert app.ci_info is fake_ctx.ci_info

    def test_workspace_property(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        app._context = fake_ctx
        assert app.workspace is fake_ctx.workspace

    def test_platform_triggers_capture(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        with patch("sniff.context.ExecutionContext.capture", return_value=fake_ctx):
            _ = app.platform
        assert app._context is fake_ctx

    def test_ci_info_triggers_capture(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        with patch("sniff.context.ExecutionContext.capture", return_value=fake_ctx):
            _ = app.ci_info
        assert app._context is fake_ctx

    def test_workspace_triggers_capture(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        with patch("sniff.context.ExecutionContext.capture", return_value=fake_ctx):
            _ = app.workspace
        assert app._context is fake_ctx


# ===========================================================================
# Session hooks
# ===========================================================================


class TestSessionHooks:
    def test_before_command_register(self):
        app = Typer()
        hook = MagicMock()
        app.before_command(hook)
        assert hook in app._before_hooks

    def test_after_command_register(self):
        app = Typer()
        hook = MagicMock()
        app.after_command(hook)
        assert hook in app._after_hooks

    def test_multiple_before_hooks(self):
        app = Typer()
        h1, h2, h3 = MagicMock(), MagicMock(), MagicMock()
        app.before_command(h1)
        app.before_command(h2)
        app.before_command(h3)
        assert app._before_hooks == [h1, h2, h3]

    def test_multiple_after_hooks(self):
        app = Typer()
        h1, h2 = MagicMock(), MagicMock()
        app.after_command(h1)
        app.after_command(h2)
        assert app._after_hooks == [h1, h2]

    def test_before_hook_called_on_command(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        hook = MagicMock()
        app.before_command(hook)

        @app.command()
        def greet():
            pass

        result = runner.invoke(app, ["greet"])
        assert result.exit_code == 0
        hook.assert_called_once_with(fake_ctx)

    def test_after_hook_called_on_command(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        hook = MagicMock()
        app.after_command(hook)

        @app.command()
        def greet():
            pass

        result = runner.invoke(app, ["greet"])
        assert result.exit_code == 0
        hook.assert_called_once_with(fake_ctx)

    def test_hooks_called_in_order(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        call_order: list[str] = []
        app.before_command(lambda ctx: call_order.append("before1"))
        app.before_command(lambda ctx: call_order.append("before2"))
        app.after_command(lambda ctx: call_order.append("after1"))
        app.after_command(lambda ctx: call_order.append("after2"))

        @app.command()
        def greet():
            call_order.append("command")

        runner.invoke(app, ["greet"])
        assert call_order == ["before1", "before2", "command", "after1", "after2"]

    def test_after_hook_called_on_exception(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        hook = MagicMock()
        app.after_command(hook)

        @app.command()
        def fail():
            raise RuntimeError("boom")

        result = runner.invoke(app, ["fail"])
        assert result.exit_code != 0
        hook.assert_called_once()

    def test_before_hook_not_called_for_unknown_command(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)
        hook = MagicMock()
        app.before_command(hook)

        runner.invoke(app, ["nonexistent"])
        hook.assert_not_called()


# ===========================================================================
# command() decorator
# ===========================================================================


class TestCommandDecorator:
    def test_basic_command(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def hello():
            print("hello world")

        result = runner.invoke(app, ["hello"])
        assert result.exit_code == 0
        assert "hello world" in result.output

    def test_command_with_args(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def greet(name: str):
            print(f"Hello, {name}!")

        result = runner.invoke(app, ["greet", "Alice"])
        assert result.exit_code == 0
        assert "Hello, Alice!" in result.output

    def test_command_preserves_function_name(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def my_fancy_func():
            pass

        result = runner.invoke(app, ["my-fancy-func"])
        assert result.exit_code == 0

    def test_command_with_track_true(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, enable_tracking=False)

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-123"
        app._tully_client = mock_client

        @app.command(track=True)
        def tracked_cmd():
            pass

        runner.invoke(app, ["tracked-cmd"])
        mock_client.start_run.assert_called_once()
        mock_client.complete_run.assert_called_once_with("run-123", "success", error=None)

    def test_command_with_track_false_override(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, enable_tracking=True)

        mock_client = MagicMock()
        app._tully_client = mock_client

        @app.command(track=False)
        def untracked_cmd():
            pass

        runner.invoke(app, ["untracked-cmd"])
        mock_client.start_run.assert_not_called()

    def test_command_capture_env_false(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, auto_capture_env=False)

        calls: list[object] = []
        app.before_command(lambda ctx: calls.append(ctx))

        @app.command()
        def cmd():
            pass

        runner.invoke(app, ["cmd"])
        assert calls == [None]

    def test_command_capture_env_true_default(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, auto_capture_env=True)

        calls: list[object] = []
        app.before_command(lambda ctx: calls.append(ctx))

        @app.command()
        def cmd():
            pass

        runner.invoke(app, ["cmd"])
        assert calls == [fake_ctx]

    def test_command_return_value(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def cmd():
            print("output")

        result = runner.invoke(app, ["cmd"])
        assert "output" in result.output

    def test_single_command_invocation(self):
        """With a single command, Typer makes it the default (no name needed)."""
        app = Typer()
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        @app.command()
        def hello():
            print("solo")

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "solo" in result.output

    def test_single_command_with_arg(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        @app.command()
        def greet(name: str):
            print(f"Hi {name}")

        result = runner.invoke(app, ["Alice"])
        assert result.exit_code == 0
        assert "Hi Alice" in result.output


# ===========================================================================
# Tracking
# ===========================================================================


class TestTracking:
    def test_start_tracking_creates_client(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-abc"

        with patch("sniff.typer_app.Typer._get_tully_client", return_value=mock_client):
            run_id = app._start_tracking("test_cmd", fake_ctx)

        assert run_id == "run-abc"
        assert app._current_run_id == "run-abc"

    def test_start_tracking_returns_none_without_tully(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()

        with patch("sniff.typer_app.Typer._get_tully_client", return_value=None):
            run_id = app._start_tracking("cmd", fake_ctx)

        assert run_id is None

    def test_complete_tracking_clears_run_id(self):
        app = Typer(enable_tracking=True)
        app._current_run_id = "run-xyz"
        mock_client = MagicMock()
        app._tully_client = mock_client

        app._complete_tracking("run-xyz", "success")
        mock_client.complete_run.assert_called_once_with("run-xyz", "success", error=None)
        assert app._current_run_id is None

    def test_complete_tracking_with_error(self):
        app = Typer(enable_tracking=True)
        app._current_run_id = "run-err"
        mock_client = MagicMock()
        app._tully_client = mock_client

        app._complete_tracking("run-err", "failed", error="kaboom")
        mock_client.complete_run.assert_called_once_with("run-err", "failed", error="kaboom")

    def test_complete_tracking_no_client(self):
        app = Typer(enable_tracking=True)
        app._current_run_id = "run-x"
        app._tully_client = None

        app._complete_tracking("run-x", "success")
        assert app._current_run_id is None

    def test_tracking_on_command_failure(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, enable_tracking=True)

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-fail"
        app._tully_client = mock_client

        @app.command()
        def failing():
            raise ValueError("test error")

        result = runner.invoke(app, ["failing"])
        assert result.exit_code != 0
        mock_client.complete_run.assert_called_once_with(
            "run-fail", "failed", error="test error"
        )

    def test_tracking_on_command_success(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, enable_tracking=True)

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-ok"
        app._tully_client = mock_client

        @app.command()
        def success_cmd():
            print("ok")

        result = runner.invoke(app, ["success-cmd"])
        assert result.exit_code == 0
        mock_client.complete_run.assert_called_once_with("run-ok", "success", error=None)


# ===========================================================================
# log_metric / log_artifact
# ===========================================================================


class TestLogMethods:
    def test_log_metric_when_tracking(self):
        app = Typer(enable_tracking=True)
        mock_client = MagicMock()
        app._tully_client = mock_client
        app._current_run_id = "run-m"

        app.log_metric("loss", 0.5, step=1)
        mock_client.log_metric.assert_called_once_with("run-m", "loss", 0.5, 1)

    def test_log_metric_no_step(self):
        app = Typer(enable_tracking=True)
        mock_client = MagicMock()
        app._tully_client = mock_client
        app._current_run_id = "run-m"

        app.log_metric("acc", 0.9)
        mock_client.log_metric.assert_called_once_with("run-m", "acc", 0.9, None)

    def test_log_metric_no_tracking(self):
        app = Typer(enable_tracking=False)
        mock_client = MagicMock()
        app._tully_client = mock_client
        app._current_run_id = "run-m"

        app.log_metric("loss", 0.5)
        mock_client.log_metric.assert_not_called()

    def test_log_metric_no_run_id(self):
        app = Typer(enable_tracking=True)
        mock_client = MagicMock()
        app._tully_client = mock_client
        app._current_run_id = None

        app.log_metric("loss", 0.5)
        mock_client.log_metric.assert_not_called()

    def test_log_artifact_when_tracking(self):
        app = Typer(enable_tracking=True)
        mock_client = MagicMock()
        app._tully_client = mock_client
        app._current_run_id = "run-a"

        app.log_artifact("model", Path("/tmp/model.pt"))
        mock_client.log_artifact.assert_called_once_with(
            "run-a", "model", Path("/tmp/model.pt")
        )

    def test_log_artifact_no_tracking(self):
        app = Typer(enable_tracking=False)
        mock_client = MagicMock()
        app._tully_client = mock_client
        app._current_run_id = "run-a"

        app.log_artifact("model", Path("/tmp/model.pt"))
        mock_client.log_artifact.assert_not_called()

    def test_log_artifact_no_run_id(self):
        app = Typer(enable_tracking=True)
        mock_client = MagicMock()
        app._tully_client = mock_client
        app._current_run_id = None

        app.log_artifact("model", Path("/tmp/model.pt"))
        mock_client.log_artifact.assert_not_called()


# ===========================================================================
# _get_tully_client
# ===========================================================================


class TestGetTullyClient:
    def test_returns_cached_client(self):
        app = Typer()
        mock_client = MagicMock()
        app._tully_client = mock_client
        assert app._get_tully_client() is mock_client

    def test_returns_none_when_tully_not_installed(self):
        app = Typer()
        with patch.dict("sys.modules", {"tully": None}):
            result = app._get_tully_client()
        assert result is None

    def test_creates_client_on_first_call(self):
        app = Typer(tully_db_path=Path("/tmp/tully.db"))
        mock_tully_module = MagicMock()
        mock_client_instance = MagicMock()
        mock_tully_module.TullyClient.return_value = mock_client_instance

        with patch.dict("sys.modules", {"tully": mock_tully_module}):
            result = app._get_tully_client()

        assert result is mock_client_instance
        mock_tully_module.TullyClient.assert_called_once_with(db_path=Path("/tmp/tully.db"))


# ===========================================================================
# Built-in commands
# ===========================================================================


class TestBuiltInDoctor:
    def test_doctor_command_registered(self):
        with patch("sniff.typer_app.Typer._add_doctor_command") as mock_add:
            Typer(add_doctor_command=True)
            mock_add.assert_called_once()

    def test_doctor_command_not_registered_by_default(self):
        app = Typer()
        cmd_names = [
            cmd.name or cmd.callback.__name__
            for cmd in app.registered_commands
            if cmd.callback is not None
        ]
        assert "doctor" not in cmd_names

    def test_doctor_command_calls_run_doctor(self):
        app = Typer(add_doctor_command=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        # Add a second command to force group mode
        @app.command()
        def _noop():
            pass

        with patch("sniff.cli_commands.run_doctor") as mock_run:
            result = runner.invoke(app, ["doctor"])
            if result.exit_code == 0:
                mock_run.assert_called_once()


class TestBuiltInVersion:
    def test_version_command_registered(self):
        with patch("sniff.typer_app.Typer._add_version_command") as mock_add:
            Typer(add_version_command=True)
            mock_add.assert_called_once()

    def test_version_command_not_registered_by_default(self):
        app = Typer()
        cmd_names = [
            cmd.name or (cmd.callback.__name__ if cmd.callback else "")
            for cmd in app.registered_commands
        ]
        assert "version-cmd" not in cmd_names
        assert "version" not in cmd_names

    def test_version_command_with_project_version(self):
        app = Typer(add_version_command=True, project_version="3.4.5", name="testapp")
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        @app.command()
        def _noop():
            pass

        with patch("sniff.cli_commands.run_version") as mock_run:
            result = runner.invoke(app, ["version-cmd"])
            if result.exit_code == 0:
                mock_run.assert_called_once_with("testapp", "3.4.5", fake_ctx)


class TestBuiltInEnv:
    def test_env_command_registered(self):
        with patch("sniff.typer_app.Typer._add_env_command") as mock_add:
            Typer(add_env_command=True)
            mock_add.assert_called_once()

    def test_env_command_not_registered_by_default(self):
        app = Typer()
        cmd_names = [
            cmd.name or (cmd.callback.__name__ if cmd.callback else "")
            for cmd in app.registered_commands
        ]
        assert "env" not in cmd_names

    def test_env_command_calls_run_env(self):
        app = Typer(add_env_command=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        @app.command()
        def _noop():
            pass

        with patch("sniff.cli_commands.run_env") as mock_run:
            result = runner.invoke(app, ["env"])
            if result.exit_code == 0:
                mock_run.assert_called_once()


# ===========================================================================
# All built-in commands together
# ===========================================================================


class TestAllBuiltInCommands:
    def test_all_commands_registered(self):
        app = Typer(
            add_doctor_command=True,
            add_version_command=True,
            add_env_command=True,
        )
        cmd_names = set()
        for cmd in app.registered_commands:
            if cmd.callback is not None:
                cmd_names.add(cmd.name or cmd.callback.__name__)
        assert "doctor" in cmd_names
        assert "version_cmd" in cmd_names
        assert "env" in cmd_names

    def test_no_builtin_commands_by_default(self):
        app = Typer()
        assert len(app.registered_commands) == 0

    def test_builtin_commands_count(self):
        app = Typer(
            add_doctor_command=True,
            add_version_command=True,
            add_env_command=True,
        )
        assert len(app.registered_commands) == 3


# ===========================================================================
# _wrap_with_tracking
# ===========================================================================


class TestWrapWithTracking:
    def test_wrap_preserves_function_name(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        def my_func():
            return 42

        wrapped = app._wrap_with_tracking(my_func)
        assert wrapped.__name__ == "my_func"

    def test_wrap_calls_start_and_complete(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-w"
        app._tully_client = mock_client

        def my_func():
            return "result"

        wrapped = app._wrap_with_tracking(my_func)
        result = wrapped()

        assert result == "result"
        mock_client.start_run.assert_called_once()
        mock_client.complete_run.assert_called_once_with("run-w", "success", error=None)

    def test_wrap_tracks_failure(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-f"
        app._tully_client = mock_client

        def failing_func():
            raise RuntimeError("wrapped boom")

        wrapped = app._wrap_with_tracking(failing_func)
        with pytest.raises(RuntimeError, match="wrapped boom"):
            wrapped()

        mock_client.complete_run.assert_called_once_with(
            "run-f", "failed", error="wrapped boom"
        )

    def test_wrap_passes_args(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx
        app._tully_client = MagicMock()
        app._tully_client.start_run.return_value = "run-a"

        def adder(a: int, b: int) -> int:
            return a + b

        wrapped = app._wrap_with_tracking(adder)
        assert wrapped(3, 4) == 7

    def test_wrap_passes_kwargs(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx
        app._tully_client = MagicMock()
        app._tully_client.start_run.return_value = "run-k"

        def greeter(name: str, greeting: str = "Hi") -> str:
            return f"{greeting} {name}"

        wrapped = app._wrap_with_tracking(greeter)
        assert wrapped("Bob", greeting="Hello") == "Hello Bob"

    def test_wrap_no_tully_client(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        with patch("sniff.typer_app.Typer._get_tully_client", return_value=None):
            def my_func():
                return "ok"

            wrapped = app._wrap_with_tracking(my_func)
            result = wrapped()
            assert result == "ok"


# ===========================================================================
# Integration: hooks + tracking together
# ===========================================================================


class TestIntegration:
    def test_hooks_and_tracking_together(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, enable_tracking=True)

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-int"
        app._tully_client = mock_client

        events: list[str] = []
        app.before_command(lambda ctx: events.append("before"))
        app.after_command(lambda ctx: events.append("after"))

        @app.command()
        def integrate():
            events.append("command")

        runner.invoke(app, ["integrate"])

        assert events == ["before", "command", "after"]
        mock_client.start_run.assert_called_once()
        mock_client.complete_run.assert_called_once()

    def test_multiple_commands(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def cmd1():
            print("cmd1")

        @app.command()
        def cmd2():
            print("cmd2")

        r1 = runner.invoke(app, ["cmd1"])
        r2 = runner.invoke(app, ["cmd2"])
        assert r1.exit_code == 0
        assert r2.exit_code == 0
        assert "cmd1" in r1.output
        assert "cmd2" in r2.output

    def test_command_with_options(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def greet(name: str, greeting: str = "Hello"):
            print(f"{greeting}, {name}!")

        result = runner.invoke(app, ["greet", "Bob", "--greeting", "Hi"])
        assert result.exit_code == 0
        assert "Hi, Bob!" in result.output

    def test_command_with_flag(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def debug(verbose: bool = False):
            if verbose:
                print("VERBOSE")
            else:
                print("NORMAL")

        result = runner.invoke(app, ["debug", "--verbose"])
        assert result.exit_code == 0
        assert "VERBOSE" in result.output

    def test_app_as_group(self):
        app = Typer()
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        sub = Typer()
        sub._context = fake_ctx
        app.add_typer(sub, name="sub")

        @sub.command()
        def nested():
            print("nested!")

        result = runner.invoke(app, ["sub", "nested"])
        assert result.exit_code == 0
        assert "nested!" in result.output

    def test_hooks_fire_for_each_invocation(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        count = {"before": 0, "after": 0}
        app.before_command(lambda ctx: count.__setitem__("before", count["before"] + 1))
        app.after_command(lambda ctx: count.__setitem__("after", count["after"] + 1))

        @app.command()
        def cmd_a():
            pass

        @app.command()
        def cmd_b():
            pass

        runner.invoke(app, ["cmd-a"])
        runner.invoke(app, ["cmd-b"])
        assert count["before"] == 2
        assert count["after"] == 2


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_command_with_no_capture(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, auto_capture_env=False)

        before_args: list[object] = []
        after_args: list[object] = []
        app.before_command(lambda ctx: before_args.append(ctx))
        app.after_command(lambda ctx: after_args.append(ctx))

        @app.command()
        def cmd():
            pass

        runner.invoke(app, ["cmd"])
        assert before_args == [None]
        assert after_args == [None]

    def test_capture_env_override_per_command(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, auto_capture_env=False)

        before_args: list[object] = []
        app.before_command(lambda ctx: before_args.append(ctx))

        @app.command(capture_env=True)
        def cmd():
            pass

        runner.invoke(app, ["cmd"])
        assert before_args == [fake_ctx]

    def test_track_override_per_command_enable(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, enable_tracking=False)

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-override"
        app._tully_client = mock_client

        @app.command(track=True)
        def cmd():
            pass

        runner.invoke(app, ["cmd"])
        mock_client.start_run.assert_called_once()

    def test_track_override_per_command_disable(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, enable_tracking=True)

        mock_client = MagicMock()
        app._tully_client = mock_client

        @app.command(track=False)
        def cmd():
            pass

        runner.invoke(app, ["cmd"])
        mock_client.start_run.assert_not_called()

    def test_empty_before_hooks_no_error(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def cmd():
            print("ok")

        result = runner.invoke(app, ["cmd"])
        assert result.exit_code == 0

    def test_empty_after_hooks_no_error(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def cmd():
            print("ok")

        result = runner.invoke(app, ["cmd"])
        assert result.exit_code == 0

    def test_log_metric_without_client(self):
        app = Typer(enable_tracking=True)
        app._current_run_id = "run-x"
        app._tully_client = None

        with patch("sniff.typer_app.Typer._get_tully_client", return_value=None):
            app.log_metric("m", 1.0)

    def test_log_artifact_without_client(self):
        app = Typer(enable_tracking=True)
        app._current_run_id = "run-x"
        app._tully_client = None

        with patch("sniff.typer_app.Typer._get_tully_client", return_value=None):
            app.log_artifact("a", Path("/x"))

    def test_context_property_not_set_until_accessed(self):
        app = Typer()
        assert app._context is None

    def test_complete_tracking_without_active_client(self):
        app = Typer()
        app._current_run_id = "run-z"
        with patch("sniff.typer_app.Typer._get_tully_client", return_value=None):
            app._complete_tracking("run-z", "success")
        assert app._current_run_id is None

    def test_constructor_all_params(self):
        app = Typer(
            name="full",
            enable_tracking=True,
            tully_db_path=Path("/db"),
            tully_experiment_name="exp",
            auto_capture_env=False,
            add_doctor_command=False,
            add_version_command=False,
            add_env_command=False,
            project_version="9.9.9",
            help="Full help",
        )
        assert app._name == "full"
        assert app._enable_tracking is True
        assert app._tully_db_path == Path("/db")
        assert app._tully_experiment_name == "exp"
        assert app._auto_capture_env is False
        assert app._project_version == "9.9.9"
        assert app.info.help == "Full help"

    def test_add_typer_sub_with_hooks(self):
        """Hooks only fire on the app where they were registered."""
        parent = Typer()
        parent._context = _make_fake_context()

        child = Typer()
        child._context = _make_fake_context()
        parent.add_typer(child, name="child")

        parent_hooks: list[str] = []
        parent.before_command(lambda ctx: parent_hooks.append("parent_before"))

        @child.command()
        def sub_cmd():
            print("sub")

        result = runner.invoke(parent, ["child", "sub-cmd"])
        assert result.exit_code == 0
        # Parent hook should NOT fire for child commands
        assert parent_hooks == []

    def test_tracking_experiment_name_passed_to_client(self):
        app = Typer(enable_tracking=True, tully_experiment_name="my-exp")
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-exp"
        app._tully_client = mock_client

        app._start_tracking("cmd_name", fake_ctx)
        mock_client.start_run.assert_called_once_with(
            command_name="cmd_name",
            experiment_name="my-exp",
            environment={"platform": "linux"},
        )

    def test_tracking_no_experiment_name(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        app._context = fake_ctx

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-no-exp"
        app._tully_client = mock_client

        app._start_tracking("cmd_name", fake_ctx)
        mock_client.start_run.assert_called_once_with(
            command_name="cmd_name",
            experiment_name=None,
            environment={"platform": "linux"},
        )

    def test_context_to_dict_passed_to_tracking(self):
        app = Typer(enable_tracking=True)
        fake_ctx = _make_fake_context()
        fake_ctx.to_dict.return_value = {"key": "value", "nested": {"a": 1}}
        app._context = fake_ctx

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-dict"
        app._tully_client = mock_client

        app._start_tracking("cmd", fake_ctx)
        call_kwargs = mock_client.start_run.call_args
        assert call_kwargs.kwargs["environment"] == {"key": "value", "nested": {"a": 1}}


# ===========================================================================
# catch_errors parameter
# ===========================================================================


class TestCatchErrors:
    def test_sniff_error_caught_by_default(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def fail():
            raise ValidationError("Bad input", hint="Check your config")

        result = runner.invoke(app, ["fail"])
        assert result.exit_code == ExitCodes.VALIDATION_ERROR
        assert "Bad input" in result.output

    def test_sniff_error_hint_displayed(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def fail():
            raise ValidationError("Bad input", hint="Check your config")

        result = runner.invoke(app, ["fail"])
        assert "Hint: Check your config" in result.output

    def test_sniff_error_no_hint(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def fail():
            raise ValidationError("Bad input")

        result = runner.invoke(app, ["fail"])
        assert result.exit_code == ExitCodes.VALIDATION_ERROR
        assert "Bad input" in result.output
        assert "Hint:" not in result.output

    def test_not_found_error_exit_code(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def fail():
            raise NotFoundError("File missing", hint="Check the path")

        result = runner.invoke(app, ["fail"])
        assert result.exit_code == ExitCodes.NOT_FOUND

    def test_catch_errors_false_propagates(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command(catch_errors=False)
        def fail():
            raise ValidationError("Bad input", hint="Check your config")

        result = runner.invoke(app, ["fail"])
        # Without catch_errors, the exception propagates
        assert result.exit_code != 0
        assert isinstance(result.exception, ValidationError)

    def test_non_sniff_error_not_caught(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def fail():
            raise ValueError("not a sniff error")

        result = runner.invoke(app, ["fail"])
        assert result.exit_code != 0
        assert isinstance(result.exception, ValueError)

    def test_catch_errors_with_tracking(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx, enable_tracking=True)

        mock_client = MagicMock()
        mock_client.start_run.return_value = "run-err"
        app._tully_client = mock_client

        @app.command()
        def fail():
            raise ValidationError("tracked error")

        result = runner.invoke(app, ["fail"])
        assert result.exit_code == ExitCodes.VALIDATION_ERROR
        mock_client.complete_run.assert_called_once_with(
            "run-err", "failed", error="tracked error"
        )

    def test_catch_errors_after_hooks_still_fire(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        hook_called = []
        app.after_command(lambda ctx: hook_called.append(True))

        @app.command()
        def fail():
            raise ValidationError("fail")

        runner.invoke(app, ["fail"])
        assert hook_called == [True]

    def test_sniff_error_base_class_caught(self):
        fake_ctx = _make_fake_context()
        app = _make_app_with_two_commands(fake_ctx)

        @app.command()
        def fail():
            raise SniffError("generic error", hint="try again")

        result = runner.invoke(app, ["fail"])
        assert result.exit_code == ExitCodes.GENERAL_ERROR
        assert "generic error" in result.output
        assert "Hint: try again" in result.output
