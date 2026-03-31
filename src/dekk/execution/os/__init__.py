"""OS-specific execution strategies."""

from __future__ import annotations

import platform

from dekk.execution.os.base import DekkOS
from dekk.execution.os.posix import PosixDekkOS
from dekk.execution.os.windows import WindowsDekkOS

WINDOWS_SYSTEM_NAME = "Windows"


def get_dekk_os(system_name: str | None = None) -> DekkOS:
    """Return the host or requested OS implementation."""
    detected = system_name if system_name is not None else platform.system()
    if detected == WINDOWS_SYSTEM_NAME:
        return WindowsDekkOS()
    return PosixDekkOS()


__all__ = ["DekkOS", "PosixDekkOS", "WindowsDekkOS", "get_dekk_os"]
