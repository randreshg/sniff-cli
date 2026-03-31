"""Core sub-package: version, paths, config, context, and commands.

Re-exports all public symbols so that ``from dekk.core import Version`` works.
"""

from dekk.core.commands import (
    CommandMeta,
    CommandProvider,
    CommandRegistry,
    CommandStatus,
    command,
)
from dekk.core.config import ConfigManager, ConfigReconciler, ConfigSource
from dekk.core.context import (
    CPUInfo,
    ContextDiff,
    ContextWorkspaceInfo,
    ExecutionContext,
    GPUInfo,
    GitInfo,
    MemoryInfo,
    SystemLibrary,
)
from dekk.core.paths import (
    DEFAULT_CONFIG_FILE,
    default_project_config_dir,
    find_project_config_file,
    project_config_dir,
    project_config_file,
    site_config_dir,
    site_config_file,
    user_cache_dir,
    user_config_dir,
    user_config_file,
    user_state_dir,
)
from dekk.core.version import (
    Version,
    VersionConstraint,
    VersionSpec,
    compare_versions,
    version_satisfies,
)

__all__ = [
    # commands
    "CommandMeta",
    "CommandProvider",
    "CommandRegistry",
    "CommandStatus",
    "command",
    # config
    "ConfigManager",
    "ConfigReconciler",
    "ConfigSource",
    # context
    "CPUInfo",
    "ContextDiff",
    "ContextWorkspaceInfo",
    "ExecutionContext",
    "GPUInfo",
    "GitInfo",
    "MemoryInfo",
    "SystemLibrary",
    # paths
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
    # version
    "Version",
    "VersionConstraint",
    "VersionSpec",
    "compare_versions",
    "version_satisfies",
]
