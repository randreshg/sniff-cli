"""Shared filesystem path policy for dekk-owned app directories."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from platformdirs import site_config_path, user_cache_path, user_config_path, user_state_path

from dekk._compat import walk_up

APP_AUTHOR: Final = False
DEFAULT_CONFIG_FILE: Final = "config.toml"
PROJECT_CONFIG_DIR_PREFIX: Final = "."


def default_project_config_dir(app_name: str) -> str:
    """Return the default project-local config directory name."""
    return f"{PROJECT_CONFIG_DIR_PREFIX}{app_name}"


def user_config_dir(app_name: str) -> Path:
    """Return the standard user config directory for *app_name*."""
    return user_config_path(app_name, appauthor=APP_AUTHOR)


def user_config_file(app_name: str, config_file: str = DEFAULT_CONFIG_FILE) -> Path:
    """Return the user config file path for *app_name*."""
    return user_config_dir(app_name) / config_file


def site_config_dir(app_name: str) -> Path:
    """Return the standard site-wide config directory for *app_name*."""
    return site_config_path(app_name, appauthor=APP_AUTHOR)


def site_config_file(app_name: str, config_file: str = DEFAULT_CONFIG_FILE) -> Path:
    """Return the site-wide config file path for *app_name*."""
    return site_config_dir(app_name) / config_file


def user_cache_dir(app_name: str) -> Path:
    """Return the standard user cache directory for *app_name*."""
    return user_cache_path(app_name, appauthor=APP_AUTHOR)


def user_state_dir(app_name: str) -> Path:
    """Return the standard user state directory for *app_name*."""
    return user_state_path(app_name, appauthor=APP_AUTHOR)


def project_config_dir(
    app_name: str,
    *,
    start_dir: Path | None = None,
    config_dir_name: str | None = None,
) -> Path:
    """Return the project-local config directory path."""
    base = _normalize_start_dir(start_dir)
    return base / (config_dir_name or default_project_config_dir(app_name))


def project_config_file(
    app_name: str,
    *,
    start_dir: Path | None = None,
    config_file: str = DEFAULT_CONFIG_FILE,
    config_dir_name: str | None = None,
) -> Path:
    """Return the project-local config file path."""
    return project_config_dir(
        app_name,
        start_dir=start_dir,
        config_dir_name=config_dir_name,
    ) / config_file


def find_project_config_file(
    app_name: str,
    *,
    start_dir: Path | None = None,
    config_file: str = DEFAULT_CONFIG_FILE,
    config_dir_name: str | None = None,
) -> Path | None:
    """Walk upward from *start_dir* to find a project-local config file."""
    marker = str(Path(config_dir_name or default_project_config_dir(app_name)) / config_file)
    return walk_up(_normalize_start_dir(start_dir), marker)


def _normalize_start_dir(start_dir: Path | None) -> Path:
    """Normalize a starting point into a directory."""
    base = Path.cwd() if start_dir is None else Path(start_dir)
    resolved = base.resolve()
    return resolved.parent if resolved.is_file() else resolved


__all__ = [
    "DEFAULT_CONFIG_FILE",
    "default_project_config_dir",
    "find_project_config_file",
    "project_config_dir",
    "project_config_file",
    "site_config_dir",
    "site_config_file",
    "user_cache_dir",
    "user_config_dir",
    "user_config_file",
    "user_state_dir",
]
