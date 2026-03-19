"""Tests for sniff_cli.sniff_os."""

from __future__ import annotations

from sniff_cli.sniff_os import PosixSniffOS, WindowsSniffOS, get_sniff_os


class TestGetSniffOs:
    def test_explicit_windows_override(self):
        assert isinstance(get_sniff_os("Windows"), WindowsSniffOS)

    def test_explicit_posix_override(self):
        assert isinstance(get_sniff_os("Linux"), PosixSniffOS)
