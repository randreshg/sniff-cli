"""Enhanced Typer wrapper with sniff detection and optional Tully tracking.

Provides a drop-in replacement for ``typer.Typer`` that adds:

- Lazy-loaded execution context (platform, conda, CI, workspace)
- Session hooks (before/after each command)
- Optional experiment tracking via Tully
- Built-in doctor/version/env commands

Requires the ``cli`` extra: ``pip install sniff[cli]``
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import typer as base_typer
    from typer import Option, Argument, Exit

    _TYPER_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TYPER_AVAILABLE = False


def _require_typer() -> None:
    """Raise a clear error when typer is not installed."""
    if not _TYPER_AVAILABLE:
        raise ImportError(
            "typer is required for sniff.Typer. "
            "Install it with: pip install sniff[cli]"
        )


class Typer(base_typer.Typer if _TYPER_AVAILABLE else object):  # type: ignore[misc]
    """Enhanced Typer with sniff detection and Tully integration.

    A wrapper around ``typer.Typer`` that adds automatic environment
    detection, optional experiment tracking, and built-in commands.

    Parameters
    ----------
    name:
        Application name (used in version output).
    enable_tracking:
        Enable Tully experiment tracking for all commands.
    tully_db_path:
        Path to the Tully SQLite database.
    tully_experiment_name:
        Experiment name for Tully runs.
    auto_capture_env:
        Automatically capture environment context on first access.
    add_doctor_command:
        Register a built-in ``doctor`` command.
    add_version_command:
        Register a built-in ``version`` command.
    add_env_command:
        Register a built-in ``env`` command.
    project_version:
        Version string shown by the ``version`` command.
    **typer_kwargs:
        Passed through to ``typer.Typer.__init__``.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        enable_tracking: bool = False,
        tully_db_path: Path | None = None,
        tully_experiment_name: str | None = None,
        auto_capture_env: bool = True,
        auto_activate: bool = False,
        fail_fast: bool = True,
        add_doctor_command: bool = False,
        add_version_command: bool = False,
        add_env_command: bool = False,
        project_version: str | None = None,
        **typer_kwargs: Any,
    ) -> None:
        _require_typer()
        super().__init__(**typer_kwargs)

        self._name = name
        self._enable_tracking = enable_tracking
        self._tully_db_path = tully_db_path
        self._tully_experiment_name = tully_experiment_name
        self._auto_capture_env = auto_capture_env
        self._auto_activate = auto_activate
        self._fail_fast = fail_fast
        self._project_version = project_version

        # Lazy-loaded state
        self._context: Any | None = None  # ExecutionContext
        self._tully_client: Any | None = None
        self._current_run_id: str | None = None

        # Session hooks
        self._before_hooks: list[Callable[..., Any]] = []
        self._after_hooks: list[Callable[..., Any]] = []

        # Register auto-activation hook if enabled
        if auto_activate:
            self._before_hooks.append(self._auto_activation_hook)

        # Built-in commands
        if add_doctor_command:
            self._add_doctor_command()
        if add_version_command:
            self._add_version_command()
        if add_env_command:
            self._add_env_command()

    # -- Lazy-loaded properties -----------------------------------------------

    @property
    def context(self) -> Any:
        """Execution context (lazy-loaded on first access)."""
        if self._context is None:
            from sniff.context import ExecutionContext

            self._context = ExecutionContext.capture()
        return self._context

    @property
    def platform(self) -> Any:
        """Shortcut to ``context.platform``."""
        return self.context.platform

    @property
    def conda_env(self) -> Any:
        """Shortcut to ``context.conda_env``."""
        return self.context.conda_env

    @property
    def ci_info(self) -> Any:
        """Shortcut to ``context.ci_info``."""
        return self.context.ci_info

    @property
    def workspace(self) -> Any:
        """Shortcut to ``context.workspace``."""
        return self.context.workspace

    # -- Session hooks --------------------------------------------------------

    def before_command(self, hook: Callable[..., Any]) -> None:
        """Register a hook to run before each command execution."""
        self._before_hooks.append(hook)

    def after_command(self, hook: Callable[..., Any]) -> None:
        """Register a hook to run after each command execution."""
        self._after_hooks.append(hook)

    def _auto_activation_hook(self, ctx: Any) -> None:
        """Auto-activate environment from .sniff.toml before each command."""
        import os
        from sniff.activation import EnvironmentActivator
        from sniff.envspec import find_envspec
        from sniff.cli.errors import NotFoundError, DependencyError
        from sniff.cli.styles import print_error

        # Find .sniff.toml
        spec_file = find_envspec()
        if not spec_file:
            if self._fail_fast:
                raise NotFoundError(
                    "No .sniff.toml found for auto-activation",
                    hint="Run 'sniff init' or set auto_activate=False"
                )
            return

        # Activate and validate
        activator = EnvironmentActivator.from_cwd()
        result = activator.activate()

        # Fail fast if required tools missing
        if result.missing_tools:
            error_msg = f"Missing required dependencies: {', '.join(result.missing_tools)}"
            if self._fail_fast:
                hint = f"Run '{self._name or 'app'} doctor' to diagnose or '{self._name or 'app'} install' to set up"
                raise DependencyError(error_msg, hint=hint)
            else:
                print_error(error_msg)

        # Update environment for current process (this is key!)
        if result.env_vars:
            os.environ.update(result.env_vars)

    # -- Enhanced command decorator -------------------------------------------

    def command(
        self,
        *args: Any,
        track: bool | None = None,
        capture_env: bool | None = None,
        catch_errors: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Enhanced command decorator with optional tracking and error handling.

        Parameters
        ----------
        track:
            Enable Tully tracking for this command.  Defaults to the
            app-level ``enable_tracking`` setting.
        capture_env:
            Capture environment before/after.  Defaults to the app-level
            ``auto_capture_env`` setting.
        catch_errors:
            When ``True`` (the default), automatically catch
            :class:`~sniff.cli.errors.SniffError` exceptions and display
            them with :func:`~sniff.cli.styles.print_error` /
            :func:`~sniff.cli.styles.print_info`, then exit with the
            error's ``exit_code``.  Set to ``False`` to let exceptions
            propagate normally.
        *args, **kwargs:
            Passed through to ``typer.Typer.command()``.
        """
        should_track = track if track is not None else self._enable_tracking
        should_capture = capture_env if capture_env is not None else self._auto_capture_env

        base_decorator = super().command(*args, **kwargs)

        def enhanced_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            def wrapper(*inner_args: Any, **inner_kwargs: Any) -> Any:
                ctx = self.context if should_capture else None

                # Before hooks
                for hook in self._before_hooks:
                    hook(ctx)

                # Start tracking
                run_id: str | None = None
                if should_track:
                    run_id = self._start_tracking(func.__name__, self.context)

                try:
                    result = func(*inner_args, **inner_kwargs)

                    if should_track and run_id:
                        self._complete_tracking(run_id, "success")

                    return result
                except Exception as exc:
                    if should_track and run_id:
                        self._complete_tracking(run_id, "failed", error=str(exc))

                    if catch_errors:
                        from sniff.cli.errors import SniffError

                        if isinstance(exc, SniffError):
                            from sniff.cli.styles import print_error, print_info

                            print_error(exc.message)
                            if exc.hint:
                                print_info(f"Hint: {exc.hint}")
                            raise Exit(exc.exit_code)

                    raise
                finally:
                    after_ctx = self.context if should_capture else None
                    for hook in self._after_hooks:
                        hook(after_ctx)

            return base_decorator(wrapper)

        return enhanced_decorator

    # -- Tracking helpers -----------------------------------------------------

    def log_metric(self, name: str, value: float, step: int | None = None) -> None:
        """Log a metric to Tully (if tracking is enabled and a run is active)."""
        if self._enable_tracking and self._current_run_id:
            client = self._get_tully_client()
            if client is not None:
                client.log_metric(self._current_run_id, name, value, step)

    def log_artifact(self, name: str, path: Path) -> None:
        """Log an artifact to Tully (if tracking is enabled and a run is active)."""
        if self._enable_tracking and self._current_run_id:
            client = self._get_tully_client()
            if client is not None:
                client.log_artifact(self._current_run_id, name, path)

    def _get_tully_client(self) -> Any | None:
        """Get or create the Tully client.  Returns None if tully is unavailable."""
        if self._tully_client is None:
            try:
                from tully import TullyClient  # type: ignore[import-untyped]

                self._tully_client = TullyClient(db_path=self._tully_db_path)
            except ImportError:
                return None
        return self._tully_client

    def _start_tracking(self, command_name: str, context: Any) -> str | None:
        """Start a Tully tracking run.  Returns run_id or None."""
        client = self._get_tully_client()
        if client is None:
            return None

        run_id = client.start_run(
            command_name=command_name,
            experiment_name=self._tully_experiment_name,
            environment=context.to_dict(),
        )
        self._current_run_id = run_id
        return run_id

    def _complete_tracking(
        self, run_id: str, status: str, error: str | None = None
    ) -> None:
        """Complete a Tully tracking run."""
        client = self._get_tully_client()
        if client is not None:
            client.complete_run(run_id, status, error=error)
        self._current_run_id = None

    # -- Built-in commands ----------------------------------------------------

    def _add_doctor_command(self) -> None:
        """Register the built-in ``doctor`` command."""

        @self.command()
        def doctor() -> None:
            """Check system environment and dependencies."""
            from sniff.cli_commands import run_doctor

            run_doctor(self.context)

    def _add_version_command(self) -> None:
        """Register the built-in ``version`` command."""
        app_name = self._name
        version = self._project_version

        @self.command(name="version")
        def version_cmd() -> None:
            """Show version information."""
            from sniff.cli_commands import run_version

            run_version(app_name, version, self.context)

    def _add_env_command(self) -> None:
        """Register the built-in ``env`` command."""

        @self.command()
        def env() -> None:
            """Show environment information."""
            from sniff.cli_commands import run_env

            run_env(self.context)

    # -- Wrap with tracking (standalone helper) -------------------------------

    def _wrap_with_tracking(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a callable so it is automatically tracked via Tully."""

        @functools.wraps(func)
        def tracked(*args: Any, **kwargs: Any) -> Any:
            run_id = self._start_tracking(func.__name__, self.context)
            try:
                result = func(*args, **kwargs)
                if run_id:
                    self._complete_tracking(run_id, "success")
                return result
            except Exception as exc:
                if run_id:
                    self._complete_tracking(run_id, "failed", error=str(exc))
                raise

        return tracked
