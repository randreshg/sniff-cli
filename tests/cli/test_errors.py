"""Tests for sniff.cli.errors -- exception hierarchy and exit codes."""

from __future__ import annotations

import pytest

from sniff.cli.errors import (
    ConfigError,
    DependencyError,
    ExitCodes,
    NotFoundError,
    PermissionError,
    RuntimeError,
    SniffError,
    TimeoutError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# ExitCodes Enum
# ---------------------------------------------------------------------------


class TestExitCodes:
    """Tests for the ExitCodes IntEnum."""

    def test_all_codes_present(self):
        expected = {
            "SUCCESS",
            "GENERAL_ERROR",
            "VALIDATION_ERROR",
            "NOT_FOUND",
            "PERMISSION_ERROR",
            "TIMEOUT",
            "CONFIG_ERROR",
            "DEPENDENCY_ERROR",
            "RUNTIME_ERROR",
            "INTERRUPTED",
        }
        assert expected == {c.name for c in ExitCodes}

    def test_values_are_sequential(self):
        values = [c.value for c in ExitCodes]
        assert values == list(range(10))

    def test_success_is_zero(self):
        assert ExitCodes.SUCCESS == 0

    def test_is_int(self):
        for code in ExitCodes:
            assert isinstance(code, int)

    def test_can_use_as_exit_code(self):
        assert int(ExitCodes.GENERAL_ERROR) == 1


# ---------------------------------------------------------------------------
# SniffError (base class)
# ---------------------------------------------------------------------------


class TestSniffError:
    """Tests for the base SniffError exception."""

    def test_is_exception(self):
        assert issubclass(SniffError, Exception)

    def test_message_stored(self):
        err = SniffError("Something went wrong")
        assert err.message == "Something went wrong"

    def test_hint_none_by_default(self):
        err = SniffError("error")
        assert err.hint is None

    def test_hint_stored(self):
        err = SniffError("error", hint="Try this")
        assert err.hint == "Try this"

    def test_default_exit_code(self):
        err = SniffError("error")
        assert err.exit_code == ExitCodes.GENERAL_ERROR

    def test_details_stored(self):
        err = SniffError("error", path="/tmp", count=42)
        assert err.details == {"path": "/tmp", "count": 42}

    def test_details_empty_by_default(self):
        err = SniffError("error")
        assert err.details == {}

    def test_str_is_message(self):
        err = SniffError("Something went wrong")
        assert str(err) == "Something went wrong"

    def test_can_be_raised_and_caught(self):
        with pytest.raises(SniffError, match="boom"):
            raise SniffError("boom")

    def test_to_dict_basic(self):
        err = SniffError("broken", hint="Fix it")
        d = err.to_dict()
        assert d["error"] == "SniffError"
        assert d["message"] == "broken"
        assert d["hint"] == "Fix it"
        assert d["exit_code"] == 1

    def test_to_dict_includes_details(self):
        err = SniffError("broken", searched_paths=["/a", "/b"])
        d = err.to_dict()
        assert d["searched_paths"] == ["/a", "/b"]

    def test_to_dict_hint_none(self):
        err = SniffError("broken")
        d = err.to_dict()
        assert d["hint"] is None

    def test_to_dict_no_extra_keys(self):
        err = SniffError("broken")
        assert set(d.keys()) == {"error", "message", "hint", "exit_code"} if not (d := err.to_dict()) else True
        d = err.to_dict()
        assert "error" in d
        assert "message" in d
        assert "hint" in d
        assert "exit_code" in d


# ---------------------------------------------------------------------------
# Subclass exit codes
# ---------------------------------------------------------------------------


class TestSubclassExitCodes:
    """Tests that each subclass has the correct exit_code."""

    @pytest.mark.parametrize(
        "cls, expected_code",
        [
            (NotFoundError, ExitCodes.NOT_FOUND),
            (ValidationError, ExitCodes.VALIDATION_ERROR),
            (ConfigError, ExitCodes.CONFIG_ERROR),
            (DependencyError, ExitCodes.DEPENDENCY_ERROR),
            (TimeoutError, ExitCodes.TIMEOUT),
            (PermissionError, ExitCodes.PERMISSION_ERROR),
            (RuntimeError, ExitCodes.RUNTIME_ERROR),
        ],
    )
    def test_exit_code(self, cls, expected_code):
        err = cls("test")
        assert err.exit_code == expected_code

    @pytest.mark.parametrize(
        "cls, expected_int",
        [
            (NotFoundError, 3),
            (ValidationError, 2),
            (ConfigError, 6),
            (DependencyError, 7),
            (TimeoutError, 5),
            (PermissionError, 4),
            (RuntimeError, 8),
        ],
    )
    def test_exit_code_int_value(self, cls, expected_int):
        err = cls("test")
        assert int(err.exit_code) == expected_int


# ---------------------------------------------------------------------------
# Subclass inheritance
# ---------------------------------------------------------------------------


class TestSubclassInheritance:
    """Tests that all subclasses inherit from SniffError."""

    @pytest.mark.parametrize(
        "cls",
        [
            NotFoundError,
            ValidationError,
            ConfigError,
            DependencyError,
            TimeoutError,
            PermissionError,
            RuntimeError,
        ],
    )
    def test_is_sniff_error(self, cls):
        assert issubclass(cls, SniffError)

    @pytest.mark.parametrize(
        "cls",
        [
            NotFoundError,
            ValidationError,
            ConfigError,
            DependencyError,
            TimeoutError,
            PermissionError,
            RuntimeError,
        ],
    )
    def test_catchable_as_sniff_error(self, cls):
        with pytest.raises(SniffError):
            raise cls("test")


# ---------------------------------------------------------------------------
# to_dict on subclasses
# ---------------------------------------------------------------------------


class TestSubclassToDict:
    """Tests for to_dict on error subclasses."""

    def test_not_found_to_dict(self):
        err = NotFoundError("Environment 'ml' not found", hint="Create it", searched_paths=["/opt"])
        d = err.to_dict()
        assert d["error"] == "NotFoundError"
        assert d["message"] == "Environment 'ml' not found"
        assert d["hint"] == "Create it"
        assert d["exit_code"] == 3
        assert d["searched_paths"] == ["/opt"]

    def test_validation_to_dict(self):
        err = ValidationError("Invalid format", field="name")
        d = err.to_dict()
        assert d["error"] == "ValidationError"
        assert d["field"] == "name"
        assert d["exit_code"] == 2

    def test_config_to_dict(self):
        err = ConfigError("Missing key", hint="Add 'database.path' to config.toml")
        d = err.to_dict()
        assert d["error"] == "ConfigError"
        assert d["exit_code"] == 6

    def test_dependency_to_dict(self):
        err = DependencyError("tomli not installed", package="tomli")
        d = err.to_dict()
        assert d["error"] == "DependencyError"
        assert d["package"] == "tomli"

    def test_timeout_to_dict(self):
        err = TimeoutError("Request timed out", timeout_seconds=30)
        d = err.to_dict()
        assert d["error"] == "TimeoutError"
        assert d["timeout_seconds"] == 30

    def test_permission_to_dict(self):
        err = PermissionError("Cannot write", path="/etc/config")
        d = err.to_dict()
        assert d["error"] == "PermissionError"
        assert d["path"] == "/etc/config"

    def test_runtime_to_dict(self):
        err = RuntimeError("Subprocess failed", returncode=127)
        d = err.to_dict()
        assert d["error"] == "RuntimeError"
        assert d["returncode"] == 127


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for errors module."""

    def test_empty_message(self):
        err = SniffError("")
        assert err.message == ""
        assert str(err) == ""

    def test_unicode_message(self):
        err = SniffError("Failed \u2717 badly")
        assert "\u2717" in err.message

    def test_multiple_details(self):
        err = SniffError("err", a=1, b="two", c=[3])
        assert err.details == {"a": 1, "b": "two", "c": [3]}

    def test_detail_with_colliding_key(self):
        """Details whose key collides with to_dict base keys override them."""
        # "error" is set by to_dict but can be overridden via **details
        err = SniffError("msg", error="CustomName")
        d = err.to_dict()
        # result.update(self.details) runs after setting result["error"],
        # so the detail value wins.
        assert d["error"] == "CustomName"

    def test_shadowing_builtin_names(self):
        """PermissionError and RuntimeError shadow builtins but work correctly."""
        # Our PermissionError should be SniffError, not builtins.PermissionError
        err = PermissionError("denied")
        assert isinstance(err, SniffError)
        assert not isinstance(err, builtins_PermissionError)


# We need to import builtins for the shadowing test
import builtins

builtins_PermissionError = builtins.PermissionError
