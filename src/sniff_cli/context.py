"""Execution context capture for environment reproducibility.

Captures a complete snapshot of the current execution environment including
platform, conda, CI, workspace, hardware, packages, and runtime state.

Pure detection -- consistent with sniff-cli's philosophy.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final


GIT_DIR_NAME: Final = ".git"
PROJECT_ROOT_MARKERS: Final = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Cargo.toml",
    "package.json",
    "go.mod",
    GIT_DIR_NAME,
)
BUILD_ARTIFACT_DIRS: Final = ("build", "dist", "target", "node_modules", "__pycache__")
WORKSPACE_CONFIG_PATTERNS: Final = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Cargo.toml",
    "package.json",
    "go.mod",
    "Makefile",
    "CMakeLists.txt",
    ".gitignore",
    "tox.ini",
    "pytest.ini",
    ".flake8",
)
UNKNOWN_MODEL: Final = "unknown"
LINUX_PLATFORM: Final = "linux"
DARWIN_PLATFORM: Final = "darwin"
DRM_ROOT_PATH: Final = "/sys/class/drm"
INTEL_VENDOR_ID: Final = "0x8086"


@dataclass(frozen=True)
class GitInfo:
    """Git repository state."""

    commit_sha: str
    branch: str
    is_dirty: bool
    remote_url: str | None


@dataclass(frozen=True)
class ContextWorkspaceInfo:
    """Project workspace information."""

    root: Path
    git_info: GitInfo | None
    build_artifacts: list[Path]
    config_files: list[Path]


@dataclass(frozen=True)
class CPUInfo:
    """CPU information."""

    model: str
    cores: int
    threads: int
    frequency_mhz: float | None


@dataclass(frozen=True)
class GPUInfo:
    """GPU information."""

    vendor: str  # "nvidia" | "amd" | "intel"
    model: str
    memory_mb: int | None
    driver_version: str | None


@dataclass(frozen=True)
class MemoryInfo:
    """System memory information."""

    total_mb: int
    available_mb: int
    used_mb: int


@dataclass(frozen=True)
class SystemLibrary:
    """System library information."""

    name: str
    version: str | None
    path: Path


@dataclass(frozen=True)
class ContextDiff:
    """Differences between two ExecutionContexts."""

    platform_changed: bool
    conda_env_changed: bool
    package_changes: dict[str, tuple[str | None, str | None]]  # name -> (old, new)
    env_var_changes: dict[str, tuple[str | None, str | None]]
    hardware_changes: list[str]
    git_changes: dict[str, Any]

    def is_compatible(self) -> bool:
        """Check if contexts are compatible for reproducibility.

        Compatible means the platform and packages are the same.
        Hardware and env var differences alone do not break compatibility.
        """
        return (
            not self.platform_changed
            and not self.conda_env_changed
            and len(self.package_changes) == 0
        )

    def summary(self) -> str:
        """Human-readable summary of differences."""
        lines: list[str] = []

        if self.platform_changed:
            lines.append("Platform: changed")
        if self.conda_env_changed:
            lines.append("Conda environment: changed")
        if self.package_changes:
            lines.append(f"Package changes: {len(self.package_changes)}")
            for name, (old, new) in sorted(self.package_changes.items()):
                if old is None:
                    lines.append(f"  + {name} {new}")
                elif new is None:
                    lines.append(f"  - {name} {old}")
                else:
                    lines.append(f"  ~ {name} {old} -> {new}")
        if self.env_var_changes:
            lines.append(f"Environment variable changes: {len(self.env_var_changes)}")
        if self.hardware_changes:
            lines.append(f"Hardware changes: {len(self.hardware_changes)}")
            for change in self.hardware_changes:
                lines.append(f"  {change}")
        if self.git_changes:
            lines.append(f"Git changes: {len(self.git_changes)}")
            for key, value in sorted(self.git_changes.items()):
                lines.append(f"  {key}: {value}")

        if not lines:
            return "No differences"
        return "\n".join(lines)


# -- Internal helpers --------------------------------------------------------

def _detect_git_info(root: Path) -> GitInfo | None:
    """Detect git state at the given root. Returns None on failure."""
    git_dir = root / GIT_DIR_NAME
    if not git_dir.exists():
        return None

    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(root), check=False,
        )
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(root), check=False,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, cwd=str(root), check=False,
        )
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, cwd=str(root), check=False,
        )

        commit_sha = sha.stdout.strip() if sha.returncode == 0 else ""
        branch_name = branch.stdout.strip() if branch.returncode == 0 else ""
        is_dirty = bool(dirty.stdout.strip()) if dirty.returncode == 0 else False
        remote_url = remote.stdout.strip() if remote.returncode == 0 and remote.stdout.strip() else None

        return GitInfo(
            commit_sha=commit_sha,
            branch=branch_name,
            is_dirty=is_dirty,
            remote_url=remote_url,
        )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None


def _detect_workspace(working_dir: Path) -> ContextWorkspaceInfo:
    """Detect workspace information from the working directory."""
    root = working_dir

    # Walk up to find project root markers
    current = working_dir
    while current != current.parent:
        for marker in PROJECT_ROOT_MARKERS:
            if (current / marker).exists():
                root = current
                break
        else:
            current = current.parent
            continue
        break

    git_info = _detect_git_info(root)

    # Detect build artifacts
    build_artifacts: list[Path] = []
    for d in BUILD_ARTIFACT_DIRS:
        p = root / d
        try:
            if p.is_dir():
                build_artifacts.append(p)
        except OSError:
            pass

    # Detect config files
    config_files: list[Path] = []
    for name in WORKSPACE_CONFIG_PATTERNS:
        p = root / name
        try:
            if p.is_file():
                config_files.append(p)
        except OSError:
            pass

    return ContextWorkspaceInfo(
        root=root,
        git_info=git_info,
        build_artifacts=build_artifacts,
        config_files=config_files,
    )


def _detect_cpu_info() -> CPUInfo:
    """Detect CPU information using psutil or /proc fallback."""
    model = UNKNOWN_MODEL
    cores = os.cpu_count() or 1
    threads = cores
    frequency_mhz: float | None = None

    try:
        import psutil

        cores = psutil.cpu_count(logical=False) or cores
        threads = psutil.cpu_count(logical=True) or threads
        freq = psutil.cpu_freq()
        if freq:
            frequency_mhz = freq.current
    except ImportError:
        # Fallback to /proc/cpuinfo on Linux
        if sys.platform == LINUX_PLATFORM:
            try:
                with open("/proc/cpuinfo") as f:
                    content = f.read()
                # Count physical cores
                physical_ids = set()
                core_ids = set()
                current_physical = None
                for line in content.splitlines():
                    if line.startswith("physical id"):
                        current_physical = line.split(":")[1].strip()
                        physical_ids.add(current_physical)
                    elif line.startswith("core id") and current_physical is not None:
                        core_ids.add((current_physical, line.split(":")[1].strip()))
                if core_ids:
                    cores = len(core_ids)
                # Count logical processors
                processor_count = content.count("processor\t:")
                if processor_count > 0:
                    threads = processor_count
            except OSError:
                pass

    # Detect CPU model
    if sys.platform == LINUX_PLATFORM:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        model = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass
    elif sys.platform == DARWIN_PLATFORM:
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                model = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        model = platform.processor() or UNKNOWN_MODEL

    return CPUInfo(
        model=model,
        cores=cores,
        threads=threads,
        frequency_mhz=frequency_mhz,
    )


def _detect_nvidia_gpus() -> list[GPUInfo]:
    """Detect NVIDIA GPUs via nvidia-smi."""
    import shutil

    if not shutil.which("nvidia-smi"):
        return []

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            return []

        gpus: list[GPUInfo] = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                mem: int | None = None
                try:
                    mem = int(float(parts[1]))
                except (ValueError, IndexError):
                    pass
                gpus.append(GPUInfo(
                    vendor="nvidia",
                    model=parts[0],
                    memory_mb=mem,
                    driver_version=parts[2] if parts[2] else None,
                ))
        return gpus
    except (OSError, subprocess.TimeoutExpired):
        return []


def _detect_amd_gpus() -> list[GPUInfo]:
    """Detect AMD GPUs via rocm-smi."""
    import shutil

    if not shutil.which("rocm-smi"):
        return []

    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--csv"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            # Try simpler fallback
            result2 = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if result2.returncode != 0:
                return []
            gpus: list[GPUInfo] = []
            for line in result2.stdout.strip().splitlines():
                line = line.strip()
                if line and not line.startswith("=") and "GPU" not in line.split()[0:1]:
                    gpus.append(GPUInfo(
                        vendor="amd",
                        model=line,
                        memory_mb=None,
                        driver_version=None,
                    ))
            return gpus

        gpus = []
        for line in result.stdout.strip().splitlines():
            if line.startswith("device") or line.startswith("="):
                continue
            parts = [p.strip() for p in line.split(",")]
            if parts:
                gpus.append(GPUInfo(
                    vendor="amd",
                    model=parts[0] if parts else "unknown",
                    memory_mb=None,
                    driver_version=None,
                ))
        return gpus
    except (OSError, subprocess.TimeoutExpired):
        return []


def _detect_intel_gpus() -> list[GPUInfo]:
    """Detect Intel GPUs via sysfs."""
    gpus: list[GPUInfo] = []
    drm_path = Path(DRM_ROOT_PATH)
    if not drm_path.exists():
        return gpus

    try:
        for card_dir in sorted(drm_path.iterdir()):
            if not card_dir.name.startswith("card") or "-" in card_dir.name:
                continue
            device_dir = card_dir / "device"
            vendor_path = device_dir / "vendor"
            if not vendor_path.exists():
                continue
            try:
                vendor_id = vendor_path.read_text().strip()
                if vendor_id == INTEL_VENDOR_ID:
                    model = "Intel GPU"
                    label_path = device_dir / "label"
                    if label_path.exists():
                        model = label_path.read_text().strip()
                    gpus.append(GPUInfo(
                        vendor="intel",
                        model=model,
                        memory_mb=None,
                        driver_version=None,
                    ))
            except OSError:
                continue
    except OSError:
        pass

    return gpus


def _detect_gpus() -> list[GPUInfo]:
    """Detect all GPUs."""
    gpus: list[GPUInfo] = []
    gpus.extend(_detect_nvidia_gpus())
    gpus.extend(_detect_amd_gpus())
    gpus.extend(_detect_intel_gpus())
    return gpus


def _detect_memory_info() -> MemoryInfo:
    """Detect system memory information."""
    try:
        import psutil

        mem = psutil.virtual_memory()
        return MemoryInfo(
            total_mb=int(mem.total / (1024 * 1024)),
            available_mb=int(mem.available / (1024 * 1024)),
            used_mb=int(mem.used / (1024 * 1024)),
        )
    except ImportError:
        pass

    # Fallback to /proc/meminfo on Linux
    if sys.platform == "linux":
        try:
            with open("/proc/meminfo") as f:
                info: dict[str, int] = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        try:
                            # Values in /proc/meminfo are in kB
                            info[key] = int(parts[1])
                        except ValueError:
                            pass

                total_kb = info.get("MemTotal", 0)
                avail_kb = info.get("MemAvailable", info.get("MemFree", 0))
                used_kb = total_kb - avail_kb

                return MemoryInfo(
                    total_mb=total_kb // 1024,
                    available_mb=avail_kb // 1024,
                    used_mb=used_kb // 1024,
                )
        except OSError:
            pass

    # Fallback to sysctl on macOS
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                total_bytes = int(result.stdout.strip())
                total_mb = total_bytes // (1024 * 1024)
                return MemoryInfo(
                    total_mb=total_mb,
                    available_mb=0,
                    used_mb=0,
                )
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass

    return MemoryInfo(total_mb=0, available_mb=0, used_mb=0)


def _detect_installed_packages() -> dict[str, str]:
    """Detect installed Python packages via importlib.metadata."""
    try:
        from importlib.metadata import distributions

        packages: dict[str, str] = {}
        for dist in distributions():
            name = dist.metadata.get("Name")
            version = dist.metadata.get("Version")
            if name and version:
                packages[name] = version
        return packages
    except Exception:
        return {}


def _path_to_str(p: Path) -> str:
    return str(p)


def _serialize_value(obj: Any) -> Any:
    """Convert values to JSON-serializable form."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _serialize_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_value(item) for item in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _serialize_value(v) for k, v in asdict(obj).items()}
    return obj


# -- ExecutionContext --------------------------------------------------------

@dataclass(frozen=True)
class ExecutionContext:
    """Complete execution environment snapshot.

    This is the PRIMARY interface for CLI applications.
    Captures everything needed for reproducibility.
    """

    # Core environment
    platform: Any  # PlatformInfo
    conda_env: Any | None  # CondaEnvironment | None
    ci_info: Any  # CIInfo

    # Workspace
    workspace: ContextWorkspaceInfo
    build_system: Any | None  # BuildSystemInfo | None

    # Dependencies
    installed_packages: dict[str, str]  # name -> version
    system_libraries: list[SystemLibrary]

    # Hardware
    cpu_info: CPUInfo
    gpu_info: list[GPUInfo]
    memory_info: MemoryInfo

    # Runtime
    env_vars: dict[str, str]
    command_line: list[str]
    working_dir: Path
    timestamp: datetime

    @classmethod
    def capture(
        cls,
        *,
        include_env_vars: bool = True,
        include_packages: bool = True,
        include_hardware: bool = True,
    ) -> ExecutionContext:
        """Capture current execution context.

        Args:
            include_env_vars: Include environment variables in the snapshot.
            include_packages: Include installed Python packages.
            include_hardware: Include CPU/GPU/memory information.

        Returns:
            Complete ExecutionContext snapshot.
        """
        from sniff_cli.detect import PlatformDetector
        from sniff_cli.conda import CondaDetector
        from sniff_cli.ci import CIDetector

        platform_info = PlatformDetector().detect()
        conda_env = CondaDetector().find_active()
        ci_info = CIDetector().detect()

        working_dir = Path.cwd()
        workspace = _detect_workspace(working_dir)

        # Build system detection
        build_system = None
        try:
            from sniff_cli.build import BuildSystemDetector

            detector = BuildSystemDetector()
            build_system = detector.detect_first(workspace.root)
        except Exception:
            pass

        # Packages
        installed_packages: dict[str, str] = {}
        if include_packages:
            installed_packages = _detect_installed_packages()

        # Hardware
        if include_hardware:
            cpu_info = _detect_cpu_info()
            gpu_info = _detect_gpus()
            memory_info = _detect_memory_info()
        else:
            cpu_info = CPUInfo(model="unknown", cores=0, threads=0, frequency_mhz=None)
            gpu_info = []
            memory_info = MemoryInfo(total_mb=0, available_mb=0, used_mb=0)

        # Environment variables
        env_vars: dict[str, str] = {}
        if include_env_vars:
            env_vars = dict(os.environ)

        return cls(
            platform=platform_info,
            conda_env=conda_env,
            ci_info=ci_info,
            workspace=workspace,
            build_system=build_system,
            installed_packages=installed_packages,
            system_libraries=[],
            cpu_info=cpu_info,
            gpu_info=gpu_info,
            memory_info=memory_info,
            env_vars=env_vars,
            command_line=list(sys.argv),
            working_dir=working_dir,
            timestamp=datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result: dict[str, Any] = {}

        # Platform
        if hasattr(self.platform, "__dataclass_fields__"):
            result["platform"] = _serialize_value(asdict(self.platform))
        else:
            result["platform"] = str(self.platform)

        # Conda
        if self.conda_env is not None and hasattr(self.conda_env, "__dataclass_fields__"):
            result["conda_env"] = _serialize_value(asdict(self.conda_env))
        else:
            result["conda_env"] = None

        # CI
        if hasattr(self.ci_info, "__dataclass_fields__"):
            result["ci_info"] = _serialize_value(asdict(self.ci_info))
        else:
            result["ci_info"] = str(self.ci_info)

        # Workspace
        ws = {
            "root": str(self.workspace.root),
            "git_info": None,
            "build_artifacts": [str(p) for p in self.workspace.build_artifacts],
            "config_files": [str(p) for p in self.workspace.config_files],
        }
        if self.workspace.git_info is not None:
            ws["git_info"] = asdict(self.workspace.git_info)
        result["workspace"] = ws

        # Build system
        if self.build_system is not None and hasattr(self.build_system, "__dataclass_fields__"):
            result["build_system"] = _serialize_value(asdict(self.build_system))
        else:
            result["build_system"] = None

        # Dependencies
        result["installed_packages"] = dict(self.installed_packages)
        result["system_libraries"] = [
            _serialize_value(asdict(lib)) for lib in self.system_libraries
        ]

        # Hardware
        result["cpu_info"] = asdict(self.cpu_info)
        result["gpu_info"] = [asdict(g) for g in self.gpu_info]
        result["memory_info"] = asdict(self.memory_info)

        # Runtime
        result["env_vars"] = dict(self.env_vars)
        result["command_line"] = list(self.command_line)
        result["working_dir"] = str(self.working_dir)
        result["timestamp"] = self.timestamp.isoformat()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionContext:
        """Reconstruct ExecutionContext from a dict (e.g. JSON-deserialized).

        Note: Platform, conda_env, ci_info, and build_system are stored
        as plain dicts since we cannot reconstruct frozen dataclass instances
        from other modules without coupling.
        """
        # Workspace
        ws_data = data.get("workspace", {})
        git_info = None
        if ws_data.get("git_info"):
            gi = ws_data["git_info"]
            git_info = GitInfo(
                commit_sha=gi.get("commit_sha", ""),
                branch=gi.get("branch", ""),
                is_dirty=gi.get("is_dirty", False),
                remote_url=gi.get("remote_url"),
            )

        workspace = ContextWorkspaceInfo(
            root=Path(ws_data.get("root", ".")),
            git_info=git_info,
            build_artifacts=[Path(p) for p in ws_data.get("build_artifacts", [])],
            config_files=[Path(p) for p in ws_data.get("config_files", [])],
        )

        # CPU info
        cpu_data = data.get("cpu_info", {})
        cpu_info = CPUInfo(
            model=cpu_data.get("model", "unknown"),
            cores=cpu_data.get("cores", 0),
            threads=cpu_data.get("threads", 0),
            frequency_mhz=cpu_data.get("frequency_mhz"),
        )

        # GPU info
        gpu_info = [
            GPUInfo(
                vendor=g.get("vendor", "unknown"),
                model=g.get("model", "unknown"),
                memory_mb=g.get("memory_mb"),
                driver_version=g.get("driver_version"),
            )
            for g in data.get("gpu_info", [])
        ]

        # Memory info
        mem_data = data.get("memory_info", {})
        memory_info = MemoryInfo(
            total_mb=mem_data.get("total_mb", 0),
            available_mb=mem_data.get("available_mb", 0),
            used_mb=mem_data.get("used_mb", 0),
        )

        # System libraries
        system_libraries = [
            SystemLibrary(
                name=lib.get("name", ""),
                version=lib.get("version"),
                path=Path(lib.get("path", "")),
            )
            for lib in data.get("system_libraries", [])
        ]

        # Timestamp
        ts_str = data.get("timestamp")
        if ts_str:
            timestamp = datetime.fromisoformat(ts_str)
        else:
            timestamp = datetime.now(timezone.utc)

        return cls(
            platform=data.get("platform", {}),
            conda_env=data.get("conda_env"),
            ci_info=data.get("ci_info", {}),
            workspace=workspace,
            build_system=data.get("build_system"),
            installed_packages=data.get("installed_packages", {}),
            system_libraries=system_libraries,
            cpu_info=cpu_info,
            gpu_info=gpu_info,
            memory_info=memory_info,
            env_vars=data.get("env_vars", {}),
            command_line=data.get("command_line", []),
            working_dir=Path(data.get("working_dir", ".")),
            timestamp=timestamp,
        )

    def fingerprint(self) -> str:
        """Generate reproducibility fingerprint (SHA-256).

        The fingerprint is based on platform, packages, conda env,
        and workspace git state -- the factors that affect reproducibility.
        """
        h = hashlib.sha256()

        # Platform
        if hasattr(self.platform, "__dataclass_fields__"):
            h.update(json.dumps(_serialize_value(asdict(self.platform)), sort_keys=True).encode())
        else:
            h.update(json.dumps(self.platform, sort_keys=True, default=str).encode())

        # Conda
        if self.conda_env is not None:
            if hasattr(self.conda_env, "__dataclass_fields__"):
                h.update(json.dumps(_serialize_value(asdict(self.conda_env)), sort_keys=True).encode())
            else:
                h.update(json.dumps(self.conda_env, sort_keys=True, default=str).encode())

        # Packages
        h.update(json.dumps(self.installed_packages, sort_keys=True).encode())

        # Git state
        if self.workspace.git_info is not None:
            gi = self.workspace.git_info
            h.update(f"{gi.commit_sha}:{gi.branch}:{gi.is_dirty}".encode())

        return h.hexdigest()

    def diff(self, other: ExecutionContext) -> ContextDiff:
        """Compare two contexts, return differences."""
        # Platform comparison
        platform_changed = False
        if hasattr(self.platform, "__dataclass_fields__") and hasattr(other.platform, "__dataclass_fields__"):
            platform_changed = asdict(self.platform) != asdict(other.platform)
        else:
            platform_changed = self.platform != other.platform

        # Conda comparison
        conda_env_changed = False
        if self.conda_env is None and other.conda_env is None:
            conda_env_changed = False
        elif self.conda_env is None or other.conda_env is None:
            conda_env_changed = True
        elif hasattr(self.conda_env, "__dataclass_fields__") and hasattr(other.conda_env, "__dataclass_fields__"):
            conda_env_changed = asdict(self.conda_env) != asdict(other.conda_env)
        else:
            conda_env_changed = self.conda_env != other.conda_env

        # Package changes
        package_changes: dict[str, tuple[str | None, str | None]] = {}
        all_pkg_names = set(self.installed_packages) | set(other.installed_packages)
        for name in all_pkg_names:
            old_ver = self.installed_packages.get(name)
            new_ver = other.installed_packages.get(name)
            if old_ver != new_ver:
                package_changes[name] = (old_ver, new_ver)

        # Env var changes
        env_var_changes: dict[str, tuple[str | None, str | None]] = {}
        all_env_keys = set(self.env_vars) | set(other.env_vars)
        for key in all_env_keys:
            old_val = self.env_vars.get(key)
            new_val = other.env_vars.get(key)
            if old_val != new_val:
                env_var_changes[key] = (old_val, new_val)

        # Hardware changes
        hardware_changes: list[str] = []
        if asdict(self.cpu_info) != asdict(other.cpu_info):
            hardware_changes.append(f"CPU: {self.cpu_info.model} -> {other.cpu_info.model}")
        if asdict(self.memory_info) != asdict(other.memory_info):
            hardware_changes.append(
                f"Memory: {self.memory_info.total_mb}MB -> {other.memory_info.total_mb}MB"
            )
        self_gpu_models = sorted(g.model for g in self.gpu_info)
        other_gpu_models = sorted(g.model for g in other.gpu_info)
        if self_gpu_models != other_gpu_models:
            hardware_changes.append(
                f"GPU: {self_gpu_models} -> {other_gpu_models}"
            )

        # Git changes
        git_changes: dict[str, Any] = {}
        self_git = self.workspace.git_info
        other_git = other.workspace.git_info
        if self_git is None and other_git is not None:
            git_changes["status"] = "added"
        elif self_git is not None and other_git is None:
            git_changes["status"] = "removed"
        elif self_git is not None and other_git is not None:
            if self_git.commit_sha != other_git.commit_sha:
                git_changes["commit_sha"] = (self_git.commit_sha, other_git.commit_sha)
            if self_git.branch != other_git.branch:
                git_changes["branch"] = (self_git.branch, other_git.branch)
            if self_git.is_dirty != other_git.is_dirty:
                git_changes["is_dirty"] = (self_git.is_dirty, other_git.is_dirty)

        return ContextDiff(
            platform_changed=platform_changed,
            conda_env_changed=conda_env_changed,
            package_changes=package_changes,
            env_var_changes=env_var_changes,
            hardware_changes=hardware_changes,
            git_changes=git_changes,
        )
