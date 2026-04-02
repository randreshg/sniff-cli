"""Enhanced Typer wrapper with dekk detection and optional Tully tracking.

Provides a drop-in replacement for ``typer.Typer`` that adds:

- Lazy-loaded execution context (platform, conda, CI, workspace)
- Session hooks (before/after each command)
- Optional experiment tracking via Tully
- Built-in doctor/version/env commands

The base ``pip install dekk`` install includes the CLI stack.

Typer is imported lazily -- this module can be imported without triggering
a typer/click/rich import chain.
"""

from __future__ import annotations

import functools
import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

# Typer is loaded lazily on first use
_typer = None
_TYPER_AVAILABLE: bool | None = None


TYPER_EXPORTS: Final = ("Option", "Argument", "Exit", "Context")
TRACKING_STATUS_SUCCESS: Final = "success"
TRACKING_STATUS_FAILED: Final = "failed"
DEFAULT_APP_NAME: Final = "app"
AUTO_ACTIVATE_SPEC_NAME: Final = ".dekk.toml"
BUILTIN_DOCTOR_COMMAND: Final = "doctor"
BUILTIN_VERSION_COMMAND: Final = "version"
BUILTIN_ENV_COMMAND: Final = "env"


def _get_typer() -> Any:
    """Import typer on first use."""
    global _typer, _TYPER_AVAILABLE
    if _TYPER_AVAILABLE is None:
        try:
            import typer as _t

            _typer = _t
            _TYPER_AVAILABLE = True
        except ImportError:
            _TYPER_AVAILABLE = False
    if not _TYPER_AVAILABLE:
        raise ImportError(
            "typer is required for dekk.Typer. "
            "Install or repair the package with: pip install --upgrade dekk"
        )
    return _typer


# Module-level __getattr__ for lazy Option, Argument, Exit access
def __getattr__(name: str) -> Any:  # noqa: N807
    if name in TYPER_EXPORTS:
        t = _get_typer()
        val = getattr(t, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module 'dekk.cli.typer_app' has no attribute {name!r}")


class Typer:
    """Enhanced Typer with dekk detection and Tully integration.

    Uses composition to wrap ``typer.Typer`` without requiring typer
    to be imported at class definition time.
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
        add_worktree_command: bool = False,
        add_agents_command: bool = False,
        project_version: str | None = None,
        **typer_kwargs: Any,
    ) -> None:
        t = _get_typer()
        self._app = t.Typer(**typer_kwargs)

        self._name = name
        self._enable_tracking = enable_tracking
        self._tully_db_path = tully_db_path
        self._tully_experiment_name = tully_experiment_name
        self._auto_capture_env = auto_capture_env
        self._auto_activate = auto_activate
        self._fail_fast = fail_fast
        self._project_version = project_version

        # Lazy-loaded state
        self._context: Any | None = None
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
        if add_worktree_command:
            self._add_worktree_command()
        if add_agents_command:
            self._add_agents_command()

    # -- Proxy to underlying typer.Typer for compatibility --------------------

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._app(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Proxy attribute access to the underlying typer.Typer instance.
        # This is only called for attributes not found on self via __dict__.
        # Block dunder lookups to avoid infinite recursion, but allow
        # single-underscore attrs (e.g. typer's _add_completion) to proxy.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return getattr(self._app, name)

    # -- Lazy-loaded properties -----------------------------------------------

    @property
    def context(self) -> Any:
        """Execution context (lazy-loaded on first access)."""
        if self._context is None:
            from dekk.core.context import ExecutionContext

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
        """Auto-activate environment from .dekk.toml before each command."""
        import os

        from dekk.cli.errors import DependencyError, NotFoundError
        from dekk.cli.styles import print_error
        from dekk.environment.activation import EnvironmentActivator
        from dekk.environment.spec import find_envspec

        spec_file = find_envspec()
        if not spec_file:
            if self._fail_fast:
                raise NotFoundError(
                    f"No {AUTO_ACTIVATE_SPEC_NAME} found for auto-activation",
                    hint="Run 'dekk init' or set auto_activate=False",
                )
            return

        activator = EnvironmentActivator.from_cwd()
        result = activator.activate()

        if result.missing_tools:
            error_msg = f"Missing required dependencies: {', '.join(result.missing_tools)}"
            if self._fail_fast:
                app_name = self._name or DEFAULT_APP_NAME
                hint = (
                    f"Run '{app_name} {BUILTIN_DOCTOR_COMMAND}' to diagnose "
                    f"or '{app_name} install' to set up"
                )
                raise DependencyError(error_msg, hint=hint)
            else:
                print_error(error_msg)

        if result.env_vars:
            from dekk.environment.spec import PREPEND_ENV_VARS

            for key, value in result.env_vars.items():
                if key in PREPEND_ENV_VARS:
                    current = os.environ.get(key, "")
                    os.environ[key] = f"{value}{os.pathsep}{current}" if current else value
                else:
                    os.environ[key] = value

    # -- Enhanced command decorator -------------------------------------------

    def command(
        self,
        *args: Any,
        track: bool | None = None,
        capture_env: bool | None = None,
        catch_errors: bool = True,
        agent_skill: bool = False,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Enhanced command decorator with optional tracking and error handling.

        Args:
            agent_skill: If True, marks this command for agent skill generation.
                When ``dekk agents init`` introspects this app, only commands
                with ``agent_skill=True`` are converted into SKILL.md templates.
        """
        should_track = track if track is not None else self._enable_tracking
        should_capture = capture_env if capture_env is not None else self._auto_capture_env

        base_decorator = self._app.command(*args, **kwargs)

        def enhanced_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if agent_skill:
                func._dekk_agent_skill = True  # type: ignore[attr-defined]

            @functools.wraps(func)
            def wrapper(*inner_args: Any, **inner_kwargs: Any) -> Any:
                ctx = self.context if should_capture else None

                for hook in self._before_hooks:
                    hook(ctx)

                run_id: str | None = None
                if should_track:
                    run_id = self._start_tracking(func.__name__, self.context)

                try:
                    result = func(*inner_args, **inner_kwargs)

                    if should_track and run_id:
                        self._complete_tracking(run_id, TRACKING_STATUS_SUCCESS)

                    return result
                except Exception as exc:
                    if should_track and run_id:
                        self._complete_tracking(run_id, TRACKING_STATUS_FAILED, error=str(exc))

                    if catch_errors:
                        from dekk.cli.errors import DekkError

                        if isinstance(exc, DekkError):
                            from dekk.cli.styles import print_error, print_info

                            print_error(exc.message)
                            if exc.hint:
                                print_info(f"Hint: {exc.hint}")
                            t = _get_typer()
                            raise t.Exit(exc.exit_code) from exc

                    raise
                finally:
                    after_ctx = self.context if should_capture else None
                    for hook in self._after_hooks:
                        hook(after_ctx)

            decorated = cast(Callable[..., Any], base_decorator(wrapper))
            return decorated

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
        """Get or create the Tully client."""
        if self._tully_client is None:
            try:
                tully_module = importlib.import_module("tully")
                TullyClient = tully_module.TullyClient
                self._tully_client = TullyClient(db_path=self._tully_db_path)
            except ImportError:
                return None
        return self._tully_client

    def _start_tracking(self, command_name: str, context: Any) -> str | None:
        """Start a Tully tracking run."""
        client = self._get_tully_client()
        if client is None:
            return None

        run_id = client.start_run(
            command_name=command_name,
            experiment_name=self._tully_experiment_name,
            environment=context.to_dict(),
        )
        run_id_str = str(run_id)
        self._current_run_id = run_id_str
        return run_id_str

    def _complete_tracking(self, run_id: str, status: str, error: str | None = None) -> None:
        """Complete a Tully tracking run."""
        client = self._get_tully_client()
        if client is not None:
            client.complete_run(run_id, status, error=error)
        self._current_run_id = None

    # -- Built-in commands ----------------------------------------------------

    def _add_doctor_command(self) -> None:
        """Register the built-in ``doctor`` command."""

        @self.command(name=BUILTIN_DOCTOR_COMMAND)
        def doctor() -> None:
            """Check system environment and dependencies."""
            from dekk.cli.cli_commands import run_doctor

            run_doctor(self.context)

    def _add_version_command(self) -> None:
        """Register the built-in ``version`` command."""
        app_name = self._name
        version = self._project_version

        @self.command(name=BUILTIN_VERSION_COMMAND)
        def version_cmd() -> None:
            """Show version information."""
            from dekk.cli.cli_commands import run_version

            run_version(app_name, version, self.context)

    def _add_env_command(self) -> None:
        """Register the built-in ``env`` command."""

        @self.command(name=BUILTIN_ENV_COMMAND)
        def env() -> None:
            """Show environment information."""
            from dekk.cli.cli_commands import run_env

            run_env(self.context)

    def _add_worktree_command(self) -> None:
        """Register the built-in ``worktree`` sub-app."""
        from dekk.tools.worktree import create_worktree_app

        self.add_typer(create_worktree_app(), name="worktree")

    def _add_agents_command(self) -> None:
        """Register the built-in ``agents`` sub-app."""
        from dekk.agents import create_agents_app

        self.add_typer(create_agents_app(parent_app=self._app), name="agents")
