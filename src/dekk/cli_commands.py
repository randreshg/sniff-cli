"""Pre-built CLI command helpers for common tasks.

Provides run_doctor, run_version, and run_env functions that display
formatted environment information using the dekk unified styling system.
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

from dekk.cli.styles import console, print_section, print_table

if TYPE_CHECKING:
    from dekk.context import ExecutionContext


def run_doctor(context: ExecutionContext) -> None:
    """Run doctor command -- comprehensive system check.

    Displays platform, conda, CI, hardware, and package information
    using the dekk unified styling system.

    Args:
        context: Captured execution context.
    """
    # Platform
    print_section("Platform Information")
    plat = context.platform
    if hasattr(plat, "os") and hasattr(plat, "arch"):
        console.print(f"  OS: {plat.os} {plat.arch}")
    else:
        console.print(f"  OS: {plat}")
    console.print(f"  Python: {platform.python_version()}")
    console.print(f"  Hostname: {platform.node()}")

    # Conda
    if context.conda_env is not None:
        print_section("Conda Environment")
        conda = context.conda_env
        name = getattr(conda, "name", str(conda))
        console.print(f"  Active: {name}")
        prefix = getattr(conda, "prefix", None)
        if prefix is not None:
            console.print(f"  Prefix: {prefix}")
        console.print(f"  Packages: {len(context.installed_packages)}")

    # CI
    ci = context.ci_info
    is_ci = getattr(ci, "is_ci", False) if ci is not None else False
    if is_ci:
        print_section("CI Environment")
        provider = getattr(ci, "provider", None)
        if provider is not None:
            display = getattr(provider, "display_name", str(provider))
            console.print(f"  Provider: {display}")
        build = getattr(ci, "build", None)
        if build is not None:
            build_id = getattr(build, "build_id", None)
            if build_id is not None:
                console.print(f"  Build ID: {build_id}")

    # Hardware
    print_section("Hardware")
    console.print(f"  CPU: {context.cpu_info.model} ({context.cpu_info.cores} cores)")
    mem = context.memory_info
    console.print(f"  Memory: {mem.total_mb} MB")
    if context.gpu_info:
        for gpu in context.gpu_info:
            console.print(f"  GPU: {gpu.vendor} {gpu.model}")

    # Packages summary
    pkg_count = len(context.installed_packages)
    if pkg_count > 0:
        console.print(f"\n[bold]Packages[/bold]: {pkg_count} installed")


def run_version(
    app_name: str | None,
    version: str | None,
    context: ExecutionContext,
) -> None:
    """Run version command -- display app and platform version.

    Args:
        app_name: Application name (may be None).
        version: Application version string (may be None).
        context: Captured execution context.
    """
    if app_name and version:
        console.print(f"[bold]{app_name}[/bold] version {version}")

    console.print(f"  Python: {platform.python_version()}")
    plat = context.platform
    if hasattr(plat, "os") and hasattr(plat, "arch"):
        console.print(f"  Platform: {plat.os} {plat.arch}")
    else:
        console.print(f"  Platform: {plat}")


def run_env(context: ExecutionContext) -> None:
    """Run env command -- show environment details.

    Displays a table of environment variables followed by installed
    packages (limited to the first 20).

    Args:
        context: Captured execution context.
    """
    # Environment variables table
    rows = [[name, value] for name, value in sorted(context.env_vars.items())]
    print_table("Environment Variables", ["Name", "Value"], rows)

    # Installed packages (first 20)
    print_section("Installed Packages")
    for name, ver in sorted(context.installed_packages.items())[:20]:
        console.print(f"  {name}: {ver}")
