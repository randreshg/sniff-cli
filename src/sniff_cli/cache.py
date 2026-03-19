"""Build cache detection -- identify build cache tools and their configuration.

Detects:
  - sccache (Mozilla's shared compilation cache)
  - ccache (compiler cache)
  - Turborepo (Vercel monorepo build cache)
  - Nx (Nrwl monorepo build cache)
  - Bazel (remote/disk cache)

Pure detection -- no side effects, no modifications. Reads environment variables,
checks binary availability, and inspects config files.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CacheKind(Enum):
    SCCACHE = "sccache"
    CCACHE = "ccache"
    TURBOREPO = "turborepo"
    NX = "nx"
    BAZEL = "bazel"


@dataclass(frozen=True)
class BuildCacheInfo:
    """Detected build cache information."""

    kind: CacheKind
    binary_path: str | None = None  # Full path to the cache binary
    version: str | None = None  # Version if cheaply available
    is_enabled: bool = False  # Whether the cache appears actively enabled
    config_path: str | None = None  # Path to config file, if found
    extra: dict[str, str] = field(default_factory=dict)  # Provider-specific metadata


class BuildCacheDetector:
    """Detect build cache tools in the environment.

    Checks binary availability via PATH, environment variables, and config
    file markers. Never runs subprocesses. Never modifies state.
    """

    def __init__(self, project_root: Path | None = None):
        self._project_root = project_root or Path.cwd()

    def detect_all(self) -> list[BuildCacheInfo]:
        """Detect all available build caches.

        Returns:
            List of detected BuildCacheInfo, one per cache found.
            Empty list if no caches are detected.
        """
        results: list[BuildCacheInfo] = []
        for method in (
            self._detect_sccache,
            self._detect_ccache,
            self._detect_turborepo,
            self._detect_nx,
            self._detect_bazel,
        ):
            info = method()
            if info is not None:
                results.append(info)
        return results

    def detect(self, kind: CacheKind) -> BuildCacheInfo | None:
        """Detect a specific build cache.

        Args:
            kind: The cache kind to detect.

        Returns:
            BuildCacheInfo if detected, None otherwise.
        """
        detectors = {
            CacheKind.SCCACHE: self._detect_sccache,
            CacheKind.CCACHE: self._detect_ccache,
            CacheKind.TURBOREPO: self._detect_turborepo,
            CacheKind.NX: self._detect_nx,
            CacheKind.BAZEL: self._detect_bazel,
        }
        return detectors[kind]()

    # ── Individual detectors ─────────────────────────────────────────

    def _detect_sccache(self) -> BuildCacheInfo | None:
        """Detect sccache (shared compilation cache)."""
        binary = shutil.which("sccache")
        env = os.environ

        # sccache is "enabled" if RUSTC_WRAPPER or CC/CXX point to it
        rustc_wrapper = env.get("RUSTC_WRAPPER", "")
        is_enabled = "sccache" in rustc_wrapper

        # Also check if CC/CXX are set to sccache
        if not is_enabled:
            for var in ("CC", "CXX"):
                val = env.get(var, "")
                if "sccache" in val:
                    is_enabled = True
                    break

        if binary is None and not is_enabled:
            return None

        extra: dict[str, str] = {}
        if env.get("SCCACHE_BUCKET"):
            extra["storage"] = "s3"
            extra["bucket"] = env["SCCACHE_BUCKET"]
        elif env.get("SCCACHE_GCS_BUCKET"):
            extra["storage"] = "gcs"
            extra["bucket"] = env["SCCACHE_GCS_BUCKET"]
        elif env.get("SCCACHE_AZURE_CONNECTION_STRING"):
            extra["storage"] = "azure"
        elif env.get("SCCACHE_REDIS"):
            extra["storage"] = "redis"
        elif env.get("SCCACHE_MEMCACHED"):
            extra["storage"] = "memcached"
        elif env.get("SCCACHE_DIR"):
            extra["storage"] = "local"
            extra["dir"] = env["SCCACHE_DIR"]

        config_path = env.get("SCCACHE_CONF")

        return BuildCacheInfo(
            kind=CacheKind.SCCACHE,
            binary_path=binary,
            is_enabled=is_enabled,
            config_path=config_path,
            extra=extra,
        )

    def _detect_ccache(self) -> BuildCacheInfo | None:
        """Detect ccache (compiler cache)."""
        binary = shutil.which("ccache")
        env = os.environ

        # ccache is enabled if CC/CXX contain "ccache" or if it's symlinked
        is_enabled = False
        for var in ("CC", "CXX"):
            val = env.get(var, "")
            if "ccache" in val:
                is_enabled = True
                break

        if binary is None and not is_enabled:
            return None

        extra: dict[str, str] = {}
        if env.get("CCACHE_DIR"):
            extra["dir"] = env["CCACHE_DIR"]
        if env.get("CCACHE_MAXSIZE"):
            extra["max_size"] = env["CCACHE_MAXSIZE"]

        config_path = env.get("CCACHE_CONFIGPATH")
        if config_path is None:
            # Check default location
            default = Path.home() / ".config" / "ccache" / "ccache.conf"
            if default.exists():
                config_path = str(default)

        return BuildCacheInfo(
            kind=CacheKind.CCACHE,
            binary_path=binary,
            is_enabled=is_enabled or binary is not None,
            config_path=config_path,
            extra=extra,
        )

    def _detect_turborepo(self) -> BuildCacheInfo | None:
        """Detect Turborepo build cache."""
        binary = shutil.which("turbo")

        # Check for turbo.json config
        config_path = None
        turbo_json = self._project_root / "turbo.json"
        if turbo_json.exists():
            config_path = str(turbo_json)

        if binary is None and config_path is None:
            return None

        extra: dict[str, str] = {}
        env = os.environ
        if env.get("TURBO_TOKEN"):
            extra["remote_cache"] = "enabled"
        if env.get("TURBO_TEAM"):
            extra["team"] = env["TURBO_TEAM"]
        if env.get("TURBO_API"):
            extra["api"] = env["TURBO_API"]

        return BuildCacheInfo(
            kind=CacheKind.TURBOREPO,
            binary_path=binary,
            is_enabled=binary is not None or config_path is not None,
            config_path=config_path,
            extra=extra,
        )

    def _detect_nx(self) -> BuildCacheInfo | None:
        """Detect Nx build cache."""
        binary = shutil.which("nx")

        # Check for nx.json config
        config_path = None
        nx_json = self._project_root / "nx.json"
        if nx_json.exists():
            config_path = str(nx_json)

        if binary is None and config_path is None:
            return None

        extra: dict[str, str] = {}
        env = os.environ
        if env.get("NX_CLOUD_ACCESS_TOKEN"):
            extra["cloud"] = "enabled"
        if env.get("NX_CACHE_DIRECTORY"):
            extra["cache_dir"] = env["NX_CACHE_DIRECTORY"]

        return BuildCacheInfo(
            kind=CacheKind.NX,
            binary_path=binary,
            is_enabled=binary is not None or config_path is not None,
            config_path=config_path,
            extra=extra,
        )

    def _detect_bazel(self) -> BuildCacheInfo | None:
        """Detect Bazel build cache."""
        binary = shutil.which("bazel") or shutil.which("bazelisk")

        # Check for workspace markers
        config_path = None
        for name in ("WORKSPACE", "WORKSPACE.bazel", "MODULE.bazel"):
            candidate = self._project_root / name
            if candidate.exists():
                config_path = str(candidate)
                break

        if binary is None and config_path is None:
            return None

        extra: dict[str, str] = {}
        env = os.environ

        # Check .bazelrc for disk/remote cache hints
        bazelrc = self._project_root / ".bazelrc"
        if bazelrc.exists():
            extra["bazelrc"] = str(bazelrc)

        if env.get("BAZEL_REMOTE_CACHE"):
            extra["remote_cache"] = env["BAZEL_REMOTE_CACHE"]

        return BuildCacheInfo(
            kind=CacheKind.BAZEL,
            binary_path=binary,
            is_enabled=binary is not None,
            config_path=config_path,
            extra=extra,
        )
