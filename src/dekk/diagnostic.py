"""Diagnostic framework - extensible health checks with pluggable formatters.

Provides a protocol-based diagnostic system where consumers register checks
and dekk runs them, collects results, and formats reports. dekk ships
built-in checks for platform, dependencies, and CI; consumers add their own.
"""

from __future__ import annotations

import enum
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class CheckStatus(enum.Enum):
    """Outcome of a single diagnostic check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class CheckResult:
    """Result of running one diagnostic check."""

    name: str
    status: CheckStatus
    summary: str = ""
    details: dict[str, str] = field(default_factory=dict)
    fix_hint: str | None = None
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        """True unless the check failed."""
        return self.status is not CheckStatus.FAIL


@dataclass(frozen=True)
class DiagnosticReport:
    """Aggregated results from a diagnostic run."""

    results: tuple[CheckResult, ...]
    elapsed_ms: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status is CheckStatus.PASS)

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.status is CheckStatus.WARN)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status is CheckStatus.FAIL)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status is CheckStatus.SKIP)

    @property
    def ok(self) -> bool:
        """True if no checks failed."""
        return self.failed == 0


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DiagnosticCheck(Protocol):
    """Protocol for a single diagnostic check.

    Consumers implement this to add custom health checks.  Each implementation
    is a self-contained check that knows its *name*, *category*, and how to
    *run* itself.
    """

    @property
    def name(self) -> str:
        """Short machine-friendly identifier (e.g. ``'python-version'``)."""
        ...

    @property
    def category(self) -> str:
        """Grouping key (e.g. ``'platform'``, ``'deps'``, ``'ci'``)."""
        ...

    @property
    def description(self) -> str:
        """One-line human description of what this check verifies."""
        ...

    def run(self) -> CheckResult:
        """Execute the check and return a result.  Must never raise."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class CheckRegistry:
    """Central registry for diagnostic checks."""

    def __init__(self) -> None:
        self._checks: list[DiagnosticCheck] = []

    def register(self, check: DiagnosticCheck) -> None:
        """Register a diagnostic check.

        Raises:
            TypeError: If *check* does not satisfy the DiagnosticCheck protocol.
        """
        if not isinstance(check, DiagnosticCheck):
            raise TypeError(f"{check!r} does not satisfy DiagnosticCheck protocol")
        self._checks.append(check)

    def checks(self) -> list[DiagnosticCheck]:
        """Return all registered checks (insertion order)."""
        return list(self._checks)

    def by_category(self, category: str) -> list[DiagnosticCheck]:
        """Return checks matching *category*."""
        return [c for c in self._checks if c.category == category]

    def categories(self) -> list[str]:
        """Return unique categories in insertion order."""
        seen: dict[str, None] = {}
        for c in self._checks:
            seen.setdefault(c.category, None)
        return list(seen)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class DiagnosticRunner:
    """Run diagnostic checks and produce reports."""

    def __init__(self, registry: CheckRegistry | None = None) -> None:
        self._registry = registry or CheckRegistry()

    @property
    def registry(self) -> CheckRegistry:
        return self._registry

    def register(self, check: DiagnosticCheck) -> None:
        """Convenience: delegate to the underlying registry."""
        self._registry.register(check)

    def run_all(self) -> DiagnosticReport:
        """Run every registered check and return a report."""
        return self._run(self._registry.checks())

    def run_category(self, category: str) -> DiagnosticReport:
        """Run checks in a single category."""
        return self._run(self._registry.by_category(category))

    def _run(self, checks: Sequence[DiagnosticCheck]) -> DiagnosticReport:
        results: list[CheckResult] = []
        t0 = time.monotonic()
        for check in checks:
            start = time.monotonic()
            try:
                result = check.run()
            except Exception as exc:
                result = CheckResult(
                    name=check.name,
                    status=CheckStatus.FAIL,
                    summary=f"Check raised: {exc}",
                )
            elapsed = (time.monotonic() - start) * 1000
            # Attach timing if the check didn't set it
            if result.elapsed_ms == 0.0:
                result = CheckResult(
                    name=result.name,
                    status=result.status,
                    summary=result.summary,
                    details=result.details,
                    fix_hint=result.fix_hint,
                    elapsed_ms=elapsed,
                )
            results.append(result)
        total = (time.monotonic() - t0) * 1000
        return DiagnosticReport(results=tuple(results), elapsed_ms=total)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

_STATUS_SYMBOLS = {
    CheckStatus.PASS: "[PASS]",
    CheckStatus.WARN: "[WARN]",
    CheckStatus.FAIL: "[FAIL]",
    CheckStatus.SKIP: "[SKIP]",
}


class TextFormatter:
    """Render a DiagnosticReport as plain text."""

    def format(self, report: DiagnosticReport) -> str:
        lines: list[str] = []
        for r in report.results:
            sym = _STATUS_SYMBOLS[r.status]
            lines.append(f"  {sym} {r.name}: {r.summary}")
            if r.fix_hint:
                lines.append(f"         hint: {r.fix_hint}")
        lines.append("")
        lines.append(
            f"  {report.passed} passed, {report.warned} warned, "
            f"{report.failed} failed, {report.skipped} skipped "
            f"({report.elapsed_ms:.0f}ms)"
        )
        return "\n".join(lines)


class JsonFormatter:
    """Render a DiagnosticReport as JSON."""

    def format(self, report: DiagnosticReport) -> str:
        data = {
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "summary": r.summary,
                    "details": r.details,
                    "fix_hint": r.fix_hint,
                    "elapsed_ms": round(r.elapsed_ms, 2),
                }
                for r in report.results
            ],
            "summary": {
                "passed": report.passed,
                "warned": report.warned,
                "failed": report.failed,
                "skipped": report.skipped,
                "elapsed_ms": round(report.elapsed_ms, 2),
            },
        }
        return json.dumps(data, indent=2)


class MarkdownFormatter:
    """Render a DiagnosticReport as Markdown."""

    _STATUS_EMOJI = {
        CheckStatus.PASS: "PASS",
        CheckStatus.WARN: "WARN",
        CheckStatus.FAIL: "FAIL",
        CheckStatus.SKIP: "SKIP",
    }

    def format(self, report: DiagnosticReport) -> str:
        lines: list[str] = ["# Diagnostic Report", ""]
        lines.append("| Status | Check | Summary |")
        lines.append("|--------|-------|---------|")
        for r in report.results:
            status = self._STATUS_EMOJI[r.status]
            lines.append(f"| {status} | {r.name} | {r.summary} |")
        lines.append("")
        lines.append(
            f"**{report.passed}** passed, **{report.warned}** warned, "
            f"**{report.failed}** failed, **{report.skipped}** skipped "
            f"({report.elapsed_ms:.0f}ms)"
        )
        return "\n".join(lines)
