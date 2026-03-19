"""Tests for dependency checking."""

import pytest

from dekk.deps import DependencyChecker, DependencySpec, DependencyResult


def test_dependency_spec_creation():
    """Test creating dependency specs."""
    spec = DependencySpec("Python", "python3", min_version="3.11")
    assert spec.name == "Python"
    assert spec.command == "python3"
    assert spec.min_version == "3.11"
    assert spec.required is True


def test_check_existing_tool():
    """Test checking for a tool that should exist (python)."""
    checker = DependencyChecker()
    result = checker.check(DependencySpec("Python", "python3"))

    assert result.found is True
    assert result.command == "python3"
    assert result.version is not None


def test_check_missing_tool():
    """Test checking for a non-existent tool."""
    checker = DependencyChecker()
    result = checker.check(DependencySpec("Nonexistent", "definitely-not-a-real-command"))

    assert result.found is False
    assert result.version is None
    assert result.error is not None


def test_dependency_result_ok_property():
    """Test the 'ok' property."""
    # Found and meets minimum
    result = DependencyResult(
        name="Test",
        command="test",
        found=True,
        version="1.0.0",
        meets_minimum=True,
    )
    assert result.ok is True

    # Found but doesn't meet minimum
    result = DependencyResult(
        name="Test", command="test", found=True, version="0.5.0", meets_minimum=False
    )
    assert result.ok is False

    # Not found
    result = DependencyResult(name="Test", command="test", found=False)
    assert result.ok is False
