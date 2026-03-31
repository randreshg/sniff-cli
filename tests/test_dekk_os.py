"""Tests for dekk.execution.os."""

from __future__ import annotations

from dekk.execution.os import PosixDekkOS, WindowsDekkOS, get_dekk_os


class TestGetDekkOs:
    def test_explicit_windows_override(self):
        assert isinstance(get_dekk_os("Windows"), WindowsDekkOS)

    def test_explicit_posix_override(self):
        assert isinstance(get_dekk_os("Linux"), PosixDekkOS)
