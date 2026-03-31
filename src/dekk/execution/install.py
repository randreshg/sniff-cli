"""Binary installation and PATH management for project tools."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from ..cli.errors import NotFoundError
from .os import get_dekk_os
from ..shell import ShellDetector, ShellKind

if TYPE_CHECKING:
    from ..environment.spec import EnvironmentSpec

DEFAULT_INSTALL_DIRNAME: Final = ".install"
PROJECT_SPEC_FILENAME: Final = ".dekk.toml"
PYTHON_SCRIPT_SUFFIX: Final = ".py"
PROJECT_VENV_DIRNAME: Final = ".venv"
DEKK_MARKER_PREFIX: Final = "# dekk:"
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
        install_dir: Path | None = None,
        update_shell: bool = False,
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
        spec: EnvironmentSpec | None = None,
        spec_file: Path | None = None,
        python: Path | None = None,
        name: str | None = None,
        install_dir: Path | None = None,
        update_shell: bool = False,
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
        from dekk.environment.spec import EnvironmentSpec, find_envspec
        from dekk.execution.wrapper import WrapperGenerator

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

        python = self._resolve_python(target, python=python, spec=spec)
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

    def uninstall(
        self,
        name: str,
        install_dir: Path | None = None,
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
        install_dir: Path | None = None,
        clean_shell: bool = False,
    ) -> InstallResult:
        """Remove an installed wrapper and optionally remove its PATH entry.

        This is the wrapper/script counterpart to ``install_wrapper``.
        Projects can call it directly to provide their own uninstall command
        on top of dekk's install surface.
        """
        from dekk.execution.wrapper import WrapperGenerator

        result = WrapperGenerator.uninstall(
            name, install_dir=install_dir or self.default_install_dir()
        )
        if clean_shell:
            self._remove_from_shell_config(result.bin_path.parent)
            result.message += MESSAGE_REMOVED_SHELL_CONFIG_ENTRY
        return result

    def default_install_dir(self) -> Path:
        """Return the project-local install directory used by dekk."""
        return self.project_root / DEFAULT_INSTALL_DIRNAME

    def _resolve_python(
        self,
        target: Path,
        *,
        python: Path | None,
        spec: EnvironmentSpec,
    ) -> Path | None:
        """Resolve the interpreter for Python script targets."""
        if python is not None:
            return python.resolve()

        if target.suffix.lower() != PYTHON_SCRIPT_SUFFIX:
            return None

        from dekk.environment.resolver import resolve_environment

        resolved = resolve_environment(spec, project_root=self.project_root)
        dekk_os = get_dekk_os()
        if resolved is not None:
            for candidate in resolved.runtime_paths(dekk_os):
                for executable in dekk_os.python_command_candidates():
                    interpreter = candidate / executable
                    if interpreter.exists():
                        return interpreter

        venv_python = dekk_os.venv_python(self.project_root / PROJECT_VENV_DIRNAME)
        if venv_python.exists():
            return venv_python

        for executable in dekk_os.python_command_candidates():
            if found := shutil.which(executable):
                return Path(found).resolve()

        raise NotFoundError(
            f"No Python interpreter found for {target}",
            hint="Pass --python or create a project environment before installing the wrapper",
        )

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

    def _find_shell_config(self, kind: ShellKind) -> Path | None:
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

    def _with_shell_path_update(
        self, result: InstallResult, *, update_shell: bool
    ) -> InstallResult:
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
        return f"{DEKK_MARKER_PREFIX} {self.project_root.name} {SHELL_CONFIG_ENTRY_SUFFIX}"
