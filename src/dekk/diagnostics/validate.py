"""Environment validation - run checks and produce reports.

Bridges detection results to the remediation system by producing
DetectedIssue instances for failed checks. Never raises; always
returns results.
"""

from __future__ import annotations

import enum
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from dekk.diagnostics.remediate import DetectedIssue, IssueSeverity


class CheckStatus(enum.Enum):
    """Outcome of a single validation check."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CheckResult:
    """Result of a single validation check."""

    name: str
    status: CheckStatus
    message: str = ""
    category: str = "environment"
    details: dict[str, str] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        """True if the check passed."""
        return self.status is CheckStatus.PASSED

    def to_issue(self) -> DetectedIssue | None:
        """Convert a non-passing result to a DetectedIssue for remediation.

        Returns None for passed or skipped checks.
        """
        if self.status in (CheckStatus.PASSED, CheckStatus.SKIPPED):
            return None
        severity = (
            IssueSeverity.WARNING if self.status is CheckStatus.WARNING else IssueSeverity.ERROR
        )
        return DetectedIssue(
            category=self.category,
            severity=severity,
            tool_name=self.details.get("tool"),
            message=self.message,
            details=self.details,
        )


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate report of all validation checks."""

    results: tuple[CheckResult, ...]
    elapsed_ms: float = 0.0

    @property
    def passed(self) -> int:
        """Number of checks that passed."""
        return sum(1 for r in self.results if r.status is CheckStatus.PASSED)

    @property
    def warnings(self) -> int:
        """Number of checks that produced warnings."""
        return sum(1 for r in self.results if r.status is CheckStatus.WARNING)

    @property
    def failed(self) -> int:
        """Number of checks that failed."""
        return sum(1 for r in self.results if r.status is CheckStatus.FAILED)

    @property
    def skipped(self) -> int:
        """Number of checks that were skipped."""
        return sum(1 for r in self.results if r.status is CheckStatus.SKIPPED)

    @property
    def ok(self) -> bool:
        """True if no checks failed."""
        return self.failed == 0

    def issues(self) -> list[DetectedIssue]:
        """Extract DetectedIssue instances from non-passing results."""
        out: list[DetectedIssue] = []
        for r in self.results:
            issue = r.to_issue()
            if issue is not None:
                out.append(issue)
        return out


# Type alias for a check function: () -> CheckResult
CheckFn = Callable[[], CheckResult]


class EnvironmentValidator:
    """Run environment validation checks and produce reports.

    Provides built-in checks for common scenarios (tool presence, directory
    existence, environment variables) and accepts custom check functions.

    Never raises from check execution; errors are captured as FAILED results.
    """

    def __init__(self) -> None:
        self._checks: list[CheckFn] = []

    def add_check(self, check: CheckFn) -> None:
        """Register a custom check function.

        The function must accept no arguments and return a CheckResult.
        """
        self._checks.append(check)

    def check_tool(
        self,
        command: str,
        *,
        name: str | None = None,
        category: str = "dependency",
    ) -> CheckResult:
        """Check that a CLI tool is available on PATH.

        Returns a PASSED result with the resolved path, or FAILED if not found.
        """
        display = name or command
        t0 = time.monotonic()
        path = shutil.which(command)
        elapsed = (time.monotonic() - t0) * 1000
        if path:
            return CheckResult(
                name=display,
                status=CheckStatus.PASSED,
                message=f"{display} found at {path}",
                category=category,
                details={"tool": command, "path": path},
                elapsed_ms=elapsed,
            )
        return CheckResult(
            name=display,
            status=CheckStatus.FAILED,
            message=f"{display} not found in PATH",
            category=category,
            details={"tool": command},
            elapsed_ms=elapsed,
        )

    def check_directory(
        self,
        path: str | Path,
        *,
        name: str | None = None,
        category: str = "environment",
    ) -> CheckResult:
        """Check that a directory exists.

        Returns PASSED if the directory exists, FAILED otherwise.
        """
        p = Path(path)
        display = name or str(p)
        if p.is_dir():
            return CheckResult(
                name=display,
                status=CheckStatus.PASSED,
                message=f"Directory exists: {p}",
                category=category,
                details={"path": str(p)},
            )
        return CheckResult(
            name=display,
            status=CheckStatus.FAILED,
            message=f"Directory not found: {p}",
            category=category,
            details={"path": str(p)},
        )

    def check_env_var(
        self,
        var: str,
        *,
        name: str | None = None,
        category: str = "environment",
        expected: str | None = None,
    ) -> CheckResult:
        """Check that an environment variable is set.

        If *expected* is provided, also checks that the value matches.
        """
        import os

        display = name or var
        value = os.environ.get(var)
        if value is None:
            return CheckResult(
                name=display,
                status=CheckStatus.FAILED,
                message=f"Environment variable {var} is not set",
                category=category,
                details={"variable": var},
            )
        if expected is not None and value != expected:
            return CheckResult(
                name=display,
                status=CheckStatus.WARNING,
                message=f"{var}={value!r} (expected {expected!r})",
                category=category,
                details={"variable": var, "value": value, "expected": expected},
            )
        return CheckResult(
            name=display,
            status=CheckStatus.PASSED,
            message=f"{var} is set",
            category=category,
            details={"variable": var, "value": value},
        )

    def check_file(
        self,
        path: str | Path,
        *,
        name: str | None = None,
        category: str = "config",
    ) -> CheckResult:
        """Check that a file exists.

        Returns PASSED if the file exists, FAILED otherwise.
        """
        p = Path(path)
        display = name or str(p)
        if p.is_file():
            return CheckResult(
                name=display,
                status=CheckStatus.PASSED,
                message=f"File exists: {p}",
                category=category,
                details={"path": str(p)},
            )
        return CheckResult(
            name=display,
            status=CheckStatus.FAILED,
            message=f"File not found: {p}",
            category=category,
            details={"path": str(p)},
        )

    def run_all(self) -> ValidationReport:
        """Run all registered checks and produce a ValidationReport.

        Individual check failures are captured as FAILED results; exceptions
        from check functions are caught and converted to FAILED results so
        this method never raises.
        """
        results: list[CheckResult] = []
        t0 = time.monotonic()
        for check_fn in self._checks:
            try:
                result = check_fn()
            except Exception as exc:
                result = CheckResult(
                    name=getattr(check_fn, "__name__", "unknown"),
                    status=CheckStatus.FAILED,
                    message=f"Check raised: {exc}",
                )
            results.append(result)
        elapsed = (time.monotonic() - t0) * 1000
        return ValidationReport(results=tuple(results), elapsed_ms=elapsed)

    def run_checks(self, checks: Sequence[CheckFn]) -> ValidationReport:
        """Run an explicit list of check functions and produce a report.

        Like run_all but does not use the registered check list.
        """
        results: list[CheckResult] = []
        t0 = time.monotonic()
        for check_fn in checks:
            try:
                result = check_fn()
            except Exception as exc:
                result = CheckResult(
                    name=getattr(check_fn, "__name__", "unknown"),
                    status=CheckStatus.FAILED,
                    message=f"Check raised: {exc}",
                )
            results.append(result)
        elapsed = (time.monotonic() - t0) * 1000
        return ValidationReport(results=tuple(results), elapsed_ms=elapsed)
