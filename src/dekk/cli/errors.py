"""Structured error handling for dekk CLI applications.

Provides a hierarchy of semantic exceptions with associated exit codes,
user-facing hints, and structured output support (JSON/YAML via to_dict).

Usage::

    from dekk.cli.errors import NotFoundError, ValidationError

    raise NotFoundError(
        "Conda environment 'ml' not found",
        hint="Run 'conda create -n ml' to create it",
        searched_paths=["/opt/conda/envs", "~/.conda/envs"],
    )
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCodes(IntEnum):
    """Standard exit codes for CLI applications.

    Values 0-9 follow Unix conventions extended with domain-specific
    semantics for CLI tooling.
    """

    SUCCESS = 0
    """Command completed successfully."""

    GENERAL_ERROR = 1
    """Unspecified error."""

    VALIDATION_ERROR = 2
    """Input or data validation failed."""

    NOT_FOUND = 3
    """Requested resource was not found."""

    PERMISSION_ERROR = 4
    """Insufficient permissions for the operation."""

    TIMEOUT = 5
    """Operation exceeded its time limit."""

    CONFIG_ERROR = 6
    """Configuration is missing or invalid."""

    DEPENDENCY_ERROR = 7
    """A required dependency is missing or incompatible."""

    RUNTIME_ERROR = 8
    """An error occurred during execution."""

    INTERRUPTED = 9
    """Operation was interrupted by the user or a signal."""


class DekkError(Exception):
    """Base exception for dekk CLI errors.

    All dekk exceptions carry:
    - An ``exit_code`` that maps to a process exit status.
    - An optional ``hint`` with actionable remediation advice.
    - Arbitrary ``details`` that are included in structured output.

    Subclasses set ``exit_code`` as a class variable so callers can
    catch a specific category and still retrieve the correct code.

    Example::

        try:
            do_something()
        except DekkError as exc:
            print_error(exc.message)
            if exc.hint:
                print_info(f"Hint: {exc.hint}")
            raise SystemExit(exc.exit_code)
    """

    exit_code: ExitCodes = ExitCodes.GENERAL_ERROR

    def __init__(self, message: str, hint: str | None = None, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary suitable for JSON/YAML serialization.

        Returns a flat dictionary containing the error class name,
        message, hint, exit code, and any additional details passed
        at construction time.
        """
        result: dict[str, Any] = {
            "error": self.__class__.__name__,
            "message": self.message,
            "hint": self.hint,
            "exit_code": int(self.exit_code),
        }
        result.update(self.details)
        return result


class NotFoundError(DekkError):
    """Raised when a requested resource cannot be located.

    Examples: missing conda environment, file not on disk, unknown
    command name, registry entry absent.
    """

    exit_code = ExitCodes.NOT_FOUND


class ValidationError(DekkError):
    """Raised when input data or configuration fails validation.

    Examples: malformed TOML, schema mismatch, invalid argument
    combination, out-of-range value.
    """

    exit_code = ExitCodes.VALIDATION_ERROR


class ConfigError(DekkError):
    """Raised when configuration is missing, unreadable, or invalid.

    Examples: config file not found, required key absent, conflicting
    settings across tiers.
    """

    exit_code = ExitCodes.CONFIG_ERROR


class DependencyError(DekkError):
    """Raised when a required dependency is missing or incompatible.

    Examples: package not installed, version too old, shared library
    not found, compiler unavailable.
    """

    exit_code = ExitCodes.DEPENDENCY_ERROR


class TimeoutError(DekkError):
    """Raised when an operation exceeds its time limit.

    Examples: network request timeout, build step exceeded deadline,
    subprocess did not finish in time.
    """

    exit_code = ExitCodes.TIMEOUT


class PermissionError(DekkError):
    """Raised when the process lacks permissions for an operation.

    Examples: cannot write to directory, insufficient filesystem
    permissions, access denied by policy.
    """

    exit_code = ExitCodes.PERMISSION_ERROR


class RuntimeError(DekkError):
    """Raised for errors that occur during command execution.

    A catch-all for execution failures that do not fit a more
    specific category.

    Examples: subprocess returned non-zero, assertion failed during
    a build step, unexpected state encountered.
    """

    exit_code = ExitCodes.RUNTIME_ERROR
