"""Tests for sniff.validate -- EnvironmentValidator, CheckResult, ValidationReport."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from sniff.remediate import DetectedIssue, IssueSeverity
from sniff.validate import (
    CheckResult,
    CheckStatus,
    EnvironmentValidator,
    ValidationReport,
)


# ---------------------------------------------------------------------------
# CheckStatus enum
# ---------------------------------------------------------------------------


class TestCheckStatus:
    def test_values(self):
        assert CheckStatus.PASSED.value == "passed"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.FAILED.value == "failed"
        assert CheckStatus.SKIPPED.value == "skipped"

    def test_all_members(self):
        assert len(CheckStatus) == 4


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------


class TestCheckResult:
    def test_frozen(self):
        r = CheckResult(name="test", status=CheckStatus.PASSED)
        with pytest.raises(AttributeError):
            r.name = "other"  # type: ignore[misc]

    def test_passed_property(self):
        assert CheckResult(name="t", status=CheckStatus.PASSED).passed is True
        assert CheckResult(name="t", status=CheckStatus.FAILED).passed is False
        assert CheckResult(name="t", status=CheckStatus.WARNING).passed is False
        assert CheckResult(name="t", status=CheckStatus.SKIPPED).passed is False

    def test_defaults(self):
        r = CheckResult(name="test", status=CheckStatus.PASSED)
        assert r.message == ""
        assert r.category == "environment"
        assert r.details == {}
        assert r.elapsed_ms == 0.0

    def test_custom_fields(self):
        r = CheckResult(
            name="cmake",
            status=CheckStatus.FAILED,
            message="cmake not found",
            category="dependency",
            details={"tool": "cmake"},
            elapsed_ms=12.5,
        )
        assert r.name == "cmake"
        assert r.message == "cmake not found"
        assert r.category == "dependency"
        assert r.details["tool"] == "cmake"
        assert r.elapsed_ms == 12.5

    def test_to_issue_passed_returns_none(self):
        r = CheckResult(name="t", status=CheckStatus.PASSED)
        assert r.to_issue() is None

    def test_to_issue_skipped_returns_none(self):
        r = CheckResult(name="t", status=CheckStatus.SKIPPED)
        assert r.to_issue() is None

    def test_to_issue_failed(self):
        r = CheckResult(
            name="cmake",
            status=CheckStatus.FAILED,
            message="cmake not found",
            category="dependency",
            details={"tool": "cmake"},
        )
        issue = r.to_issue()
        assert issue is not None
        assert isinstance(issue, DetectedIssue)
        assert issue.severity is IssueSeverity.ERROR
        assert issue.category == "dependency"
        assert issue.tool_name == "cmake"
        assert issue.message == "cmake not found"

    def test_to_issue_warning(self):
        r = CheckResult(
            name="var",
            status=CheckStatus.WARNING,
            message="value mismatch",
            category="environment",
            details={"tool": "env"},
        )
        issue = r.to_issue()
        assert issue is not None
        assert issue.severity is IssueSeverity.WARNING

    def test_to_issue_no_tool_in_details(self):
        r = CheckResult(
            name="t",
            status=CheckStatus.FAILED,
            message="problem",
            details={},
        )
        issue = r.to_issue()
        assert issue is not None
        assert issue.tool_name is None


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


class TestValidationReport:
    def _make_report(self, *statuses: CheckStatus) -> ValidationReport:
        results = tuple(
            CheckResult(name=f"check_{i}", status=s)
            for i, s in enumerate(statuses)
        )
        return ValidationReport(results=results, elapsed_ms=42.0)

    def test_empty_report(self):
        report = ValidationReport(results=())
        assert report.passed == 0
        assert report.warnings == 0
        assert report.failed == 0
        assert report.skipped == 0
        assert report.ok is True
        assert report.issues() == []

    def test_all_passed(self):
        report = self._make_report(
            CheckStatus.PASSED, CheckStatus.PASSED, CheckStatus.PASSED
        )
        assert report.passed == 3
        assert report.ok is True

    def test_mixed_results(self):
        report = self._make_report(
            CheckStatus.PASSED,
            CheckStatus.WARNING,
            CheckStatus.FAILED,
            CheckStatus.SKIPPED,
        )
        assert report.passed == 1
        assert report.warnings == 1
        assert report.failed == 1
        assert report.skipped == 1
        assert report.ok is False

    def test_ok_with_warnings(self):
        report = self._make_report(CheckStatus.PASSED, CheckStatus.WARNING)
        assert report.ok is True  # warnings don't fail

    def test_ok_with_skipped(self):
        report = self._make_report(CheckStatus.PASSED, CheckStatus.SKIPPED)
        assert report.ok is True

    def test_elapsed_ms(self):
        report = self._make_report(CheckStatus.PASSED)
        assert report.elapsed_ms == 42.0

    def test_issues_extracts_non_passing(self):
        report = self._make_report(
            CheckStatus.PASSED,
            CheckStatus.WARNING,
            CheckStatus.FAILED,
            CheckStatus.SKIPPED,
        )
        issues = report.issues()
        assert len(issues) == 2  # warning + failed
        severities = {i.severity for i in issues}
        assert IssueSeverity.WARNING in severities
        assert IssueSeverity.ERROR in severities

    def test_frozen(self):
        report = ValidationReport(results=())
        with pytest.raises(AttributeError):
            report.results = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EnvironmentValidator -- check_tool
# ---------------------------------------------------------------------------


class TestCheckTool:
    def setup_method(self):
        self.validator = EnvironmentValidator()

    def test_tool_found(self):
        # 'python3' or 'python' should exist in test environment
        result = self.validator.check_tool("python3")
        assert result.status is CheckStatus.PASSED
        assert "python3" in result.message
        assert result.details["tool"] == "python3"
        assert "path" in result.details
        assert result.elapsed_ms >= 0

    def test_tool_not_found(self):
        result = self.validator.check_tool("absolutely_nonexistent_binary_xyz")
        assert result.status is CheckStatus.FAILED
        assert "not found" in result.message
        assert result.details["tool"] == "absolutely_nonexistent_binary_xyz"
        assert "path" not in result.details

    def test_custom_name(self):
        result = self.validator.check_tool("python3", name="Python")
        assert result.name == "Python"

    def test_custom_category(self):
        result = self.validator.check_tool("python3", category="runtime")
        assert result.category == "runtime"

    def test_default_category(self):
        result = self.validator.check_tool("python3")
        assert result.category == "dependency"


# ---------------------------------------------------------------------------
# EnvironmentValidator -- check_directory
# ---------------------------------------------------------------------------


class TestCheckDirectory:
    def setup_method(self):
        self.validator = EnvironmentValidator()

    def test_directory_exists(self, tmp_path):
        result = self.validator.check_directory(tmp_path)
        assert result.status is CheckStatus.PASSED
        assert "exists" in result.message

    def test_directory_not_exists(self, tmp_path):
        result = self.validator.check_directory(tmp_path / "nonexistent_dir_xyz")
        assert result.status is CheckStatus.FAILED
        assert "not found" in result.message

    def test_file_is_not_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = self.validator.check_directory(f)
        assert result.status is CheckStatus.FAILED

    def test_custom_name(self, tmp_path):
        result = self.validator.check_directory(tmp_path, name="Build dir")
        assert result.name == "Build dir"

    def test_custom_category(self, tmp_path):
        result = self.validator.check_directory(tmp_path, category="build")
        assert result.category == "build"

    def test_string_path(self, tmp_path):
        result = self.validator.check_directory(str(tmp_path))
        assert result.status is CheckStatus.PASSED

    def test_pathlib_path(self, tmp_path):
        result = self.validator.check_directory(tmp_path)
        assert result.status is CheckStatus.PASSED


# ---------------------------------------------------------------------------
# EnvironmentValidator -- check_env_var
# ---------------------------------------------------------------------------


class TestCheckEnvVar:
    def setup_method(self):
        self.validator = EnvironmentValidator()

    def test_var_set(self):
        with patch.dict(os.environ, {"SNIFF_TEST_VAR": "hello"}):
            result = self.validator.check_env_var("SNIFF_TEST_VAR")
        assert result.status is CheckStatus.PASSED
        assert result.details["value"] == "hello"

    def test_var_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            result = self.validator.check_env_var("TOTALLY_MISSING_VAR_XYZ")
        assert result.status is CheckStatus.FAILED
        assert "not set" in result.message

    def test_var_expected_match(self):
        with patch.dict(os.environ, {"SNIFF_TEST_VAR": "correct"}):
            result = self.validator.check_env_var(
                "SNIFF_TEST_VAR", expected="correct"
            )
        assert result.status is CheckStatus.PASSED

    def test_var_expected_mismatch(self):
        with patch.dict(os.environ, {"SNIFF_TEST_VAR": "wrong"}):
            result = self.validator.check_env_var(
                "SNIFF_TEST_VAR", expected="correct"
            )
        assert result.status is CheckStatus.WARNING
        assert "wrong" in result.message
        assert "correct" in result.message

    def test_custom_name(self):
        with patch.dict(os.environ, {"SNIFF_TEST_VAR": "hello"}):
            result = self.validator.check_env_var(
                "SNIFF_TEST_VAR", name="Test Variable"
            )
        assert result.name == "Test Variable"

    def test_custom_category(self):
        with patch.dict(os.environ, {"SNIFF_TEST_VAR": "hello"}):
            result = self.validator.check_env_var(
                "SNIFF_TEST_VAR", category="config"
            )
        assert result.category == "config"


# ---------------------------------------------------------------------------
# EnvironmentValidator -- check_file
# ---------------------------------------------------------------------------


class TestCheckFile:
    def setup_method(self):
        self.validator = EnvironmentValidator()

    def test_file_exists(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        result = self.validator.check_file(f)
        assert result.status is CheckStatus.PASSED
        assert "exists" in result.message

    def test_file_not_exists(self, tmp_path):
        result = self.validator.check_file(tmp_path / "nonexistent_file.txt")
        assert result.status is CheckStatus.FAILED
        assert "not found" in result.message

    def test_directory_is_not_file(self, tmp_path):
        result = self.validator.check_file(tmp_path)
        assert result.status is CheckStatus.FAILED

    def test_custom_name(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text("[section]")
        result = self.validator.check_file(f, name="Config file")
        assert result.name == "Config file"

    def test_custom_category(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text("[section]")
        result = self.validator.check_file(f, category="project")
        assert result.category == "project"

    def test_string_path(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        result = self.validator.check_file(str(f))
        assert result.status is CheckStatus.PASSED


# ---------------------------------------------------------------------------
# EnvironmentValidator -- run_all
# ---------------------------------------------------------------------------


class TestRunAll:
    def test_empty(self):
        v = EnvironmentValidator()
        report = v.run_all()
        assert report.ok is True
        assert len(report.results) == 0
        assert report.elapsed_ms >= 0

    def test_registered_checks(self):
        v = EnvironmentValidator()
        v.add_check(lambda: CheckResult(name="a", status=CheckStatus.PASSED))
        v.add_check(lambda: CheckResult(name="b", status=CheckStatus.FAILED, message="bad"))
        report = v.run_all()
        assert len(report.results) == 2
        assert report.passed == 1
        assert report.failed == 1
        assert not report.ok

    def test_exception_in_check(self):
        v = EnvironmentValidator()

        def bad_check():
            raise RuntimeError("boom")

        v.add_check(bad_check)
        report = v.run_all()
        assert len(report.results) == 1
        assert report.results[0].status is CheckStatus.FAILED
        assert "boom" in report.results[0].message

    def test_exception_preserves_function_name(self):
        v = EnvironmentValidator()

        def my_special_check():
            raise ValueError("oops")

        v.add_check(my_special_check)
        report = v.run_all()
        assert report.results[0].name == "my_special_check"

    def test_mixed_with_builtin_checks(self, tmp_path):
        v = EnvironmentValidator()
        d = tmp_path / "exists"
        d.mkdir()

        v.add_check(lambda: v.check_tool("python3"))
        v.add_check(lambda: v.check_directory(d))
        v.add_check(lambda: v.check_directory("/nonexistent/path"))

        report = v.run_all()
        assert report.passed == 2
        assert report.failed == 1


# ---------------------------------------------------------------------------
# EnvironmentValidator -- run_checks
# ---------------------------------------------------------------------------


class TestRunChecks:
    def test_explicit_checks(self):
        v = EnvironmentValidator()
        # add_check should be ignored by run_checks
        v.add_check(lambda: CheckResult(name="registered", status=CheckStatus.PASSED))

        checks = [
            lambda: CheckResult(name="explicit", status=CheckStatus.PASSED),
        ]
        report = v.run_checks(checks)
        assert len(report.results) == 1
        assert report.results[0].name == "explicit"

    def test_exception_handling(self):
        v = EnvironmentValidator()
        checks = [
            lambda: (_ for _ in ()).throw(RuntimeError("fail")),  # type: ignore
        ]
        # Actually use a proper callable
        def raises():
            raise RuntimeError("fail")

        report = v.run_checks([raises])
        assert len(report.results) == 1
        assert report.results[0].status is CheckStatus.FAILED

    def test_empty_checks_list(self):
        v = EnvironmentValidator()
        report = v.run_checks([])
        assert report.ok is True
        assert len(report.results) == 0


# ---------------------------------------------------------------------------
# Integration: Validator -> Report -> Issues -> Remediation pipeline
# ---------------------------------------------------------------------------


class TestValidationPipeline:
    def test_full_pipeline(self, tmp_path):
        """End-to-end: register checks -> run -> extract issues."""
        v = EnvironmentValidator()
        d = tmp_path / "ok_dir"
        d.mkdir()

        v.add_check(lambda: v.check_directory(d, name="Build dir"))
        v.add_check(
            lambda: v.check_tool(
                "nonexistent_tool_xyz123",
                name="MissingTool",
                category="dependency",
            )
        )
        with patch.dict(os.environ, {"SNIFF_TEST": "wrong"}):
            v.add_check(
                lambda: v.check_env_var(
                    "SNIFF_TEST", expected="correct", name="Test Var"
                )
            )
            report = v.run_all()

        assert not report.ok  # at least one failure
        issues = report.issues()
        assert len(issues) >= 1
        # Should have a dependency issue for the missing tool
        dep_issues = [i for i in issues if i.category == "dependency"]
        assert len(dep_issues) == 1
        assert dep_issues[0].severity is IssueSeverity.ERROR

    def test_issues_from_passing_report(self):
        """A fully passing report should produce no issues."""
        v = EnvironmentValidator()
        v.add_check(lambda: CheckResult(name="ok", status=CheckStatus.PASSED))
        v.add_check(lambda: CheckResult(name="skip", status=CheckStatus.SKIPPED))
        report = v.run_all()
        assert report.ok is True
        assert report.issues() == []

    def test_top_level_import(self):
        """ValidationReport and EnvironmentValidator are importable from sniff."""
        from sniff import ValidationReport as VR, EnvironmentValidator as EV
        assert VR is ValidationReport
        assert EV is EnvironmentValidator


# ---------------------------------------------------------------------------
# Integration with toolchain profiles
# ---------------------------------------------------------------------------


class TestValidateToolchainIntegration:
    """Tests combining validate + toolchain modules."""

    def test_validate_cmake_directories(self, tmp_path):
        """Validate that CMakeToolchain paths exist using EnvironmentValidator."""
        from sniff.toolchain import CMakeToolchain

        prefix = tmp_path / "envs" / "apxm"
        (prefix / "lib" / "cmake" / "mlir").mkdir(parents=True)
        (prefix / "lib" / "cmake" / "llvm").mkdir(parents=True)
        (prefix / "bin").mkdir(parents=True)

        tc = CMakeToolchain(prefix=prefix)

        v = EnvironmentValidator()
        v.add_check(lambda: v.check_directory(tc.mlir_dir, name="MLIR CMake"))
        v.add_check(lambda: v.check_directory(tc.llvm_dir, name="LLVM CMake"))
        v.add_check(lambda: v.check_directory(tc.bin_dir, name="Toolchain bin"))
        v.add_check(lambda: v.check_directory(tc.lib_dir, name="Toolchain lib"))

        report = v.run_all()
        assert report.ok is True
        assert report.passed == 4

    def test_validate_missing_cmake_directories(self, tmp_path):
        """Report failures for missing CMakeToolchain directories."""
        from sniff.toolchain import CMakeToolchain

        prefix = tmp_path / "nonexistent" / "envs" / "apxm"
        tc = CMakeToolchain(prefix=prefix)

        v = EnvironmentValidator()
        v.add_check(lambda: v.check_directory(tc.mlir_dir, name="MLIR CMake"))
        v.add_check(lambda: v.check_directory(tc.llvm_dir, name="LLVM CMake"))

        report = v.run_all()
        assert report.failed == 2
        assert not report.ok

    def test_validate_conda_env_var(self, tmp_path):
        """After CondaToolchain configures env vars, validate they're set."""
        from sniff.toolchain import CondaToolchain, EnvVarBuilder as TcBuilder

        prefix = tmp_path / "miniforge3" / "envs" / "apxm"
        prefix.mkdir(parents=True)

        tc = CondaToolchain(prefix=prefix, env_name="apxm")
        builder = TcBuilder()
        tc.configure(builder)
        env_dict = builder.to_env_dict()

        v = EnvironmentValidator()
        with patch.dict(os.environ, env_dict, clear=False):
            v.add_check(
                lambda: v.check_env_var("CONDA_PREFIX", expected=str(prefix))
            )
            v.add_check(
                lambda: v.check_env_var("CONDA_DEFAULT_ENV", expected="apxm")
            )
            report = v.run_all()

        assert report.ok is True
        assert report.passed == 2


# ---------------------------------------------------------------------------
# Integration with env module
# ---------------------------------------------------------------------------


class TestValidateEnvIntegration:
    """Tests combining validate + env modules."""

    def test_validate_env_snapshot_vars(self):
        """Build an env from EnvVarBuilder, then validate with EnvironmentValidator."""
        from sniff.env import EnvVarBuilder as EnvBuilder

        snap = (
            EnvBuilder()
            .set("MY_VAR", "my_value")
            .set("OTHER_VAR", "other")
            .build()
        )

        v = EnvironmentValidator()
        with patch.dict(os.environ, snap.to_dict(), clear=False):
            v.add_check(
                lambda: v.check_env_var("MY_VAR", expected="my_value")
            )
            v.add_check(
                lambda: v.check_env_var("OTHER_VAR", expected="other")
            )
            report = v.run_all()

        assert report.ok is True
        assert report.passed == 2


# ---------------------------------------------------------------------------
# Integration with libpath module
# ---------------------------------------------------------------------------


class TestValidateLibpathIntegration:
    """Tests combining validate + libpath modules."""

    def test_validate_library_path_after_apply(self):
        """After LibraryPathResolver.apply(), validate the env var is set."""
        from sniff.libpath import LibraryPathResolver

        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/test/lib")

        v = EnvironmentValidator()
        with patch.dict(os.environ, {}, clear=True):
            resolver.apply()
            result = v.check_env_var("LD_LIBRARY_PATH")

        assert result.status is CheckStatus.PASSED
        assert "/opt/test/lib" in result.details.get("value", "")
