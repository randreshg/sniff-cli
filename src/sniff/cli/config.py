"""Configuration management with TOML support and multi-tier precedence.

Provides a :class:`ConfigManager` that loads configuration from multiple
tiers (user config, project config, environment variables) and supports
reading/writing TOML files with dot-notation access to nested keys.

Tier precedence (highest to lowest):
    1. Environment variables  (``{APP_NAME}_SECTION_KEY``)
    2. Project config         (``.{app_name}/config.toml`` in ancestor dirs)
    3. User config            (``~/.{app_name}/config.toml``)
    4. Built-in defaults      (passed to constructor)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# TOML reading: use stdlib tomllib on 3.11+, fall back to tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

# TOML writing: optional dependency from sniff[cli]
try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]


class ConfigManager:
    """Multi-tier configuration manager with TOML support.

    Loads configuration from user config, project config, and environment
    variables, with higher tiers overriding lower ones.  Supports dot-notation
    for nested key access (e.g. ``"database.path"``).

    Args:
        app_name: Application name used for directory/env-var naming.
        config_file: Config filename within the app config directory.
        defaults: Built-in default values to start with.

    Example::

        cfg = ConfigManager("myapp")
        cfg.set("database.path", "/tmp/db.sqlite")
        cfg.save()                     # writes to ~/.myapp/config.toml
        print(cfg.get("database.path"))  # /tmp/db.sqlite
    """

    def __init__(
        self,
        app_name: str,
        config_file: str = "config.toml",
        defaults: dict[str, Any] | None = None,
    ) -> None:
        self.app_name = app_name
        self.config_file = config_file
        self._defaults: dict[str, Any] = defaults or {}
        self._config: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load config from all tiers (defaults -> user -> project -> env vars).

        Each tier deeply merges into the accumulated config so that
        higher-precedence tiers override individual keys without wiping
        entire sections.
        """
        # Start from built-in defaults
        config: dict[str, Any] = _deep_copy(self._defaults)

        # User config: ~/.{app_name}/config.toml
        user_config = self._user_config_path()
        if user_config.exists():
            _deep_merge(config, _load_toml(user_config))

        # Project config: .{app_name}/config.toml (search ancestors)
        project_config = self._find_project_config()
        if project_config is not None:
            _deep_merge(config, _load_toml(project_config))

        # Environment variables: {APP_NAME}_{KEY}
        _deep_merge(config, self._load_env_vars())

        self._config = config

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation.

        Args:
            key: Dot-separated path (e.g. ``"database.path"``).
            default: Returned when the key is missing.

        Returns:
            The stored value, or *default* if not found.
        """
        parts = key.split(".")
        value: Any = self._config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a config value using dot notation.

        Intermediate dicts are created automatically.

        Args:
            key: Dot-separated path (e.g. ``"database.path"``).
            value: Value to store.
        """
        parts = key.split(".")
        target = self._config
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    def save(self, user: bool = True) -> None:
        """Save the current config to a TOML file.

        Args:
            user: If ``True`` (default), write to the user config directory
                (``~/.{app_name}/config.toml``).  If ``False``, write to the
                project-local directory (``.{app_name}/config.toml`` relative
                to the current working directory).

        Raises:
            RuntimeError: If ``tomli_w`` is not installed.
        """
        if tomli_w is None:
            raise RuntimeError(
                "tomli_w is required for saving config. "
                "Install it with: pip install 'sniff[cli]'"
            )

        if user:
            path = self._user_config_path()
        else:
            path = Path.cwd() / f".{self.app_name}" / self.config_file

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(tomli_w.dumps(self._config).encode())

    def to_dict(self) -> dict[str, Any]:
        """Return the full configuration as a dictionary (shallow copy)."""
        return self._config.copy()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _user_config_path(self) -> Path:
        """Return the user-level config file path."""
        return Path.home() / f".{self.app_name}" / self.config_file

    def _find_project_config(self) -> Path | None:
        """Search ancestor directories for a project config file.

        Walks up from the current working directory looking for
        ``.{app_name}/config.toml``.

        Returns:
            Path to the project config, or ``None`` if not found.
        """
        current = Path.cwd()
        while True:
            config_path = current / f".{self.app_name}" / self.config_file
            if config_path.exists():
                return config_path
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    def _load_env_vars(self) -> dict[str, Any]:
        """Load config overrides from environment variables.

        Variables matching ``{APP_NAME}_*`` are converted to nested keys:
        ``MYAPP_DATABASE_PATH`` becomes ``{"database": {"path": "..."}}``.

        Returns:
            Dict of config values derived from the environment.
        """
        prefix = f"{self.app_name.upper()}_"
        config: dict[str, Any] = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                # Build nested dict from underscore-separated parts
                parts = config_key.split("_")
                target = config
                for part in parts[:-1]:
                    if part not in target or not isinstance(target[part], dict):
                        target[part] = {}
                    target = target[part]
                target[parts[-1]] = value
        return config


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file, returning an empty dict on error."""
    if tomllib is None:
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        return {}


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Recursively merge *source* into *target* in place."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _deep_copy(d: dict[str, Any]) -> dict[str, Any]:
    """Simple deep copy for nested dicts of plain values."""
    result: dict[str, Any] = {}
    for key, value in d.items():
        if isinstance(value, dict):
            result[key] = _deep_copy(value)
        elif isinstance(value, list):
            result[key] = list(value)
        else:
            result[key] = value
    return result
