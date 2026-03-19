"""Binary installation and PATH management for project tools."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Optional, Sequence

from .cli.errors import NotFoundError
from .shell import ShellDetector, ShellKind
from .dekk_os import get_dekk_os

DEFAULT_INSTALL_DIRNAME: Final = ".install"
DEKK_MODULE_NAME: Final = "dekk"
PROJECT_SPEC_FILENAME: Final = ".dekk.toml"
SHELL_CONFIG_STATE_ADDED: Final = "added"
SHELL_CONFIG_STATE_ALREADY_CONFIGURED: Final = "already_configured"
SHELL_CONFIG_STATE_FAILED: Final = "failed"
SHELL_CONFIG_ENTRY_SUFFIX: Final = "install dir"
MESSAGE_ADDED_TO_SHELL_CONFIG: Final = " (added to shell config - restart shell)"
MESSAGE_ALREADY_IN_SHELL_CONFIG: Final = " (already in shell config - restart shell if needed)"
MESSAGE_REMOVED_SHELL_CONFIG_ENTRY: Final = " (removed shell config entry)"


@dataclass
class InstallResult:
    """Result of binary installation."""

    bin_path: Path
    in_path: bool
    message: str


class BinaryInstaller:
    """Install binaries and manage PATH."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def install_binary(
        self,
        source: Path,
        install_dir: Optional[Path] = None,
        update_shell: bool = True,
    ) -> InstallResult:
        """Install a binary to the project install directory and optionally update PATH.

        Args:
            source: Binary to install
            install_dir: Target directory (default: ``{project}/.install``)
            update_shell: Update shell config if install dir is not in PATH

        Returns:
            InstallResult with details
        """
        if not source.exists():
            raise NotFoundError(f"Binary not found: {source}", hint="Build it first")

        if install_dir is None:
            install_dir = self.default_install_dir()
        install_dir.mkdir(parents=True, exist_ok=True)
        target = install_dir / source.name

        # Install: try symlink first, fall back to copy
        try:
            if target.exists():
                target.unlink()
            target.symlink_to(source.resolve())
        except (OSError, NotImplementedError):
            shutil.copy2(source, target)
            target.chmod(0o755)
        result = InstallResult(
            bin_path=target,
            in_path=self._is_in_path(install_dir),
            message=f"Installed {source.name} → {install_dir}",
        )
        return self._with_shell_path_update(result, update_shell=update_shell)

    def install_wrapper(
        self,
        target: Path,
        spec: Optional["EnvironmentSpec"] = None,
        spec_file: Optional[Path] = None,
        python: Optional[Path] = None,
        name: Optional[str] = None,
        install_dir: Optional[Path] = None,
        update_shell: bool = True,
    ) -> InstallResult:
        """Generate and install a self-contained wrapper script.

        Creates a shell script that activates the full project environment
        (conda, paths, env vars) and execs the target. No manual activation needed.

        Args:
            target: Binary or script to wrap (what the wrapper execs)
            spec: Pre-loaded EnvironmentSpec (mutually exclusive with spec_file)
            spec_file: Path to .dekk.toml (mutually exclusive with spec)
            python: Python interpreter to use (for wrapping Python scripts)
            name: Name for the wrapper binary (default: target filename)
            install_dir: Where to install (default: ``{project}/.install``)

        Returns:
            InstallResult with details
        """
        from dekk.envspec import EnvironmentSpec, find_envspec
        from dekk.wrapper import WrapperGenerator

        if spec is None:
            if spec_file is not None:
                spec = EnvironmentSpec.from_file(spec_file)
            else:
                found = find_envspec(self.project_root)
                if found is None:
                    raise NotFoundError(
                        f"No {PROJECT_SPEC_FILENAME} found",
                        hint=f"Provide spec or spec_file, or create {PROJECT_SPEC_FILENAME}",
                    )
                spec = EnvironmentSpec.from_file(found)

        wrapper_name = name or target.stem

        result = WrapperGenerator.install_from_spec(
            spec_file=spec,
            target=target,
            name=wrapper_name,
            python=python,
            install_dir=install_dir,
            project_root=self.project_root,
        )
        return self._with_shell_path_update(result, update_shell=update_shell)

    def install_python_shim(
        self,
        script: Path,
        *,
        name: Optional[str] = None,
        install_dir: Optional[Path] = None,
        update_shell: bool = True,
    ) -> InstallResult:
        """Install a wrapper that runs a Python script through ``python -m dekk``.

        This is the highest-friction-free path for Python CLIs that live in a
        normal Python project: the installed command reuses dekk's
        ``run_script`` bootstrap, which creates ``.venv`` from ``pyproject.toml``
        on first run and then execs the script with the project environment.
        """
        from dekk.wrapper import WrapperGenerator

        script = script.resolve()
        if not script.exists():
            raise NotFoundError(f"Script not found: {script}", hint="Check the path and try again")
        if _find_pyproject(script.parent) is None:
            raise NotFoundError(
                f"No pyproject.toml found for {script}",
                hint="Add a pyproject.toml near the script or use --python with a .dekk.toml config",
            )

        command = [sys.executable, "-m", DEKK_MODULE_NAME, str(script)]
        wrapper_name = name or script.stem
        project_name = self.project_root.name or wrapper_name
        wrapper = _render_command_wrapper(command, project_name=project_name)
        result = WrapperGenerator.install(
            wrapper,
            wrapper_name,
            install_dir=install_dir or self.default_install_dir(),
        )
        return self._with_shell_path_update(result, update_shell=update_shell)

    def uninstall(
        self,
        name: str,
        install_dir: Optional[Path] = None,
        clean_shell: bool = True,
    ) -> InstallResult:
        """Remove an installed binary and optionally clean shell config.

        Args:
            name: Binary file name to remove
            install_dir: Directory to look in (default: ``{project}/.install``)
            clean_shell: Remove PATH entries from shell config

        Returns:
            InstallResult with details
        """
        if install_dir is None:
            install_dir = self.default_install_dir()

        target = install_dir / name
        if target.exists() or target.is_symlink():
            target.unlink()
            message = f"Removed {name} from {install_dir}"
        else:
            message = f"{name} not found in {install_dir} (nothing to remove)"

        if clean_shell:
            self._remove_from_shell_config(install_dir)

        return InstallResult(bin_path=target, in_path=False, message=message)

    def uninstall_wrapper(
        self,
        name: str,
        *,
        install_dir: Optional[Path] = None,
        clean_shell: bool = False,
    ) -> InstallResult:
        """Remove an installed wrapper and optionally remove its PATH entry.

        This is the wrapper/script counterpart to ``install_wrapper`` and
        ``install_python_shim``. Projects can call it directly to provide
        their own uninstall command on top of dekk's install surface.
        """
        from dekk.wrapper import WrapperGenerator

        result = WrapperGenerator.uninstall(name, install_dir=install_dir or self.default_install_dir())
        if clean_shell:
            self._remove_from_shell_config(result.bin_path.parent)
            result.message += MESSAGE_REMOVED_SHELL_CONFIG_ENTRY
        return result

    def default_install_dir(self) -> Path:
        """Return the project-local install directory used by dekk."""
        return self.project_root / DEFAULT_INSTALL_DIRNAME

    def _remove_from_shell_config(self, install_dir: Path) -> bool:
        """Remove PATH entries added by dekk. Returns True if cleaned."""
        shell_info = ShellDetector().detect()
        if not shell_info or shell_info.kind == ShellKind.UNKNOWN:
            return False

        config_file = self._find_shell_config(shell_info.kind)
        if not config_file or not config_file.exists():
            return False

        marker = self._shell_config_marker()
        try:
            lines = config_file.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            return False

        # Remove the marker line and the export line that follows it
        cleaned: list[str] = []
        skip_next = False
        removed = False
        for line in lines:
            if skip_next:
                skip_next = False
                removed = True
                continue
            if marker in line:
                skip_next = True
                removed = True
                # Also skip the blank line before the marker if present
                if cleaned and cleaned[-1].strip() == "":
                    cleaned.pop()
                continue
            cleaned.append(line)

        if removed:
            try:
                config_file.write_text("".join(cleaned), encoding="utf-8")
                return True
            except (OSError, PermissionError):
                return False

        return False

    def _is_in_path(self, directory: Path) -> bool:
        """Check if directory is in PATH."""
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        dir_resolved = str(directory.resolve())
        return any(str(Path(p).resolve()) == dir_resolved for p in path_dirs if p)

    def _ensure_shell_config_path(
        self,
        install_dir: Path,
    ) -> Literal["added", "already_configured", "failed"]:
        """Ensure the install directory is exported from the active shell config."""
        shell_info = ShellDetector().detect()
        if not shell_info or shell_info.kind == ShellKind.UNKNOWN:
            return SHELL_CONFIG_STATE_FAILED

        config_file = self._find_shell_config(shell_info.kind)
        if not config_file:
            return SHELL_CONFIG_STATE_FAILED

        config_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            existing = config_file.read_text(encoding="utf-8") if config_file.exists() else ""
            if str(install_dir) in existing:
                return SHELL_CONFIG_STATE_ALREADY_CONFIGURED
        except (OSError, UnicodeDecodeError):
            return SHELL_CONFIG_STATE_FAILED

        export_line = self._path_export(shell_info.kind, install_dir)
        try:
            with config_file.open("a", encoding="utf-8") as f:
                f.write(f"\n{self._shell_config_marker()}\n{export_line}\n")
            return SHELL_CONFIG_STATE_ADDED
        except (OSError, PermissionError):
            return SHELL_CONFIG_STATE_FAILED

    def _find_shell_config(self, kind: ShellKind) -> Optional[Path]:
        """Find the shell config file to update."""
        detector = ShellDetector()
        candidates = detector.config_candidates(kind)

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[0] if candidates else None

    def _path_export(self, kind: ShellKind, install_dir: Path) -> str:
        """Generate PATH export for shell type."""
        path = str(install_dir)
        if kind == ShellKind.FISH:
            return f'fish_add_path -p "{path}"'
        elif kind == ShellKind.TCSH:
            return f'setenv PATH "{path}:$PATH"'
        elif kind in (ShellKind.POWERSHELL, ShellKind.PWSH):
            return f'$env:PATH = "{path}" + [IO.Path]::PathSeparator + $env:PATH'
        else:
            return f'export PATH="{path}:$PATH"'

    def _with_shell_path_update(self, result: InstallResult, *, update_shell: bool) -> InstallResult:
        """Update shell config for an install result when needed."""
        install_dir = result.bin_path.parent
        in_path = self._is_in_path(install_dir)
        message = result.message.split(" (add ", 1)[0]

        if not in_path and update_shell:
            shell_config_state = self._ensure_shell_config_path(install_dir)
            if shell_config_state == SHELL_CONFIG_STATE_ADDED:
                message += MESSAGE_ADDED_TO_SHELL_CONFIG
                in_path = True
            elif shell_config_state == SHELL_CONFIG_STATE_ALREADY_CONFIGURED:
                message += MESSAGE_ALREADY_IN_SHELL_CONFIG
                in_path = True
            else:
                message += f" (add {install_dir} to PATH manually)"

        return InstallResult(bin_path=result.bin_path, in_path=in_path, message=message)

    def _shell_config_marker(self) -> str:
        """Return the dekk marker used around shell PATH exports."""
        return f"# {DEKK_MODULE_NAME}: {self.project_root.name} {SHELL_CONFIG_ENTRY_SUFFIX}"


def _render_command_wrapper(command: Sequence[str], *, project_name: str) -> str:
    """Render a minimal cross-platform wrapper for an arbitrary command."""
    dekk_os = get_dekk_os()
    if dekk_os.name == "windows":
        lines = [
            "@echo off",
            "setlocal",
            f"REM Wrapper for {project_name}",
            "REM Generated by dekk",
            "REM This wrapper bootstraps and runs the project command.",
            "",
            "call " + subprocess.list2cmdline(list(command)) + " %*",
            "set EXIT_CODE=%ERRORLEVEL%",
            "endlocal & exit /b %EXIT_CODE%",
            "",
        ]
        return "\r\n".join(lines)

    quoted = " ".join(shlex.quote(part) for part in command)
    return "\n".join(
        [
            "#!/bin/sh",
            f"# Wrapper for {project_name}",
            "# Generated by dekk",
            "# This wrapper bootstraps and runs the project command.",
            "",
            f"exec {quoted} \"$@\"",
            "",
        ]
    )


def _find_pyproject(start: Path) -> Path | None:
    """Walk up from *start* looking for ``pyproject.toml``."""
    current = start.resolve()
    for parent in (current, *current.parents):
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None
