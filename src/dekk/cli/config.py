"""Configuration management with TOML support and multi-tier precedence.

Provides a :class:`ConfigManager` that loads configuration from multiple
tiers (user config, project config, environment variables) and supports
reading/writing TOML files with dot-notation access to nested keys.

Tier precedence (highest to lowest):
    1. Environment variables  (``{APP_NAME}_SECTION_KEY``)
    2. Project config         (``.{app_name}/config.toml`` in ancestor dirs)
    3. User config            (platform-standard user config dir)
    4. Built-in defaults      (passed to constructor)
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from dekk._compat import deep_merge, load_toml
from dekk.core.paths import find_project_config_file, project_config_file, user_config_file

# TOML writing: prefer tomli_w when available, fall back to a small writer.
try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]


DEFAULT_CONFIG_FILE: Final = "config.toml"
KEY_SEPARATOR: Final = "."
ENV_VAR_SEPARATOR: Final = "_"


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
        cfg.save()
        print(cfg.get("database.path"))  # /tmp/db.sqlite
    """

    def __init__(
        self,
        app_name: str,
        config_file: str = DEFAULT_CONFIG_FILE,
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

        # User config: platform-standard user config directory
        user_config = self._user_config_path()
        if user_config.exists():
            config = deep_merge(config, load_toml(user_config) or {})

        # Project config: .{app_name}/config.toml (search ancestors)
        project_config = self._find_project_config()
        if project_config is not None:
            config = deep_merge(config, load_toml(project_config) or {})

        # Environment variables: {APP_NAME}_{KEY}
        config = deep_merge(config, self._load_env_vars())

        self._config = config

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation.

        Args:
            key: Dot-separated path (e.g. ``"database.path"``).
            default: Returned when the key is missing.

        Returns:
            The stored value, or *default* if not found.
        """
        parts = key.split(KEY_SEPARATOR)
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
        parts = key.split(KEY_SEPARATOR)
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
                for the current platform. If ``False``, write to the
                project-local directory (``.{app_name}/config.toml`` relative
                to the current working directory).

        """
        if user:
            path = self._user_config_path()
        else:
            path = project_config_file(self.app_name, config_file=self.config_file)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump_toml(self._config), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        """Return the full configuration as a dictionary (shallow copy)."""
        return self._config.copy()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _user_config_path(self) -> Path:
        """Return the user-level config file path."""
        return user_config_file(self.app_name, self.config_file)

    def _find_project_config(self) -> Path | None:
        """Search ancestor directories for a project config file.

        Walks up from the current working directory looking for
        ``.{app_name}/config.toml``.

        Returns:
            Path to the project config, or ``None`` if not found.
        """
        return find_project_config_file(self.app_name, config_file=self.config_file)

    def _load_env_vars(self) -> dict[str, Any]:
        """Load config overrides from environment variables.

        Variables matching ``{APP_NAME}_*`` are converted to nested keys:
        ``MYAPP_DATABASE_PATH`` becomes ``{"database": {"path": "..."}}``.

        Returns:
            Dict of config values derived from the environment.
        """
        prefix = f"{self.app_name.upper()}{ENV_VAR_SEPARATOR}"
        config: dict[str, Any] = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower()
                # Build nested dict from underscore-separated parts
                parts = config_key.split(ENV_VAR_SEPARATOR)
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


def _dump_toml(data: dict[str, Any]) -> str:
    """Serialize a nested config dict to TOML."""
    if tomli_w is not None:
        return tomli_w.dumps(data)
    return _render_toml_table(data)


def _render_toml_table(table: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> str:
    """Render a TOML table using only stdlib features."""
    lines: list[str] = []
    child_tables: list[tuple[tuple[str, ...], Mapping[str, Any]]] = []

    for key, value in table.items():
        if isinstance(value, Mapping):
            child_tables.append(((*prefix, key), value))
        else:
            lines.append(f"{key} = {_format_toml_value(value)}")

    rendered_sections: list[str] = []
    if prefix:
        header = ".".join(prefix)
        body = "\n".join(lines)
        rendered_sections.append(f"[{header}]\n{body}" if body else f"[{header}]")
    elif lines:
        rendered_sections.append("\n".join(lines))

    for child_prefix, child_table in child_tables:
        rendered_sections.append(_render_toml_table(child_table, child_prefix))

    return "\n\n".join(section for section in rendered_sections if section) + "\n"


def _format_toml_value(value: Any) -> str:
    """Render a scalar TOML value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        inner = ", ".join(_format_toml_value(item) for item in value)
        return f"[{inner}]"
    raise TypeError(f"Unsupported TOML value: {value!r}")


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Recursively merge *source* into *target* in place.

    Thin wrapper kept for backward compatibility; delegates to
    :func:`dekk._compat.deep_merge`.
    """
    merged = deep_merge(target, source)
    target.clear()
    target.update(merged)
