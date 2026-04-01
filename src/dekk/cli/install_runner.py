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
        self._steps: list[tuple[str, Callable[[], bool] | str]] = []

    def add(self, label: str, action: Callable[[], bool] | str) -> None:
        """Add a step. *action* is a callable returning bool, or a shell command string."""
        self._steps.append((label, action))

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

        for i, (label, action) in enumerate(self._steps, 1):
            print_step(label, step_num=i, total=total)
            t0 = time.monotonic()

            if isinstance(action, str):
                step_ok = self._run_command(action, label, env=env, cwd=cwd)
            else:
                step_ok = self._run_callable(action, label)

            elapsed = time.monotonic() - t0
            result.steps.append(StepResult(label=label, ok=step_ok, elapsed=elapsed))

            if step_ok:
                suffix = f" ({elapsed:.0f}s)" if elapsed > 5 else ""
                print_success(f"{label}{suffix}")
            else:
                print_error(f"{label} failed")
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
        """Run a shell command with spinner + log capture (no stdout)."""
        from dekk.cli.runner import run_logged

        if self.log_path is None:
            import subprocess

            proc = subprocess.run(
                ["sh", "-c", cmd],
                capture_output=True,
                env=env,
                cwd=cwd,
            )
            return proc.returncode == 0

        rr = run_logged(
            ["sh", "-c", cmd],
            log_path=self.log_path,
            label=label,
            spinner_text=f"{label}...",
            env=env,
            cwd=cwd,
            append=True,
            tail_lines=0,  # never dump tail (agent-friendly)
        )
        return rr.ok

    def _run_callable(self, fn: Callable[[], bool], label: str) -> bool:
        """Run a callable with spinner."""
        from dekk.cli.progress import spinner

        with spinner(f"{label}..."):
            try:
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
) -> list[str]:
    """Prompt user to select optional install components.

    Args:
        components: Available components (objects with ``name``, ``label``,
            ``description``, and ``default`` attributes).
        preselect: Override default selection (e.g. from ``--components`` flag).
        interactive: If False, use defaults or preselect without prompting.
                     Agents/CI should pass ``interactive=False``.

    Returns:
        List of selected component names.
    """
    if preselect is not None:
        return preselect

    if not interactive:
        return [c.name for c in components if c.default]  # type: ignore[attr-defined]

    try:
        import questionary
        import questionary.prompts.common as _qcommon
        from prompt_toolkit.styles import Style as PtStyle
    except ImportError:
        # Fallback: use defaults if questionary not installed
        return [c.name for c in components if c.default]  # type: ignore[attr-defined]

    # Use ✓/○ instead of default ●/○ for clearer checked/unchecked state
    _qcommon.INDICATOR_SELECTED = "\u2713"  # type: ignore[attr-defined]  # ✓
    _qcommon.INDICATOR_UNSELECTED = "\u25cb"  # type: ignore[attr-defined]  # ○

    choices = [
        questionary.Choice(
            title=f"{c.label} — {c.description}",  # type: ignore[attr-defined]
            value=c.name,  # type: ignore[attr-defined]
            checked=c.default,  # type: ignore[attr-defined]
        )
        for c in components
    ]

    component_style = PtStyle(
        [
            ("selected", "fg:#00ff00 bold"),  # green ✓ and text for checked
            ("text", "fg:#808080"),  # dim ○ and text for unchecked
            ("pointer", "fg:#00d7ff bold"),  # cyan pointer
            ("highlighted", "bold"),  # bold current row
        ]
    )

    selected = questionary.checkbox(
        "Select components to install:",
        choices=choices,
        style=component_style,
    ).ask()

    return selected if selected is not None else []
