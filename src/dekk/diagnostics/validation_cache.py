"""Fast validation caching for dekk auto-activation.

Performance: <5ms cache hit, <100ms cache miss
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from dekk.core.paths import user_cache_dir

CACHE_TTL = 3600  # 1 hour
DEKK_APP_NAME = "dekk"


@dataclass
class CachedValidation:
    """Cached validation result."""

    timestamp: float
    environment_prefix: str | None
    env_vars: dict[str, str]
    missing_tools: list[str]


class ValidationCache:
    """Fast disk cache for environment validation."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or user_cache_dir(DEKK_APP_NAME)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_file(self, project_path: Path, environment_key: str) -> Path:
        """Get cache file path with readable name.

        Uses a hash of the full resolved project path to avoid collisions
        between projects with the same directory name (e.g. /a/proj vs /b/proj).
        The environment key should uniquely identify the configured environment,
        e.g. the resolved environment prefix path.
        """
        path_hash = hashlib.sha256(
            str(project_path.resolve()).encode()
        ).hexdigest()[:12]
        safe_name = f"{project_path.name}_{path_hash}_{environment_key}"
        safe_name = re.sub(r'[/\\:?*<>"]', "_", safe_name)
        return self.cache_dir / f"{safe_name}.json"

    def get(self, project_path: Path, environment_key: str) -> CachedValidation | None:
        """Get cached validation if still valid."""
        cache_file = self._cache_file(project_path, environment_key)
        if not cache_file.exists():
            return None

        try:
            with open(cache_file) as f:
                data = json.load(f)

            # Check TTL
            if time.time() - data["timestamp"] > CACHE_TTL:
                return None

            return CachedValidation(**data)
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def set(
        self,
        project_path: Path,
        environment_key: str,
        environment_prefix: Path | None,
        env_vars: dict[str, str],
        missing_tools: list[str],
    ) -> None:
        """Cache validation result."""
        cached = CachedValidation(
            timestamp=time.time(),
            environment_prefix=str(environment_prefix) if environment_prefix else None,
            env_vars=env_vars,
            missing_tools=missing_tools,
        )

        cache_file = self._cache_file(project_path, environment_key)
        try:
            with open(cache_file, "w") as f:
                json.dump(asdict(cached), f)
        except OSError:
            pass  # Non-critical


# Lazy module-level singleton — instantiated on first call to get_cache()
# to avoid side-effects (directory creation) at import time.
_cache: ValidationCache | None = None


def get_cache() -> ValidationCache:
    """Get validation cache instance (created on first call)."""
    global _cache  # noqa: PLW0603
    if _cache is None:
        _cache = ValidationCache()
    return _cache
