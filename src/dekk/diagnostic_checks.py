"""Built-in diagnostic checks for common environment concerns.

These checks use existing dekk detectors (PlatformDetector, DependencyChecker,
CIDetector) and expose them through the DiagnosticCheck protocol so consumers
can include them in a DiagnosticRunner without writing boilerplate.
"""

from __future__ import annotations

from typing import Final

from dekk.detect import PlatformDetector
from dekk.deps import DependencyChecker, DependencySpec
from dekk.ci import CIDetector
from dekk.diagnostic import CheckResult, CheckStatus


PLATFORM_CHECK_NAME: Final = "platform"
PLATFORM_CHECK_CATEGORY: Final = "platform"
PLATFORM_CHECK_DESCRIPTION: Final = "Detect OS, architecture, and container/WSL status"
DEPENDENCY_CHECK_CATEGORY: Final = "deps"
CI_CHECK_NAME: Final = "ci-environment"
CI_CHECK_CATEGORY: Final = "ci"
CI_CHECK_DESCRIPTION: Final = "Detect CI/CD provider and build metadata"
CI_SKIP_SUMMARY: Final = "Not running in CI"
UNKNOWN_CI_PROVIDER: Final = "Unknown CI"


# ---------------------------------------------------------------------------
# PlatformCheck
# ---------------------------------------------------------------------------


class PlatformCheck:
    """Check that the current platform is detected and report key details."""

    @property
    def name(self) -> str:
        return PLATFORM_CHECK_NAME

    @property
    def category(self) -> str:
        return PLATFORM_CHECK_CATEGORY

    @property
    def description(self) -> str:
        return PLATFORM_CHECK_DESCRIPTION

    def run(self) -> CheckResult:
        try:
            info = PlatformDetector().detect()
        except Exception as exc:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                summary=f"Platform detection failed: {exc}",
            )

        details: dict[str, str] = {
            "os": info.os,
            "arch": info.arch,
        }
        if info.distro:
            details["distro"] = info.distro
        if info.distro_version:
            details["distro_version"] = info.distro_version
        if info.pkg_manager:
            details["pkg_manager"] = info.pkg_manager
        if info.is_wsl:
            details["wsl"] = "true"
        if info.is_container:
            details["container"] = "true"

        summary = f"{info.os} {info.arch}"
        if info.distro:
            summary += f" ({info.distro})"

        return CheckResult(
            name=self.name,
            status=CheckStatus.PASS,
            summary=summary,
            details=details,
        )


# ---------------------------------------------------------------------------
# DependencyCheck
# ---------------------------------------------------------------------------


class DependencyCheck:
    """Check that a CLI dependency is available and meets version requirements.

    Wraps a ``DependencySpec`` and adapts the result to the diagnostic
    framework.
    """

    def __init__(self, spec: DependencySpec, *, timeout: float = 10.0) -> None:
        self._spec = spec
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"dep-{self._spec.command}"

    @property
    def category(self) -> str:
        return DEPENDENCY_CHECK_CATEGORY

    @property
    def description(self) -> str:
        desc = f"{self._spec.name} ({self._spec.command}) is available"
        if self._spec.min_version:
            desc += f" >= {self._spec.min_version}"
        return desc

    def run(self) -> CheckResult:
        try:
            result = DependencyChecker(timeout=self._timeout).check(self._spec)
        except Exception as exc:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                summary=f"Dependency check error: {exc}",
            )

        details: dict[str, str] = {"command": result.command}
        if result.version:
            details["version"] = result.version

        if not result.found:
            status = CheckStatus.FAIL if self._spec.required else CheckStatus.WARN
            return CheckResult(
                name=self.name,
                status=status,
                summary=f"{self._spec.name} not found",
                details=details,
                fix_hint=f"Install {self._spec.name} ({self._spec.command})",
            )

        if not result.meets_minimum:
            return CheckResult(
                name=self.name,
                status=CheckStatus.WARN,
                summary=(
                    f"{self._spec.name} {result.version} "
                    f"< required {self._spec.min_version}"
                ),
                details=details,
                fix_hint=f"Upgrade {self._spec.name} to >= {self._spec.min_version}",
            )

        summary = f"{self._spec.name} {result.version}" if result.version else f"{self._spec.name} found"
        return CheckResult(
            name=self.name,
            status=CheckStatus.PASS,
            summary=summary,
            details=details,
        )


# ---------------------------------------------------------------------------
# CIEnvironmentCheck
# ---------------------------------------------------------------------------


class CIEnvironmentCheck:
    """Detect CI/CD environment and report provider details."""

    @property
    def name(self) -> str:
        return CI_CHECK_NAME

    @property
    def category(self) -> str:
        return CI_CHECK_CATEGORY

    @property
    def description(self) -> str:
        return CI_CHECK_DESCRIPTION

    def run(self) -> CheckResult:
        try:
            info = CIDetector().detect()
        except Exception as exc:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                summary=f"CI detection failed: {exc}",
            )

        if not info.is_ci:
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIP,
                summary=CI_SKIP_SUMMARY,
            )

        details: dict[str, str] = {}
        if info.provider:
            details["provider"] = info.provider.display_name
        if info.git.branch:
            details["branch"] = info.git.branch
        if info.git.commit_short:
            details["commit"] = info.git.commit_short
        if info.runner.runner_os:
            details["runner_os"] = info.runner.runner_os

        provider_name = info.provider.display_name if info.provider else UNKNOWN_CI_PROVIDER
        summary = f"Running on {provider_name}"
        if info.git.branch:
            summary += f" (branch: {info.git.branch})"

        return CheckResult(
            name=self.name,
            status=CheckStatus.PASS,
            summary=summary,
            details=details,
        )
