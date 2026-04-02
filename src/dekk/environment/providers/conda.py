"""Conda runtime environment provider."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from dekk.environment.spec import ToolSpec

from dekk.environment.providers.base import DekkEnv, DekkEnvSetupResult, ProgressCallback
from dekk.environment.types import EnvironmentKind
from dekk.execution.os import DekkOS, get_dekk_os
from dekk.execution.toolchain import CMakeToolchain, CondaToolchain, EnvVarBuilder

CONDA_FORGE_CHANNEL: Final = "conda-forge"
_PASSTHROUGH_ENV_VARS: Final = (
    "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
    "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS",
    "NPM_CONFIG_REGISTRY", "USERPROFILE",
)
CONDA_COMMANDS: Final = ("mamba", "conda")
CONDA_METADATA_DIRNAME: Final = "conda-meta"
PATH_ENV_NAME: Final = "PATH"
HOME_ENV_NAME: Final = "HOME"
CMAKE_TOOL_NAME: Final = "cmake"


class CondaEnv(DekkEnv):
    """Conda-backed runtime environment."""

    def __init__(
        self,
        *,
        prefix: Path,
        file: str | None = None,
        name: str | None = None,
        channels: list[str] | None = None,
        packages: dict[str, str] | None = None,
        pip: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            kind=EnvironmentKind.CONDA, prefix=prefix, file=file, name=name,
            channels=channels, packages=packages, pip=pip,
        )

    def exists(self) -> bool:
        return self.prefix.is_dir() and (self.prefix / CONDA_METADATA_DIRNAME).is_dir()

    def runtime_paths(self, os_strategy: DekkOS) -> tuple[Path, ...]:
        return os_strategy.conda_runtime_paths(self.prefix)

    def _generate_env_file(self, output_path: Path) -> Path:
        """Write conda env YAML from inline packages. Returns the file path."""
        assert self.packages, "_generate_env_file requires packages"
        lines = [f"name: {self.name or 'dekk-env'}"]
        lines.append("channels:")
        for ch in self.channels:
            lines.append(f"  - {ch}")
        lines.append("dependencies:")
        for pkg, version in self.packages.items():
            if version:
                lines.append(f"  - {pkg}={version}")
            else:
                lines.append(f"  - {pkg}")
        if self.pip:
            lines.append("  - pip:")
            for pkg, version in self.pip.items():
                spec = f"{pkg}{version}" if version else pkg
                lines.append(f"      - {spec}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output_path

    def configure(
        self,
        builder: EnvVarBuilder,
        *,
        project_name: str,
        tools: Mapping[str, ToolSpec],
    ) -> None:
        CondaToolchain(self.prefix, project_name).configure(builder)
        if any(tool_name.lower() == CMAKE_TOOL_NAME for tool_name in tools):
            CMakeToolchain(self.prefix).configure(builder)

    def get_setup_command(
        self, *, project_root: Path, force: bool = False
    ) -> str | None:
        from dekk.cli.errors import DependencyError, NotFoundError

        conda_cmd = _find_conda_cmd()
        if not conda_cmd:
            raise DependencyError(
                "conda/mamba not found on PATH",
                hint="Install mamba: https://mamba.readthedocs.io/en/latest/installation.html",
            )

        existing = self.exists()
        if existing and not force:
            return None  # only valid skip — env already exists

        if self.file:
            env_file_path = project_root / self.file
            if not env_file_path.is_file():
                raise NotFoundError(f"Environment file not found: {env_file_path}")
        elif self.packages:
            env_file_path = self._generate_env_file(project_root / ".dekk" / "environment.yaml")
        else:
            # No file, no packages — bare create
            cmd = [conda_cmd, "create", "-p", str(self.prefix), "-c", CONDA_FORGE_CHANNEL, "-y"]
            import shlex
            return shlex.join(cmd)

        # File-based create/update (works for both external and generated)
        if existing:
            cmd = [
                conda_cmd, "env", "update",
                "-p", str(self.prefix), "-f", str(env_file_path), "-y",
            ]
        else:
            cmd = [
                conda_cmd, "env", "create",
                "-p", str(self.prefix), "-f", str(env_file_path), "-y",
            ]
            if force:
                cmd.append("--force")

        import shlex
        return shlex.join(cmd)

    def setup(
        self,
        *,
        project_root: Path,
        force: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> DekkEnvSetupResult:
        conda_cmd = _find_conda_cmd()
        if not conda_cmd:
            return DekkEnvSetupResult(errors=["conda/mamba not found on PATH"])

        existing = self.exists()
        if existing and not force:
            return DekkEnvSetupResult(prefix=self.prefix)

        errors: list[str] = []
        if self.file:
            env_file_path = project_root / self.file
            if not env_file_path.is_file():
                return DekkEnvSetupResult(
                    errors=[f"Environment file not found: {env_file_path}"]
                )
        elif self.packages:
            env_file_path = self._generate_env_file(project_root / ".dekk" / "environment.yaml")
        else:
            env_file_path = None

        if env_file_path:
            if existing:
                cmd = [
                    conda_cmd, "env", "update",
                    "-p", str(self.prefix), "-f", str(env_file_path),
                ]
            else:
                cmd = [
                    conda_cmd, "env", "create",
                    "-p", str(self.prefix), "-f", str(env_file_path),
                ]
                if force:
                    cmd.append("--force")
        else:
            cmd = [
                conda_cmd, "create",
                "-p", str(self.prefix), "-c", CONDA_FORGE_CHANNEL, "-y",
            ]

        try:
            if on_progress:
                returncode, output_tail = _run_conda_streaming(
                    cmd, cwd=project_root, on_progress=on_progress,
                )
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                    cwd=project_root,
                )
                returncode = result.returncode
                output_tail = result.stderr.strip()
            if returncode != 0:
                errors.append(
                    f"{self.type_name} create failed: {output_tail[:500]}"
                )
                return DekkEnvSetupResult(errors=errors)
        except subprocess.TimeoutExpired:
            return DekkEnvSetupResult(
                errors=[f"{self.type_name} create timed out (10 minutes)"]
            )
        except OSError as exc:
            return DekkEnvSetupResult(
                errors=[f"Failed to run {conda_cmd}: {exc}"]
            )

        return DekkEnvSetupResult(
            prefix=self.prefix if self.exists() else None,
            created=not existing,
            errors=errors,
        )

    def install_npm_packages(self, packages: Mapping[str, str]) -> tuple[list[str], list[str]]:
        """Install npm packages globally into this runtime environment."""
        os_strategy = get_dekk_os()
        npm_bin = _find_runtime_executable(
            self.prefix, os_strategy.npm_command_candidates(), os_strategy
        )
        if npm_bin is None:
            return [], [
                f"npm not found in {self.type_name} runtime paths"
                " — add nodejs to environment packages"
            ]

        runtime_paths = os_strategy.conda_runtime_paths(self.prefix)
        runtime_path = os_strategy.path_separator.join(str(path) for path in runtime_paths)
        inherited_path = os.environ.get(PATH_ENV_NAME, "")
        env = {
            PATH_ENV_NAME: (
                f"{runtime_path}{os_strategy.path_separator}{inherited_path}"
                if inherited_path
                else runtime_path
            ),
            HOME_ENV_NAME: str(Path.home()),
        }
        for var in _PASSTHROUGH_ENV_VARS:
            value = os.environ.get(var)
            if value is not None:
                env[var] = value
        installed: list[str] = []
        errors: list[str] = []

        for name, version in packages.items():
            pkg_spec = f"{name}@{version}" if version and version != "latest" else name
            cmd = [str(npm_bin), "install", "-g", pkg_spec]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                    env=env,
                )
                if result.returncode != 0:
                    errors.append(f"npm install {pkg_spec} failed: {result.stderr.strip()[:300]}")
                else:
                    installed.append(name)
            except subprocess.TimeoutExpired:
                errors.append(f"npm install {pkg_spec} timed out")
            except OSError as exc:
                errors.append(f"Failed to run npm: {exc}")

        return installed, errors


def _find_conda_cmd() -> str | None:
    for cmd in CONDA_COMMANDS:
        if shutil.which(cmd):
            return cmd
    return None


_CONDA_PHASES: Final[list[tuple[str, str]]] = [
    ("collecting package metadata", "Resolving packages..."),
    ("looking for", "Resolving packages..."),
    ("solving environment", "Solving environment..."),
    ("downloading and extracting", "Downloading packages..."),
    ("downloading ", "Downloading packages..."),
    ("extracting ", "Extracting packages..."),
    ("preparing transaction", "Linking packages..."),
    ("linking ", "Linking packages..."),
    ("verifying transaction", "Verifying..."),
    ("executing transaction", "Installing packages..."),
]


def _parse_conda_phase(line: str) -> str | None:
    """Extract a user-friendly phase message from conda/mamba output."""
    low = line.strip().lower()
    if not low:
        return None
    for trigger, phase in _CONDA_PHASES:
        if trigger in low:
            return phase
    return None


def _run_conda_streaming(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    on_progress: ProgressCallback,
) -> tuple[int, str]:
    """Run a conda/mamba command, streaming output for phase detection.

    Returns ``(returncode, tail_output)`` for error reporting.
    Only called when a progress callback is provided — the non-streaming
    path uses ``subprocess.run()`` directly.
    """
    from collections import deque

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
    )

    last_phase: str | None = None
    tail: deque[str] = deque(maxlen=20)

    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                tail.append(line.rstrip("\n"))
                phase = _parse_conda_phase(line)
                if phase and phase != last_phase:
                    last_phase = phase
                    on_progress(phase)
        returncode = proc.wait()
    except BaseException:
        proc.kill()
        proc.wait()
        raise

    return returncode, "\n".join(tail)


def _find_runtime_executable(
    prefix: Path, candidates: tuple[str, ...], os_strategy: DekkOS
) -> Path | None:
    for runtime_dir in os_strategy.conda_runtime_paths(prefix):
        for candidate in candidates:
            executable = runtime_dir / candidate
            if executable.is_file():
                return executable
    return None


def create_conda_env(
    *,
    prefix: Path,
    file: str | None = None,
    name: str | None = None,
    channels: list[str] | None = None,
    packages: dict[str, str] | None = None,
    pip: dict[str, str] | None = None,
) -> CondaEnv:
    """Construct a `CondaEnv` from resolved spec values."""
    return CondaEnv(
        prefix=prefix, file=file, name=name,
        channels=channels, packages=packages, pip=pip,
    )


__all__ = ["CondaEnv", "create_conda_env"]
