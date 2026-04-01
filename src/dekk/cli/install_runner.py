"""Reusable multi-step install runner with spinners, log capture, and component selection.

Provides ``InstallRunner`` for orchestrating numbered install steps with
pretty output, and ``select_components`` for interactive component selection.

Key design: agent-friendly output. On failure, only the log FILE PATH
is printed — never the log content. This keeps AI agent context windows
clean. The agent can choose to read the log file if it needs to debug.
Pass ``verbose=True`` for human-interactive mode (shows log tail on error).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "InstallRunner",
    "InstallRunnerResult",
    "StepResult",
    "select_components",
]


@dataclass(frozen=True)
class StepResult:
    """Outcome of a single install step."""

    label: str
    ok: bool
    elapsed: float  # seconds
    error: str | None = None


@dataclass
class InstallRunnerResult:
    """Aggregate result of all install steps."""

    title: str
    steps: list[StepResult] = field(default_factory=list)
    log_path: Path | None = None
    selected_components: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)

    @property
    def failed_step(self) -> int | None:
        for i, s in enumerate(self.steps, 1):
            if not s.ok:
                return i
        return None


class InstallRunner:
    """Orchestrates a multi-step install with pretty output and log capture.

    Usage::

        runner = InstallRunner("My Project Install", log_path=Path(".dekk/install.log"))
        runner.add("Setting up environment", setup_fn)
        runner.add("Building", "cargo build --release")
        runner.add("Installing wrapper", wrap_fn)
        result = runner.run()
    """

    def __init__(self, title: str, log_path: Path | None = None) -> None:
        self.title = title
        self.log_path = log_path
        self._steps: list[tuple[str, Callable[..., bool] | str, bool]] = []

    def add(
        self,
        label: str,
        action: Callable[..., bool] | str,
        *,
        progress: bool = False,
    ) -> None:
        """Add a step.

        Args:
            label: Human-readable step description.
            action: A callable returning bool, or a shell command string.
            progress: If True, the callable receives a ``status_fn(msg)``
                argument that updates the spinner text with sub-status
                messages (e.g. "Solving environment...").
        """
        self._steps.append((label, action, progress))

    def run(
        self,
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        verbose: bool = False,
    ) -> InstallRunnerResult:
        """Run all steps sequentially.

        Args:
            env: Environment variables for shell commands.
            cwd: Working directory for shell commands.
            verbose: If True, print log tail on failure (human mode).
                     If False, only print log path (agent mode, default).
        """
        from dekk.cli.styles import (
            print_blank,
            print_error,
            print_header,
            print_info,
            print_step,
            print_success,
        )

        print_header(self.title)
        result = InstallRunnerResult(title=self.title, log_path=self.log_path)
        total = len(self._steps)

        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text("", encoding="utf-8")

        for i, (label, action, has_progress) in enumerate(self._steps, 1):
            print_step(label, step_num=i, total=total)
            t0 = time.monotonic()

            try:
                if isinstance(action, str):
                    step_ok = self._run_command(action, label, env=env, cwd=cwd)
                else:
                    step_ok = self._run_callable(action, label, progress=has_progress)
            except KeyboardInterrupt:
                elapsed = time.monotonic() - t0
                result.steps.append(
                    StepResult(label=label, ok=False, elapsed=elapsed, error="interrupted")
                )
                print_blank()
                print_error(f"Installation cancelled at step {i}/{total}.")
                return result

            elapsed = time.monotonic() - t0
            result.steps.append(StepResult(label=label, ok=step_ok, elapsed=elapsed))

            if step_ok:
                suffix = f" ({elapsed:.0f}s)" if elapsed > 5 else ""
                print_success(f"Done{suffix}")
            else:
                print_error("Failed")
                if self.log_path:
                    print_info(f"Log: {self.log_path}")
                    if verbose:
                        _print_log_tail(self.log_path, 15)
                print_blank()
                print_error(f"Installation failed at step {i}/{total}.")
                return result

        print_blank()
        print_success("Installation complete!")
        return result

    def _run_command(
        self,
        cmd: str,
        label: str,
        *,
        env: dict[str, str] | None,
        cwd: Path | None,
    ) -> bool:
        """Run a shell command with spinner, streaming last line as sub-status."""
        import subprocess

        from dekk.cli.progress import spinner

        with spinner(f"{label}...") as status:
            proc = subprocess.Popen(
                ["sh", "-c", cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                env=env,
                cwd=cwd,
            )
            try:
                log_file = None
                if self.log_path:
                    log_file = open(  # noqa: SIM115
                        self.log_path, "a", encoding="utf-8", errors="replace",
                    )
                    log_file.write(f"--- {label} ---\n")

                if proc.stdout is not None:
                    for line in proc.stdout:
                        if log_file:
                            log_file.write(line)
                        stripped = line.strip()
                        if stripped:
                            # Truncate long lines for the spinner display
                            display = stripped if len(stripped) <= 60 else stripped[:57] + "..."
                            status.update(f"{display}")

                returncode = proc.wait()
            except BaseException:
                proc.kill()
                proc.wait()
                raise
            finally:
                if log_file:
                    log_file.close()

        return returncode == 0

    def _run_callable(
        self, fn: Callable[..., bool], label: str, *, progress: bool = False
    ) -> bool:
        """Run a callable with spinner.

        When *progress* is True, *fn* is called with a ``status_fn(msg)``
        argument that updates the spinner text with sub-status messages.
        Completed phases are printed as persistent ``✓`` lines.
        """
        from dekk.cli.progress import spinner
        from dekk.cli.styles import _get_console

        console = _get_console()

        with spinner(f"{label}...") as status:
            try:
                if progress:
                    last_phase: str | None = None

                    def update_status(msg: str) -> None:
                        nonlocal last_phase
                        if last_phase is not None:
                            console.print(
                                f"        [green]✓[/] {last_phase}",
                                highlight=False,
                            )
                        last_phase = msg
                        status.update(f"{msg}")

                    return fn(update_status)
                return fn()
            except Exception as e:
                if self.log_path:
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(f"--- {label} ---\n{e}\n")
                return False


def _print_log_tail(log_path: Path, n: int) -> None:
    """Print the last *n* lines of the log file."""
    from collections import deque

    from dekk.cli.styles import print_info

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            excerpt = deque(f, maxlen=n)
    except OSError:
        return

    if excerpt:
        print_info("Last lines of build output:")
        for line in excerpt:
            print_info(line.rstrip("\n"))


def select_components(
    components: Sequence[object],
    *,
    preselect: list[str] | None = None,
    interactive: bool = True,
) -> list[str] | None:
    """Prompt user to select optional install components.

    Args:
        components: Available components (objects with ``name``, ``label``,
            ``description``, and ``default`` attributes).
        preselect: Override default selection (e.g. from ``--components`` flag).
        interactive: If False, use defaults or preselect without prompting.
                     Agents/CI should pass ``interactive=False``.

    Returns:
        List of selected component names, or ``None`` if the user cancelled
        (Escape / Ctrl-C).
    """
    if preselect is not None:
        return preselect

    if not interactive:
        return [c.name for c in components if c.default]  # type: ignore[attr-defined]

    try:
        import questionary
        from prompt_toolkit.keys import Keys
        from prompt_toolkit.styles import Style as PtStyle
    except ImportError:
        # Fallback: use defaults if questionary not installed
        return [c.name for c in components if c.default]  # type: ignore[attr-defined]

    from dekk.cli.styles import PROMPT_TOKENS

    # Pass title as (style, text) tuples so the label text stays default color.
    # When title is a list, questionary uses tokens.extend(choice.title) — bypassing
    # the class:selected override that would color the entire row.
    choices = [
        questionary.Choice(
            title=[("", f"{c.label} — {c.description}")],  # type: ignore[attr-defined]
            value=c.name,  # type: ignore[attr-defined]
            checked=c.default,  # type: ignore[attr-defined]
        )
        for c in components
    ]

    component_style = PtStyle(
        [
            ("selected", PROMPT_TOKENS["selected"]),
            ("text", PROMPT_TOKENS["unselected"]),
            ("pointer", PROMPT_TOKENS["pointer"]),
            ("highlighted", PROMPT_TOKENS["highlighted"]),
        ]
    )

    question = questionary.checkbox(
        "Select components to install:",
        choices=choices,
        style=component_style,
    )

    # Bind Escape to cancel (questionary only binds Ctrl-C by default)
    app_kb = question.application.key_bindings
    if app_kb is not None and hasattr(app_kb, "add"):
        app_kb.add(Keys.Escape, eager=True)(
            lambda event: event.app.exit(result=None)
        )

    # None = user pressed Escape/Ctrl-C → cancel
    result: list[str] | None = question.ask()
    return result
