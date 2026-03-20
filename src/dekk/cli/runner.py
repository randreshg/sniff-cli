"""Subprocess runner with log capture for LLM/agent-friendly CLI workflows.

Imports of Rich/styles/progress are deferred to first use of run_logged.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "RunResult",
    "run_logged",
]

# Label printed after every logged run so LLMs / agents know where to read.
_BUILD_OUTPUT_LABEL = "Build output ->"

# Default number of trailing log lines shown inline on failure.
_DEFAULT_TAIL_LINES = 30


@dataclass(frozen=True)
class RunResult:
    """Result of a logged subprocess run."""

    returncode: int
    log_path: Path

    @property
    def ok(self) -> bool:
        """True when the subprocess exited with code 0."""
        return self.returncode == 0


def run_logged(
    cmd: Sequence[str],
    *,
    log_path: Path,
    label: str,
    spinner_text: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    tail_lines: int = _DEFAULT_TAIL_LINES,
    append: bool = False,
) -> RunResult:
    """Run *cmd* with a spinner, capturing all output to *log_path*."""
    from dekk.cli.progress import spinner
    from dekk.cli.styles import print_info

    log_path = log_path.resolve()

    write_mode = "a" if append else "w"

    with open(log_path, write_mode, encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"--- {label} ---\n")
        log_file.flush()

        with spinner(spinner_text):
            proc = subprocess.run(
                list(cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=cwd,
                text=True,
                errors="replace",
            )
            log_file.write(proc.stdout or "")

    if proc.returncode != 0:
        print_info(f"{_BUILD_OUTPUT_LABEL} {log_path}")
        if tail_lines > 0:
            _print_tail(log_path, tail_lines)

    return RunResult(returncode=proc.returncode, log_path=log_path)


def _print_tail(log_path: Path, tail_lines: int) -> None:
    """Echo the last *tail_lines* lines of *log_path*."""
    from collections import deque

    from dekk.cli.styles import print_info

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            excerpt = deque(f, maxlen=tail_lines)
    except OSError:
        return

    if excerpt:
        print_info("Last lines of build output:")
        for line in excerpt:
            print_info(line.rstrip("\n"))
