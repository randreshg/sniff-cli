"""Tests for the diagnostic framework: runner, registry, formatters, built-in checks, and remediation."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from sniff.diagnostic import (
    CheckRegistry,
    CheckResult,
    CheckStatus,
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticRunner,
    JsonFormatter,
    MarkdownFormatter,
    TextFormatter,
)
from sniff.diagnostic_checks import (
    CIEnvironmentCheck,
    DependencyCheck,
    PlatformCheck,
)
from sniff.deps import DependencySpec
from sniff.remediate import (
    DetectedIssue,
    FixResult,
    FixStatus,
    IssueSeverity,
    Remediator,
    RemediatorRegistry,
)


# =========================================================================
# Helpers - concrete DiagnosticCheck implementations for testing
# =========================================================================


class AlwaysPassCheck:
    """A check that always passes."""

    @property
    def name(self) -> str:
        return "always-pass"

    @property
    def category(self) -> str:
        return "test"

    @property
    def description(self) -> str:
        return "A check that always passes"

    def run(self) -> CheckResult:
        return CheckResult(
            name=self.name,
            status=CheckStatus.PASS,
            summary="Everything is fine",
            details={"key": "value"},
        )


class AlwaysFailCheck:
    """A check that always fails."""

    @property
    def name(self) -> str:
        return "always-fail"

    @property
    def category(self) -> str:
        return "test"

    @property
    def description(self) -> str:
        return "A check that always fails"

    def run(self) -> CheckResult:
        return CheckResult(
            name=self.name,
            status=CheckStatus.FAIL,
            summary="Something is broken",
            fix_hint="Fix it by doing X",
        )


class AlwaysWarnCheck:
    """A check that always warns."""

    @property
    def name(self) -> str:
        return "always-warn"

    @property
    def category(self) -> str:
        return "quality"

    @property
    def description(self) -> str:
        return "A check that always warns"

    def run(self) -> CheckResult:
        return CheckResult(
            name=self.name,
            status=CheckStatus.WARN,
            summary="Suboptimal but works",
        )


class AlwaysSkipCheck:
    """A check that always skips."""

    @property
    def name(self) -> str:
        return "always-skip"

    @property
    def category(self) -> str:
        return "optional"

    @property
    def description(self) -> str:
        return "A check that always skips"

    def run(self) -> CheckResult:
        return CheckResult(
            name=self.name,
            status=CheckStatus.SKIP,
            summary="Not applicable",
        )


class ExplodingCheck:
    """A check that raises an exception."""

    @property
    def name(self) -> str:
        return "exploding"

    @property
    def category(self) -> str:
        return "test"

    @property
    def description(self) -> str:
        return "A check that raises"

    def run(self) -> CheckResult:
        raise RuntimeError("kaboom")


class SlowCheck:
    """A check that reports its own timing."""

    @property
    def name(self) -> str:
        return "slow-check"

    @property
    def category(self) -> str:
        return "perf"

    @property
    def description(self) -> str:
        return "A check with pre-set timing"

    def run(self) -> CheckResult:
        return CheckResult(
            name=self.name,
            status=CheckStatus.PASS,
            summary="Timed check",
            elapsed_ms=42.5,
        )


# =========================================================================
# 1. CheckResult
# =========================================================================


class TestCheckResult:
    """Tests for the CheckResult data type."""

    def test_pass_is_ok(self):
        r = CheckResult(name="t", status=CheckStatus.PASS, summary="ok")
        assert r.ok is True

    def test_warn_is_ok(self):
        r = CheckResult(name="t", status=CheckStatus.WARN, summary="meh")
        assert r.ok is True

    def test_skip_is_ok(self):
        r = CheckResult(name="t", status=CheckStatus.SKIP, summary="n/a")
        assert r.ok is True

    def test_fail_is_not_ok(self):
        r = CheckResult(name="t", status=CheckStatus.FAIL, summary="bad")
        assert r.ok is False

    def test_frozen(self):
        r = CheckResult(name="t", status=CheckStatus.PASS, summary="ok")
        with pytest.raises(AttributeError):
            r.name = "other"  # type: ignore[misc]

    def test_default_details_empty(self):
        r = CheckResult(name="t", status=CheckStatus.PASS)
        assert r.details == {}

    def test_default_fix_hint_none(self):
        r = CheckResult(name="t", status=CheckStatus.PASS)
        assert r.fix_hint is None

    def test_default_elapsed_zero(self):
        r = CheckResult(name="t", status=CheckStatus.PASS)
        assert r.elapsed_ms == 0.0

    def test_details_stored(self):
        r = CheckResult(name="t", status=CheckStatus.PASS, details={"a": "b"})
        assert r.details == {"a": "b"}

    def test_fix_hint_stored(self):
        r = CheckResult(name="t", status=CheckStatus.FAIL, fix_hint="do X")
        assert r.fix_hint == "do X"


# =========================================================================
# 2. DiagnosticReport
# =========================================================================


class TestDiagnosticReport:
    """Tests for the DiagnosticReport data type."""

    def _make_report(self, *statuses: CheckStatus) -> DiagnosticReport:
        results = tuple(
            CheckResult(name=f"check-{i}", status=s, summary=f"s{i}")
            for i, s in enumerate(statuses)
        )
        return DiagnosticReport(results=results, elapsed_ms=100.0)

    def test_all_pass(self):
        report = self._make_report(CheckStatus.PASS, CheckStatus.PASS)
        assert report.passed == 2
        assert report.warned == 0
        assert report.failed == 0
        assert report.skipped == 0
        assert report.ok is True

    def test_mixed_statuses(self):
        report = self._make_report(
            CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL, CheckStatus.SKIP
        )
        assert report.passed == 1
        assert report.warned == 1
        assert report.failed == 1
        assert report.skipped == 1
        assert report.ok is False

    def test_empty_report_is_ok(self):
        report = DiagnosticReport(results=(), elapsed_ms=0.0)
        assert report.ok is True
        assert report.passed == 0

    def test_only_warns_is_ok(self):
        report = self._make_report(CheckStatus.WARN, CheckStatus.WARN)
        assert report.ok is True

    def test_only_skips_is_ok(self):
        report = self._make_report(CheckStatus.SKIP)
        assert report.ok is True

    def test_frozen(self):
        report = DiagnosticReport(results=(), elapsed_ms=0.0)
        with pytest.raises(AttributeError):
            report.elapsed_ms = 50.0  # type: ignore[misc]

    def test_elapsed_ms_stored(self):
        report = DiagnosticReport(results=(), elapsed_ms=123.45)
        assert report.elapsed_ms == 123.45


# =========================================================================
# 3. CheckRegistry
# =========================================================================


class TestCheckRegistry:
    """Tests for the CheckRegistry."""

    def test_register_and_list(self):
        reg = CheckRegistry()
        c = AlwaysPassCheck()
        reg.register(c)
        assert reg.checks() == [c]

    def test_register_multiple(self):
        reg = CheckRegistry()
        c1 = AlwaysPassCheck()
        c2 = AlwaysFailCheck()
        reg.register(c1)
        reg.register(c2)
        assert len(reg.checks()) == 2

    def test_insertion_order_preserved(self):
        reg = CheckRegistry()
        c1 = AlwaysPassCheck()
        c2 = AlwaysFailCheck()
        c3 = AlwaysWarnCheck()
        reg.register(c1)
        reg.register(c2)
        reg.register(c3)
        assert reg.checks() == [c1, c2, c3]

    def test_checks_returns_copy(self):
        reg = CheckRegistry()
        reg.register(AlwaysPassCheck())
        checks = reg.checks()
        checks.clear()
        assert len(reg.checks()) == 1

    def test_by_category(self):
        reg = CheckRegistry()
        reg.register(AlwaysPassCheck())  # category: test
        reg.register(AlwaysFailCheck())  # category: test
        reg.register(AlwaysWarnCheck())  # category: quality
        assert len(reg.by_category("test")) == 2
        assert len(reg.by_category("quality")) == 1
        assert len(reg.by_category("nonexistent")) == 0

    def test_categories(self):
        reg = CheckRegistry()
        reg.register(AlwaysPassCheck())  # test
        reg.register(AlwaysWarnCheck())  # quality
        reg.register(AlwaysFailCheck())  # test
        reg.register(AlwaysSkipCheck())  # optional
        cats = reg.categories()
        assert cats == ["test", "quality", "optional"]

    def test_categories_empty(self):
        reg = CheckRegistry()
        assert reg.categories() == []

    def test_register_invalid_raises_type_error(self):
        reg = CheckRegistry()
        with pytest.raises(TypeError, match="does not satisfy"):
            reg.register("not a check")  # type: ignore[arg-type]

    def test_register_object_missing_method_raises(self):
        class Incomplete:
            @property
            def name(self) -> str:
                return "incomplete"

            @property
            def category(self) -> str:
                return "test"

            # Missing description and run

        reg = CheckRegistry()
        with pytest.raises(TypeError):
            reg.register(Incomplete())  # type: ignore[arg-type]


# =========================================================================
# 4. DiagnosticRunner
# =========================================================================


class TestDiagnosticRunner:
    """Tests for the DiagnosticRunner."""

    def test_run_all_empty(self):
        runner = DiagnosticRunner()
        report = runner.run_all()
        assert report.ok is True
        assert len(report.results) == 0

    def test_run_all_single_pass(self):
        runner = DiagnosticRunner()
        runner.register(AlwaysPassCheck())
        report = runner.run_all()
        assert report.ok is True
        assert report.passed == 1
        assert report.results[0].name == "always-pass"

    def test_run_all_mixed(self):
        runner = DiagnosticRunner()
        runner.register(AlwaysPassCheck())
        runner.register(AlwaysFailCheck())
        runner.register(AlwaysWarnCheck())
        report = runner.run_all()
        assert report.ok is False
        assert report.passed == 1
        assert report.failed == 1
        assert report.warned == 1

    def test_run_category(self):
        runner = DiagnosticRunner()
        runner.register(AlwaysPassCheck())  # test
        runner.register(AlwaysFailCheck())  # test
        runner.register(AlwaysWarnCheck())  # quality
        report = runner.run_category("test")
        assert len(report.results) == 2
        assert report.passed == 1
        assert report.failed == 1

    def test_run_category_empty(self):
        runner = DiagnosticRunner()
        runner.register(AlwaysPassCheck())
        report = runner.run_category("nonexistent")
        assert len(report.results) == 0

    def test_exploding_check_caught(self):
        runner = DiagnosticRunner()
        runner.register(ExplodingCheck())
        report = runner.run_all()
        assert report.failed == 1
        assert "kaboom" in report.results[0].summary

    def test_timing_attached_automatically(self):
        runner = DiagnosticRunner()
        runner.register(AlwaysPassCheck())
        report = runner.run_all()
        assert report.results[0].elapsed_ms > 0.0
        assert report.elapsed_ms > 0.0

    def test_pre_set_timing_preserved(self):
        runner = DiagnosticRunner()
        runner.register(SlowCheck())
        report = runner.run_all()
        assert report.results[0].elapsed_ms == 42.5

    def test_runner_with_existing_registry(self):
        reg = CheckRegistry()
        reg.register(AlwaysPassCheck())
        runner = DiagnosticRunner(registry=reg)
        assert runner.registry is reg
        report = runner.run_all()
        assert report.passed == 1

    def test_runner_register_delegates(self):
        runner = DiagnosticRunner()
        check = AlwaysPassCheck()
        runner.register(check)
        assert check in runner.registry.checks()

    def test_all_statuses_run(self):
        runner = DiagnosticRunner()
        runner.register(AlwaysPassCheck())
        runner.register(AlwaysFailCheck())
        runner.register(AlwaysWarnCheck())
        runner.register(AlwaysSkipCheck())
        report = runner.run_all()
        assert len(report.results) == 4
        assert report.passed == 1
        assert report.failed == 1
        assert report.warned == 1
        assert report.skipped == 1

    def test_results_preserve_order(self):
        runner = DiagnosticRunner()
        runner.register(AlwaysSkipCheck())
        runner.register(AlwaysPassCheck())
        runner.register(AlwaysFailCheck())
        report = runner.run_all()
        names = [r.name for r in report.results]
        assert names == ["always-skip", "always-pass", "always-fail"]

    def test_multiple_explosions_all_caught(self):
        runner = DiagnosticRunner()
        runner.register(ExplodingCheck())
        runner.register(AlwaysPassCheck())
        runner.register(ExplodingCheck())
        report = runner.run_all()
        assert report.failed == 2
        assert report.passed == 1


# =========================================================================
# 5. TextFormatter
# =========================================================================


class TestTextFormatter:
    """Tests for the TextFormatter."""

    def _make_report(self, *results: CheckResult, elapsed: float = 100.0) -> DiagnosticReport:
        return DiagnosticReport(results=results, elapsed_ms=elapsed)

    def test_pass_format(self):
        report = self._make_report(
            CheckResult(name="test", status=CheckStatus.PASS, summary="OK")
        )
        text = TextFormatter().format(report)
        assert "[PASS]" in text
        assert "test" in text
        assert "OK" in text

    def test_fail_format(self):
        report = self._make_report(
            CheckResult(name="test", status=CheckStatus.FAIL, summary="bad")
        )
        text = TextFormatter().format(report)
        assert "[FAIL]" in text

    def test_warn_format(self):
        report = self._make_report(
            CheckResult(name="test", status=CheckStatus.WARN, summary="meh")
        )
        text = TextFormatter().format(report)
        assert "[WARN]" in text

    def test_skip_format(self):
        report = self._make_report(
            CheckResult(name="test", status=CheckStatus.SKIP, summary="n/a")
        )
        text = TextFormatter().format(report)
        assert "[SKIP]" in text

    def test_fix_hint_shown(self):
        report = self._make_report(
            CheckResult(
                name="test", status=CheckStatus.FAIL,
                summary="bad", fix_hint="run pip install"
            )
        )
        text = TextFormatter().format(report)
        assert "hint:" in text
        assert "run pip install" in text

    def test_no_hint_when_none(self):
        report = self._make_report(
            CheckResult(name="test", status=CheckStatus.PASS, summary="ok")
        )
        text = TextFormatter().format(report)
        assert "hint:" not in text

    def test_summary_line(self):
        report = self._make_report(
            CheckResult(name="a", status=CheckStatus.PASS, summary="ok"),
            CheckResult(name="b", status=CheckStatus.FAIL, summary="bad"),
            elapsed=200.0,
        )
        text = TextFormatter().format(report)
        assert "1 passed" in text
        assert "1 failed" in text
        assert "200ms" in text

    def test_empty_report(self):
        report = DiagnosticReport(results=(), elapsed_ms=0.0)
        text = TextFormatter().format(report)
        assert "0 passed" in text
        assert "0 failed" in text


# =========================================================================
# 6. JsonFormatter
# =========================================================================


class TestJsonFormatter:
    """Tests for the JsonFormatter."""

    def _make_report(self, *results: CheckResult, elapsed: float = 100.0) -> DiagnosticReport:
        return DiagnosticReport(results=results, elapsed_ms=elapsed)

    def test_valid_json(self):
        report = self._make_report(
            CheckResult(name="test", status=CheckStatus.PASS, summary="ok")
        )
        text = JsonFormatter().format(report)
        data = json.loads(text)
        assert "results" in data
        assert "summary" in data

    def test_result_fields(self):
        report = self._make_report(
            CheckResult(
                name="t", status=CheckStatus.FAIL,
                summary="bad", details={"k": "v"},
                fix_hint="do X", elapsed_ms=12.34,
            )
        )
        data = json.loads(JsonFormatter().format(report))
        r = data["results"][0]
        assert r["name"] == "t"
        assert r["status"] == "fail"
        assert r["summary"] == "bad"
        assert r["details"] == {"k": "v"}
        assert r["fix_hint"] == "do X"
        assert r["elapsed_ms"] == 12.34

    def test_summary_counts(self):
        report = self._make_report(
            CheckResult(name="a", status=CheckStatus.PASS, summary="ok"),
            CheckResult(name="b", status=CheckStatus.WARN, summary="meh"),
            CheckResult(name="c", status=CheckStatus.FAIL, summary="bad"),
            CheckResult(name="d", status=CheckStatus.SKIP, summary="n/a"),
            elapsed=50.0,
        )
        data = json.loads(JsonFormatter().format(report))
        s = data["summary"]
        assert s["passed"] == 1
        assert s["warned"] == 1
        assert s["failed"] == 1
        assert s["skipped"] == 1
        assert s["elapsed_ms"] == 50.0

    def test_null_fix_hint(self):
        report = self._make_report(
            CheckResult(name="t", status=CheckStatus.PASS, summary="ok")
        )
        data = json.loads(JsonFormatter().format(report))
        assert data["results"][0]["fix_hint"] is None

    def test_empty_report(self):
        report = DiagnosticReport(results=(), elapsed_ms=0.0)
        data = json.loads(JsonFormatter().format(report))
        assert data["results"] == []
        assert data["summary"]["passed"] == 0


# =========================================================================
# 7. MarkdownFormatter
# =========================================================================


class TestMarkdownFormatter:
    """Tests for the MarkdownFormatter."""

    def _make_report(self, *results: CheckResult, elapsed: float = 100.0) -> DiagnosticReport:
        return DiagnosticReport(results=results, elapsed_ms=elapsed)

    def test_has_header(self):
        report = self._make_report(
            CheckResult(name="t", status=CheckStatus.PASS, summary="ok")
        )
        md = MarkdownFormatter().format(report)
        assert md.startswith("# Diagnostic Report")

    def test_table_header(self):
        report = self._make_report(
            CheckResult(name="t", status=CheckStatus.PASS, summary="ok")
        )
        md = MarkdownFormatter().format(report)
        assert "| Status | Check | Summary |" in md
        assert "|--------|-------|---------|" in md

    def test_result_row(self):
        report = self._make_report(
            CheckResult(name="my-check", status=CheckStatus.PASS, summary="All good")
        )
        md = MarkdownFormatter().format(report)
        assert "| PASS | my-check | All good |" in md

    def test_fail_row(self):
        report = self._make_report(
            CheckResult(name="broken", status=CheckStatus.FAIL, summary="Oops")
        )
        md = MarkdownFormatter().format(report)
        assert "| FAIL | broken | Oops |" in md

    def test_bold_counts(self):
        report = self._make_report(
            CheckResult(name="a", status=CheckStatus.PASS, summary="ok"),
            CheckResult(name="b", status=CheckStatus.FAIL, summary="bad"),
        )
        md = MarkdownFormatter().format(report)
        assert "**1** passed" in md
        assert "**1** failed" in md

    def test_empty_report(self):
        report = DiagnosticReport(results=(), elapsed_ms=0.0)
        md = MarkdownFormatter().format(report)
        assert "# Diagnostic Report" in md
        assert "**0** passed" in md


# =========================================================================
# 8. Built-in Checks: PlatformCheck
# =========================================================================


class TestPlatformCheck:
    """Tests for the PlatformCheck built-in."""

    def test_satisfies_protocol(self):
        check = PlatformCheck()
        assert isinstance(check, DiagnosticCheck)

    def test_name(self):
        assert PlatformCheck().name == "platform"

    def test_category(self):
        assert PlatformCheck().category == "platform"

    def test_description_not_empty(self):
        assert len(PlatformCheck().description) > 0

    def test_run_returns_pass(self):
        result = PlatformCheck().run()
        assert result.status is CheckStatus.PASS
        assert result.name == "platform"

    def test_run_has_os_in_summary(self):
        result = PlatformCheck().run()
        assert platform.system() in result.summary

    def test_run_has_os_detail(self):
        result = PlatformCheck().run()
        assert "os" in result.details
        assert result.details["os"] == platform.system()

    def test_run_has_arch_detail(self):
        result = PlatformCheck().run()
        assert "arch" in result.details

    def test_integrates_with_runner(self):
        runner = DiagnosticRunner()
        runner.register(PlatformCheck())
        report = runner.run_all()
        assert report.ok is True
        assert report.passed == 1


# =========================================================================
# 9. Built-in Checks: DependencyCheck
# =========================================================================


class TestDependencyCheck:
    """Tests for the DependencyCheck built-in."""

    def test_satisfies_protocol(self):
        spec = DependencySpec("Test", "test-cmd")
        check = DependencyCheck(spec)
        assert isinstance(check, DiagnosticCheck)

    def test_name_includes_command(self):
        spec = DependencySpec("Python", "python3")
        check = DependencyCheck(spec)
        assert check.name == "dep-python3"

    def test_category_is_deps(self):
        spec = DependencySpec("Python", "python3")
        check = DependencyCheck(spec)
        assert check.category == "deps"

    def test_description_includes_name(self):
        spec = DependencySpec("Python", "python3")
        check = DependencyCheck(spec)
        assert "Python" in check.description

    def test_description_includes_min_version(self):
        spec = DependencySpec("Python", "python3", min_version="3.11")
        check = DependencyCheck(spec)
        assert "3.11" in check.description

    def test_found_dep_passes(self):
        spec = DependencySpec("Python", "python3")
        result = DependencyCheck(spec).run()
        assert result.status is CheckStatus.PASS
        assert "Python" in result.summary

    def test_found_dep_has_version_detail(self):
        spec = DependencySpec("Python", "python3")
        result = DependencyCheck(spec).run()
        assert "version" in result.details

    def test_missing_required_dep_fails(self):
        spec = DependencySpec("Fake", "definitely-not-real-xyz", required=True)
        result = DependencyCheck(spec).run()
        assert result.status is CheckStatus.FAIL
        assert result.fix_hint is not None

    def test_missing_optional_dep_warns(self):
        spec = DependencySpec("Fake", "definitely-not-real-xyz", required=False)
        result = DependencyCheck(spec).run()
        assert result.status is CheckStatus.WARN

    def test_integrates_with_runner(self):
        runner = DiagnosticRunner()
        runner.register(DependencyCheck(DependencySpec("Python", "python3")))
        runner.register(DependencyCheck(DependencySpec("Fake", "not-real-cmd", required=False)))
        report = runner.run_all()
        assert report.passed >= 1
        assert report.warned >= 1


# =========================================================================
# 10. Built-in Checks: CIEnvironmentCheck
# =========================================================================


@pytest.fixture
def clean_ci_env(monkeypatch):
    """Remove all CI-related environment variables."""
    ci_vars = [
        "CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL", "CIRCLECI",
        "BUILDKITE", "TRAVIS", "TF_BUILD", "AZURE_PIPELINES",
        "BITBUCKET_PIPELINE_UUID", "TEAMCITY_VERSION", "CODEBUILD_BUILD_ID",
        "DRONE", "WOODPECKER_CI", "HEROKU_TEST_RUN_ID",
    ]
    for var in ci_vars:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestCIEnvironmentCheck:
    """Tests for the CIEnvironmentCheck built-in."""

    def test_satisfies_protocol(self):
        check = CIEnvironmentCheck()
        assert isinstance(check, DiagnosticCheck)

    def test_name(self):
        assert CIEnvironmentCheck().name == "ci-environment"

    def test_category(self):
        assert CIEnvironmentCheck().category == "ci"

    def test_description_not_empty(self):
        assert len(CIEnvironmentCheck().description) > 0

    def test_not_ci_skips(self, clean_ci_env):
        result = CIEnvironmentCheck().run()
        assert result.status is CheckStatus.SKIP
        assert "Not running in CI" in result.summary

    def test_github_actions_detected(self, clean_ci_env):
        clean_ci_env.setenv("GITHUB_ACTIONS", "true")
        clean_ci_env.setenv("CI", "true")
        clean_ci_env.setenv("GITHUB_REF", "refs/heads/main")
        clean_ci_env.setenv("GITHUB_SHA", "abc123")
        result = CIEnvironmentCheck().run()
        assert result.status is CheckStatus.PASS
        assert "GitHub Actions" in result.summary

    def test_github_actions_has_provider_detail(self, clean_ci_env):
        clean_ci_env.setenv("GITHUB_ACTIONS", "true")
        clean_ci_env.setenv("CI", "true")
        result = CIEnvironmentCheck().run()
        assert result.details.get("provider") == "GitHub Actions"

    def test_branch_in_details(self, clean_ci_env):
        clean_ci_env.setenv("GITHUB_ACTIONS", "true")
        clean_ci_env.setenv("CI", "true")
        clean_ci_env.setenv("GITHUB_REF", "refs/heads/develop")
        result = CIEnvironmentCheck().run()
        assert result.details.get("branch") == "develop"

    def test_integrates_with_runner(self, clean_ci_env):
        runner = DiagnosticRunner()
        runner.register(CIEnvironmentCheck())
        report = runner.run_all()
        assert len(report.results) == 1
        # Outside CI, should skip (which is still ok)
        assert report.ok is True


# =========================================================================
# 11. DetectedIssue and Remediation
# =========================================================================


class TestDetectedIssue:
    """Tests for DetectedIssue data type."""

    def test_creation(self):
        issue = DetectedIssue(
            category="dependency",
            severity=IssueSeverity.ERROR,
            tool_name="cmake",
            message="CMake not found",
        )
        assert issue.category == "dependency"
        assert issue.severity is IssueSeverity.ERROR
        assert issue.tool_name == "cmake"
        assert issue.message == "CMake not found"

    def test_frozen(self):
        issue = DetectedIssue(
            category="dependency",
            severity=IssueSeverity.ERROR,
            tool_name="cmake",
            message="CMake not found",
        )
        with pytest.raises(AttributeError):
            issue.category = "config"  # type: ignore[misc]

    def test_default_details_empty(self):
        issue = DetectedIssue(
            category="config",
            severity=IssueSeverity.WARNING,
            tool_name=None,
            message="Config suboptimal",
        )
        assert issue.details == {}

    def test_details_stored(self):
        issue = DetectedIssue(
            category="config",
            severity=IssueSeverity.INFO,
            tool_name=None,
            message="Info",
            details={"key": "val"},
        )
        assert issue.details == {"key": "val"}

    def test_severity_values(self):
        assert IssueSeverity.INFO.value == "info"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.ERROR.value == "error"

    def test_tool_name_optional(self):
        issue = DetectedIssue(
            category="environment",
            severity=IssueSeverity.INFO,
            tool_name=None,
            message="All good",
        )
        assert issue.tool_name is None


# =========================================================================
# 12. FixResult
# =========================================================================


class TestFixResult:
    """Tests for FixResult data type."""

    def test_fixed(self):
        r = FixResult(status=FixStatus.FIXED, message="Installed cmake")
        assert r.status is FixStatus.FIXED
        assert r.message == "Installed cmake"
        assert r.manual_steps == []

    def test_partial_with_manual_steps(self):
        r = FixResult(
            status=FixStatus.PARTIAL,
            message="Installed but needs PATH",
            manual_steps=["Add /usr/local/bin to PATH"],
        )
        assert r.status is FixStatus.PARTIAL
        assert len(r.manual_steps) == 1

    def test_skipped(self):
        r = FixResult(status=FixStatus.SKIPPED, message="Dry run")
        assert r.status is FixStatus.SKIPPED

    def test_failed(self):
        r = FixResult(status=FixStatus.FAILED, message="Permission denied")
        assert r.status is FixStatus.FAILED

    def test_frozen(self):
        r = FixResult(status=FixStatus.FIXED, message="done")
        with pytest.raises(AttributeError):
            r.status = FixStatus.FAILED  # type: ignore[misc]

    def test_fix_status_values(self):
        assert FixStatus.FIXED.value == "fixed"
        assert FixStatus.PARTIAL.value == "partial"
        assert FixStatus.SKIPPED.value == "skipped"
        assert FixStatus.FAILED.value == "failed"


# =========================================================================
# 13. RemediatorRegistry
# =========================================================================


class FakeRemediator:
    """A concrete Remediator for testing."""

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
            return FixResult(
                status=FixStatus.SKIPPED,
                message=f"Would fix {issue.message}",
            )
        return FixResult(
            status=FixStatus.FIXED,
            message=f"Fixed {issue.message}",
        )


class TestRemediatorRegistry:
    """Tests for RemediatorRegistry."""

    def test_register_and_find(self):
        reg = RemediatorRegistry()
        fixer = FakeRemediator("dep-fixer")
        reg.register(fixer)

        issue = DetectedIssue(
            category="dependency",
            severity=IssueSeverity.ERROR,
            tool_name="cmake",
            message="cmake not found",
        )
        found = reg.find_fixer(issue)
        assert found is fixer

    def test_find_returns_none_when_no_match(self):
        reg = RemediatorRegistry()
        reg.register(FakeRemediator("dep-fixer", {"dependency"}))

        issue = DetectedIssue(
            category="config",
            severity=IssueSeverity.WARNING,
            tool_name=None,
            message="config issue",
        )
        assert reg.find_fixer(issue) is None

    def test_fix_delegates(self):
        reg = RemediatorRegistry()
        reg.register(FakeRemediator("dep-fixer"))

        issue = DetectedIssue(
            category="dependency",
            severity=IssueSeverity.ERROR,
            tool_name="cmake",
            message="cmake not found",
        )
        result = reg.fix(issue)
        assert result is not None
        assert result.status is FixStatus.FIXED

    def test_fix_returns_none_when_no_fixer(self):
        reg = RemediatorRegistry()
        issue = DetectedIssue(
            category="config",
            severity=IssueSeverity.WARNING,
            tool_name=None,
            message="nope",
        )
        assert reg.fix(issue) is None

    def test_fix_dry_run(self):
        reg = RemediatorRegistry()
        reg.register(FakeRemediator("dep-fixer"))

        issue = DetectedIssue(
            category="dependency",
            severity=IssueSeverity.ERROR,
            tool_name="cmake",
            message="cmake not found",
        )
        result = reg.fix(issue, dry_run=True)
        assert result is not None
        assert result.status is FixStatus.SKIPPED

    def test_fix_all(self):
        reg = RemediatorRegistry()
        reg.register(FakeRemediator("dep-fixer", {"dependency"}))

        issues = [
            DetectedIssue(
                category="dependency",
                severity=IssueSeverity.ERROR,
                tool_name="cmake",
                message="cmake not found",
            ),
            DetectedIssue(
                category="config",
                severity=IssueSeverity.WARNING,
                tool_name=None,
                message="config issue",
            ),
        ]
        results = reg.fix_all(issues)
        assert len(results) == 2
        issue0, result0 = results[0]
        assert result0 is not None
        assert result0.status is FixStatus.FIXED
        issue1, result1 = results[1]
        assert result1 is None

    def test_fix_all_dry_run(self):
        reg = RemediatorRegistry()
        reg.register(FakeRemediator("dep-fixer"))

        issues = [
            DetectedIssue(
                category="dependency",
                severity=IssueSeverity.ERROR,
                tool_name="cmake",
                message="cmake not found",
            ),
        ]
        results = reg.fix_all(issues, dry_run=True)
        _, result = results[0]
        assert result is not None
        assert result.status is FixStatus.SKIPPED

    def test_register_invalid_raises(self):
        reg = RemediatorRegistry()
        with pytest.raises(TypeError):
            reg.register("not a remediator")  # type: ignore[arg-type]

    def test_first_matching_fixer_wins(self):
        reg = RemediatorRegistry()
        fixer1 = FakeRemediator("first", {"dependency"})
        fixer2 = FakeRemediator("second", {"dependency"})
        reg.register(fixer1)
        reg.register(fixer2)

        issue = DetectedIssue(
            category="dependency",
            severity=IssueSeverity.ERROR,
            tool_name="cmake",
            message="cmake not found",
        )
        assert reg.find_fixer(issue) is fixer1


# =========================================================================
# 14. Integration: DiagnosticRunner + Formatters
# =========================================================================


class TestRunnerFormatterIntegration:
    """End-to-end: run checks, format output."""

    def _run_mixed(self) -> DiagnosticReport:
        runner = DiagnosticRunner()
        runner.register(AlwaysPassCheck())
        runner.register(AlwaysFailCheck())
        runner.register(AlwaysWarnCheck())
        runner.register(AlwaysSkipCheck())
        return runner.run_all()

    def test_text_roundtrip(self):
        report = self._run_mixed()
        text = TextFormatter().format(report)
        assert "[PASS]" in text
        assert "[FAIL]" in text
        assert "[WARN]" in text
        assert "[SKIP]" in text
        assert "1 passed" in text
        assert "1 failed" in text
        assert "1 warned" in text
        assert "1 skipped" in text

    def test_json_roundtrip(self):
        report = self._run_mixed()
        text = JsonFormatter().format(report)
        data = json.loads(text)
        assert len(data["results"]) == 4
        statuses = {r["status"] for r in data["results"]}
        assert statuses == {"pass", "fail", "warn", "skip"}

    def test_markdown_roundtrip(self):
        report = self._run_mixed()
        md = MarkdownFormatter().format(report)
        assert "| PASS |" in md
        assert "| FAIL |" in md
        assert "| WARN |" in md
        assert "| SKIP |" in md


# =========================================================================
# 15. Integration: Diagnostic -> DetectedIssue bridge
# =========================================================================


class TestDiagnosticToRemediationBridge:
    """Test converting CheckResult failures into DetectedIssue instances."""

    def test_failed_check_becomes_issue(self):
        """A failed diagnostic check can be converted to a DetectedIssue."""
        runner = DiagnosticRunner()
        runner.register(AlwaysFailCheck())
        report = runner.run_all()

        failed = [r for r in report.results if r.status is CheckStatus.FAIL]
        assert len(failed) == 1

        # Convert to DetectedIssue
        r = failed[0]
        issue = DetectedIssue(
            category="test",
            severity=IssueSeverity.ERROR,
            tool_name=r.name,
            message=r.summary,
            details=r.details,
        )
        assert issue.severity is IssueSeverity.ERROR
        assert issue.message == "Something is broken"

    def test_warn_becomes_warning_issue(self):
        """A warning check can be converted to a warning-severity issue."""
        runner = DiagnosticRunner()
        runner.register(AlwaysWarnCheck())
        report = runner.run_all()

        warned = [r for r in report.results if r.status is CheckStatus.WARN]
        assert len(warned) == 1

        r = warned[0]
        issue = DetectedIssue(
            category="quality",
            severity=IssueSeverity.WARNING,
            tool_name=r.name,
            message=r.summary,
        )
        assert issue.severity is IssueSeverity.WARNING

    def test_full_pipeline(self):
        """Run checks -> find failures -> create issues -> remediate."""
        runner = DiagnosticRunner()
        runner.register(AlwaysPassCheck())
        runner.register(AlwaysFailCheck())
        report = runner.run_all()

        # Create issues from failures
        issues = []
        for r in report.results:
            if r.status is CheckStatus.FAIL:
                issues.append(DetectedIssue(
                    category=r.name,
                    severity=IssueSeverity.ERROR,
                    tool_name=r.name,
                    message=r.summary,
                ))

        assert len(issues) == 1

        # Set up remediation
        reg = RemediatorRegistry()
        reg.register(FakeRemediator("fix-all", {"always-fail"}))
        results = reg.fix_all(issues)
        assert len(results) == 1
        _, fix = results[0]
        assert fix is not None
        assert fix.status is FixStatus.FIXED


# =========================================================================
# 16. Integration: Built-in checks with runner
# =========================================================================


class TestBuiltInChecksWithRunner:
    """Run all built-in checks through the runner together."""

    def test_all_builtins_together(self, clean_ci_env):
        runner = DiagnosticRunner()
        runner.register(PlatformCheck())
        runner.register(DependencyCheck(DependencySpec("Python", "python3")))
        runner.register(CIEnvironmentCheck())
        report = runner.run_all()

        assert len(report.results) == 3
        # Platform always passes
        assert report.results[0].status is CheckStatus.PASS
        # Python always passes
        assert report.results[1].status is CheckStatus.PASS
        # CI skips outside CI
        assert report.results[2].status is CheckStatus.SKIP
        assert report.ok is True

    def test_builtins_by_category(self, clean_ci_env):
        runner = DiagnosticRunner()
        runner.register(PlatformCheck())
        runner.register(DependencyCheck(DependencySpec("Python", "python3")))
        runner.register(DependencyCheck(DependencySpec("Git", "git")))
        runner.register(CIEnvironmentCheck())

        platform_report = runner.run_category("platform")
        assert len(platform_report.results) == 1

        deps_report = runner.run_category("deps")
        assert len(deps_report.results) == 2

        ci_report = runner.run_category("ci")
        assert len(ci_report.results) == 1

    def test_builtins_formatted_as_json(self, clean_ci_env):
        runner = DiagnosticRunner()
        runner.register(PlatformCheck())
        runner.register(DependencyCheck(DependencySpec("Python", "python3")))
        runner.register(CIEnvironmentCheck())
        report = runner.run_all()

        data = json.loads(JsonFormatter().format(report))
        assert len(data["results"]) == 3
        names = [r["name"] for r in data["results"]]
        assert "platform" in names
        assert "dep-python3" in names
        assert "ci-environment" in names
