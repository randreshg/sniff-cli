"""Tests for platform detection."""

import platform

import pytest

from sniff_cli.detect import PlatformDetector, PlatformInfo


def test_platform_detector_always_succeeds():
    """Platform detection should never raise."""
    detector = PlatformDetector()
    info = detector.detect()
    assert isinstance(info, PlatformInfo)
    assert info.os in ("Linux", "Darwin", "Windows")


def test_platform_properties():
    """Test platform property helpers."""
    linux_info = PlatformInfo(os="Linux", arch="x86_64")
    assert linux_info.is_linux
    assert not linux_info.is_macos
    assert not linux_info.is_windows

    macos_info = PlatformInfo(os="Darwin", arch="arm64")
    assert not macos_info.is_linux
    assert macos_info.is_macos
    assert not macos_info.is_windows


def test_current_platform_detection():
    """Test detection on current platform."""
    detector = PlatformDetector()
    info = detector.detect()

    # Should match Python's platform module
    assert info.os == platform.system()
    assert info.arch in ("x86_64", "aarch64", "arm64")
