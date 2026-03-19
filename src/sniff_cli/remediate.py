"""Extension interface for remediation.

sniff-cli provides these types. Consumers implement them.
sniff-cli itself never imports or executes any implementation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable


class IssueSeverity(enum.Enum):
    """How severe the detected issue is."""

    INFO = "info"  # Informational, not blocking
    WARNING = "warning"  # Works but suboptimal
    ERROR = "error"  # Blocking, must be fixed


class FixStatus(enum.Enum):
    """Status of a fix attempt."""

    FIXED = "fixed"  # Issue resolved
    PARTIAL = "partial"  # Partially fixed, manual steps required
    SKIPPED = "skipped"  # Skipped (dry run or user choice)
    FAILED = "failed"  # Fix attempt failed


@dataclass(frozen=True)
class DetectedIssue:
    """
    An issue detected during environment scanning.

    This is the bridge between detection (pure sniff-cli) and remediation (consumer code).
    """

    category: str  # e.g., "dependency", "config", "environment"
    severity: IssueSeverity
    tool_name: str | None  # Tool that's missing or misconfigured
    message: str  # Human-readable description
    details: dict[str, str] = field(default_factory=dict)  # Structured metadata


@dataclass(frozen=True)
class FixResult:
    """Result of a fix attempt."""

    status: FixStatus
    message: str  # What happened
    manual_steps: list[str] = field(default_factory=list)  # Steps user must do manually


@runtime_checkable
class Remediator(Protocol):
    """
    Protocol for remediation implementations.

    Consumers implement this to provide install/fix logic.
    """

    @property
    def name(self) -> str:
        """Unique name for this remediator (e.g., 'apxm-conda')."""
        ...

    def can_fix(self, issue: DetectedIssue) -> bool:
        """
        Check if this remediator can fix the given issue.

        This must be pure (no I/O, no side effects).

        Args:
            issue: The detected issue.

        Returns:
            True if this remediator can handle this issue.
        """
        ...

    def fix(self, issue: DetectedIssue, dry_run: bool = False) -> FixResult:
        """
        Attempt to fix the issue.

        Args:
            issue: The issue to fix.
            dry_run: If True, don't actually make changes (report what would happen).

        Returns:
            FixResult describing what happened. Never raises.
        """
        ...


class RemediatorRegistry:
    """Registry for remediators."""

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._remediators: list[Remediator] = []

    def register(self, remediator: Remediator) -> None:
        """
        Register a remediator.

        Args:
            remediator: Remediator instance to register.

        Raises:
            TypeError: If remediator doesn't satisfy the Protocol.
        """
        if not isinstance(remediator, Remediator):
            raise TypeError(f"{remediator} does not satisfy Remediator protocol")
        self._remediators.append(remediator)

    def find_fixer(self, issue: DetectedIssue) -> Remediator | None:
        """
        Find a remediator that can fix this issue.

        Args:
            issue: The issue to fix.

        Returns:
            First remediator that can fix it, or None.
        """
        for remediator in self._remediators:
            if remediator.can_fix(issue):
                return remediator
        return None

    def fix(self, issue: DetectedIssue, dry_run: bool = False) -> FixResult | None:
        """
        Fix an issue using registered remediators.

        Args:
            issue: Issue to fix.
            dry_run: If True, don't make actual changes.

        Returns:
            FixResult if a fixer was found, None otherwise.
        """
        fixer = self.find_fixer(issue)
        if fixer:
            return fixer.fix(issue, dry_run=dry_run)
        return None

    def fix_all(
        self, issues: Sequence[DetectedIssue], dry_run: bool = False
    ) -> list[tuple[DetectedIssue, FixResult | None]]:
        """
        Attempt to fix all issues.

        Args:
            issues: Issues to fix.
            dry_run: If True, don't make actual changes.

        Returns:
            List of (issue, result) tuples.
        """
        results = []
        for issue in issues:
            result = self.fix(issue, dry_run=dry_run)
            results.append((issue, result))
        return results
