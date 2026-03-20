"""Focused tests for the diagnostic framework and built-in checks."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dekk.deps import DependencyResult, DependencySpec
from dekk.diagnostic import (
    CheckRegistry,
    CheckResult,
    CheckStatus,
    DiagnosticReport,
    DiagnosticRunner,
    JsonFormatter,
    MarkdownFormatter,
    TextFormatter,
)
from dekk.diagnostic_checks import CIEnvironmentCheck, DependencyCheck, PlatformCheck
from dekk.remediate import (
    DetectedIssue,
    FixResult,
    FixStatus,
    IssueSeverity,
    RemediatorRegistry,
)


class AlwaysPassCheck:
    name = "always-pass"
    category = "test"
    description = "pass"

    def run(self) -> CheckResult:
        return CheckResult(name=self.name, status=CheckStatus.PASS, summary="ok")


class AlwaysFailCheck:
    name = "always-fail"
    category = "test"
    description = "fail"

    def run(self) -> CheckResult:
        return CheckResult(
            name=self.name,
            status=CheckStatus.FAIL,
            summary="broken",
            fix_hint="repair it",
        )


class AlwaysWarnCheck:
    name = "always-warn"
    category = "quality"
    description = "warn"

    def run(self) -> CheckResult:
        return CheckResult(name=self.name, status=CheckStatus.WARN, summary="suboptimal")


class AlwaysSkipCheck:
    name = "always-skip"
    category = "optional"
    description = "skip"

    def run(self) -> CheckResult:
        return CheckResult(name=self.name, status=CheckStatus.SKIP, summary="n/a")


class ExplodingCheck:
    name = "exploding"
    category = "test"
    description = "boom"

    def run(self) -> CheckResult:
        raise RuntimeError("kaboom")


class SlowCheck:
    name = "slow-check"
    category = "perf"
    description = "slow"

    def run(self) -> CheckResult:
        return CheckResult(
            name=self.name,
            status=CheckStatus.PASS,
            summary="timed",
            elapsed_ms=42.5,
        )


class FakeRemediator:
    def __init__(self, name: str, categories: set[str] | None = None):
        self._name = name
        self._categories = categories or {"dependency"}

    @property
    def name(self) -> str:
        return self._name

    def can_fix(self, issue: DetectedIssue) -> bool:
        return issue.category in self._categories

    def fix(self, issue: DetectedIssue, dry_run: bool = False) -> FixResult:
        if dry_run:
            return FixResult(FixStatus.SKIPPED, f"Would fix {issue.message}")
        return FixResult(FixStatus.FIXED, f"Fixed {issue.message}")


@pytest.mark.parametrize(
    ("status", "expected_ok"),
    [
        (CheckStatus.PASS, True),
        (CheckStatus.WARN, True),
        (CheckStatus.SKIP, True),
        (CheckStatus.FAIL, False),
    ],
)
def test_check_result_ok_matches_failure_only(status, expected_ok):
    result = CheckResult(name="demo", status=status, summary="summary")
    assert result.ok is expected_ok


def test_check_result_is_frozen_and_defaults_are_stable():
    result = CheckResult(name="demo", status=CheckStatus.PASS)
    assert result.details == {}
    assert result.fix_hint is None
    assert result.elapsed_ms == 0.0
    with pytest.raises((AttributeError, FrozenInstanceError)):
        result.name = "other"


def test_diagnostic_report_aggregates_status_counts():
    report = DiagnosticReport(
        results=(
            CheckResult("a", CheckStatus.PASS, "ok"),
            CheckResult("b", CheckStatus.WARN, "meh"),
            CheckResult("c", CheckStatus.FAIL, "bad"),
            CheckResult("d", CheckStatus.SKIP, "n/a"),
        ),
        elapsed_ms=100.0,
    )

    assert report.passed == 1
    assert report.warned == 1
    assert report.failed == 1
    assert report.skipped == 1
    assert report.ok is False


def test_diagnostic_report_empty_is_ok():
    report = DiagnosticReport(results=(), elapsed_ms=0.0)
    assert report.ok is True
    assert report.passed == 0


def test_check_registry_preserves_order_and_categories():
    registry = CheckRegistry()
    registry.register(AlwaysPassCheck())
    registry.register(AlwaysWarnCheck())
    registry.register(AlwaysFailCheck())

    assert [check.name for check in registry.checks()] == [
        "always-pass",
        "always-warn",
        "always-fail",
    ]
    assert [check.name for check in registry.by_category("test")] == [
        "always-pass",
        "always-fail",
    ]
    assert registry.categories() == ["test", "quality"]


def test_check_registry_returns_copy_and_rejects_invalid_objects():
    registry = CheckRegistry()
    registry.register(AlwaysPassCheck())
    snapshot = registry.checks()
    snapshot.clear()
    assert len(registry.checks()) == 1

    with pytest.raises(TypeError, match="does not satisfy"):
        registry.register("not-a-check")  # type: ignore[arg-type]


def test_diagnostic_runner_preserves_order_and_timing():
    runner = DiagnosticRunner()
    runner.register(AlwaysSkipCheck())
    runner.register(SlowCheck())
    report = runner.run_all()

    assert [result.name for result in report.results] == ["always-skip", "slow-check"]
    assert report.results[0].elapsed_ms > 0.0
    assert report.results[1].elapsed_ms == 42.5
    assert report.elapsed_ms > 0.0


def test_diagnostic_runner_catches_exceptions_without_aborting():
    runner = DiagnosticRunner()
    runner.register(ExplodingCheck())
    runner.register(AlwaysPassCheck())

    report = runner.run_all()

    assert report.failed == 1
    assert report.passed == 1
    assert "kaboom" in report.results[0].summary


def test_diagnostic_runner_filters_by_category():
    runner = DiagnosticRunner()
    runner.register(AlwaysPassCheck())
    runner.register(AlwaysWarnCheck())
    runner.register(AlwaysFailCheck())

    report = runner.run_category("test")
    assert [result.name for result in report.results] == ["always-pass", "always-fail"]


def _mixed_report() -> DiagnosticReport:
    return DiagnosticReport(
        results=(
            CheckResult("pass-check", CheckStatus.PASS, "ok"),
            CheckResult("warn-check", CheckStatus.WARN, "meh"),
            CheckResult("fail-check", CheckStatus.FAIL, "bad", fix_hint="repair it"),
            CheckResult("skip-check", CheckStatus.SKIP, "n/a"),
        ),
        elapsed_ms=123.4,
    )


def test_text_formatter_renders_statuses_counts_and_hints():
    output = TextFormatter().format(_mixed_report())

    assert "[PASS]" in output
    assert "[WARN]" in output
    assert "[FAIL]" in output
    assert "[SKIP]" in output
    assert "hint: repair it" in output
    assert "1 passed, 1 warned, 1 failed, 1 skipped" in output


def test_json_formatter_emits_machine_readable_summary():
    payload = json.loads(JsonFormatter().format(_mixed_report()))

    assert {item["status"] for item in payload["results"]} == {"pass", "warn", "fail", "skip"}
    assert payload["summary"] == {
        "passed": 1,
        "warned": 1,
        "failed": 1,
        "skipped": 1,
        "elapsed_ms": 123.4,
    }
    assert payload["results"][2]["fix_hint"] == "repair it"


def test_markdown_formatter_emits_table_and_summary():
    output = MarkdownFormatter().format(_mixed_report())

    assert output.startswith("# Diagnostic Report")
    assert "| Status | Check | Summary |" in output
    assert "| FAIL | fail-check | bad |" in output
    assert "**1** failed" in output


def test_platform_check_reports_detected_platform_details():
    fake_platform = SimpleNamespace(
        os="Linux",
        arch="x86_64",
        distro="Ubuntu",
        distro_version="24.04",
        pkg_manager="apt",
        is_wsl=False,
        is_container=True,
    )

    with patch("dekk.diagnostic_checks.PlatformDetector.detect", return_value=fake_platform):
        result = PlatformCheck().run()

    assert result.status is CheckStatus.PASS
    assert result.summary == "Linux x86_64 (Ubuntu)"
    assert result.details["os"] == "Linux"
    assert result.details["arch"] == "x86_64"
    assert result.details["container"] == "true"


def test_platform_check_reports_detector_failures():
    with patch("dekk.diagnostic_checks.PlatformDetector.detect", side_effect=RuntimeError("boom")):
        result = PlatformCheck().run()

    assert result.status is CheckStatus.FAIL
    assert "Platform detection failed: boom" == result.summary


def test_dependency_check_passes_when_dependency_is_found():
    spec = DependencySpec("Python", "python3")
    dependency = DependencyResult(
        name="Python",
        command="python3",
        found=True,
        version="3.12.1",
    )

    with patch("dekk.diagnostic_checks.DependencyChecker.check", return_value=dependency):
        result = DependencyCheck(spec).run()

    assert result.status is CheckStatus.PASS
    assert result.summary == "Python 3.12.1"
    assert result.details == {"command": "python3", "version": "3.12.1"}


def test_dependency_check_warns_for_old_or_optional_dependencies():
    old_spec = DependencySpec("Python", "python3", min_version="3.12")
    old_dependency = DependencyResult(
        name="Python",
        command="python3",
        found=True,
        version="3.11.9",
        meets_minimum=False,
    )
    missing_optional = DependencyResult(
        name="Fake",
        command="fake",
        found=False,
        required=False,
        error="fake not found",
    )

    with patch("dekk.diagnostic_checks.DependencyChecker.check", return_value=old_dependency):
        old_result = DependencyCheck(old_spec).run()
    with patch("dekk.diagnostic_checks.DependencyChecker.check", return_value=missing_optional):
        optional_result = DependencyCheck(DependencySpec("Fake", "fake", required=False)).run()

    assert old_result.status is CheckStatus.WARN
    assert "3.11.9 < required 3.12" in old_result.summary
    assert optional_result.status is CheckStatus.WARN
    assert optional_result.fix_hint == "Install Fake (fake)"


def test_dependency_check_fails_for_missing_required_or_checker_errors():
    missing_required = DependencyResult(
        name="Git",
        command="git",
        found=False,
        required=True,
        error="git not found",
    )

    with patch("dekk.diagnostic_checks.DependencyChecker.check", return_value=missing_required):
        missing_result = DependencyCheck(DependencySpec("Git", "git")).run()
    with patch("dekk.diagnostic_checks.DependencyChecker.check", side_effect=RuntimeError("boom")):
        error_result = DependencyCheck(DependencySpec("Git", "git")).run()

    assert missing_result.status is CheckStatus.FAIL
    assert missing_result.summary == "Git not found"
    assert error_result.status is CheckStatus.FAIL
    assert error_result.summary == "Dependency check error: boom"


def test_ci_environment_check_skips_outside_ci():
    fake_ci = SimpleNamespace(is_ci=False)

    with patch("dekk.diagnostic_checks.CIDetector.detect", return_value=fake_ci):
        result = CIEnvironmentCheck().run()

    assert result.status is CheckStatus.SKIP
    assert result.summary == "Not running in CI"


def test_ci_environment_check_reports_provider_and_branch():
    fake_ci = SimpleNamespace(
        is_ci=True,
        provider=SimpleNamespace(display_name="GitHub Actions"),
        git=SimpleNamespace(branch="main", commit_short="abc123"),
        runner=SimpleNamespace(runner_os="Linux"),
    )

    with patch("dekk.diagnostic_checks.CIDetector.detect", return_value=fake_ci):
        result = CIEnvironmentCheck().run()

    assert result.status is CheckStatus.PASS
    assert result.summary == "Running on GitHub Actions (branch: main)"
    assert result.details == {
        "provider": "GitHub Actions",
        "branch": "main",
        "commit": "abc123",
        "runner_os": "Linux",
    }


def test_ci_environment_check_reports_detector_failures():
    with patch("dekk.diagnostic_checks.CIDetector.detect", side_effect=RuntimeError("boom")):
        result = CIEnvironmentCheck().run()

    assert result.status is CheckStatus.FAIL
    assert result.summary == "CI detection failed: boom"


def test_remediation_types_are_frozen_and_defaults_are_stable():
    issue = DetectedIssue(
        category="dependency",
        severity=IssueSeverity.ERROR,
        tool_name="cmake",
        message="CMake not found",
    )
    fix = FixResult(FixStatus.PARTIAL, "Installed but needs PATH", ["Update PATH"])

    assert issue.details == {}
    assert fix.manual_steps == ["Update PATH"]
    with pytest.raises((AttributeError, FrozenInstanceError)):
        issue.category = "other"
    with pytest.raises((AttributeError, FrozenInstanceError)):
        fix.status = FixStatus.FAILED


def test_remediator_registry_finds_first_matching_fixer():
    registry = RemediatorRegistry()
    first = FakeRemediator("first", {"dependency"})
    second = FakeRemediator("second", {"dependency"})
    registry.register(first)
    registry.register(second)

    issue = DetectedIssue("dependency", IssueSeverity.ERROR, "cmake", "missing")

    assert registry.find_fixer(issue) is first
    assert registry.fix(issue).status is FixStatus.FIXED


def test_remediator_registry_handles_dry_run_unmatched_and_invalid_fixers():
    registry = RemediatorRegistry()
    registry.register(FakeRemediator("dep-fixer"))

    dependency_issue = DetectedIssue("dependency", IssueSeverity.ERROR, "cmake", "missing")
    config_issue = DetectedIssue("config", IssueSeverity.WARNING, None, "check config")
    results = registry.fix_all([dependency_issue, config_issue], dry_run=True)

    assert results[0][1].status is FixStatus.SKIPPED
    assert results[1][1] is None

    with pytest.raises(TypeError):
        registry.register("not-a-remediator")  # type: ignore[arg-type]
