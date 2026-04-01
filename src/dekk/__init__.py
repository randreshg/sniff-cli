"""
dekk - One config. Zero activation. Any project.

Detect your project's environment, activate it from a .dekk.toml spec,
and generate self-contained wrapper binaries that just work.

All public symbols are lazily loaded on first access via PEP 562 __getattr__.
This means ``import dekk`` is near-instant (<5ms) regardless of which
optional tracking integrations are installed.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

try:
    __version__ = version("dekk")
except PackageNotFoundError:
    __version__ = "1.6.5"

# ---------------------------------------------------------------------------
# Lazy import registry: module_path -> list of exported names
# ---------------------------------------------------------------------------

_MODULE_ATTRS: dict[str, list[str]] = {
    # -- Automatic Environment Setup --
    "dekk.environment.spec": [
        "ComponentSpec",
        "EnvironmentSpec",
        "InstallSpec",
        "ToolSpec",
        "CommandSpec",
        "NpmSpec",
        "AgentsSpec",
        "PythonSpec",
        "RuntimeEnvironmentSpec",
        "WrapSpec",
        "find_envspec",
    ],
    "dekk.environment.types": ["EnvironmentKind"],
    "dekk.environment.providers": ["DekkEnv", "DekkEnvSetupResult", "CondaEnv"],
    # -- Project Setup --
    "dekk.environment.setup": ["SetupResult", "run_setup"],
    # -- Install Pipeline --
    "dekk.environment.install": ["run_install"],
    "dekk.cli.install_runner": [
        "InstallRunner",
        "InstallRunnerResult",
        "StepResult",
        "select_components",
    ],
    # -- Agent Config Management --
    "dekk.agents": [
        "DekkAgent",
        "AgentConfigManager",
        "RuleDefinition",
        "SkillDefinition",
        "create_agents_app",
        "discover_rules",
        "discover_skills",
        "install_codex_skills",
        "parse_frontmatter",
        "scaffold_agents_dir",
    ],
    "dekk.environment.activation": ["EnvironmentActivator", "ActivationResult"],
    "dekk.execution.install": ["BinaryInstaller", "InstallResult"],
    "dekk.execution.wrapper": ["WrapperGenerator"],
    # -- Detection & Platform --
    "dekk.detection.detect": ["PlatformDetector", "PlatformInfo"],
    "dekk.detection.deps": [
        "DependencyChecker",
        "DependencySpec",
        "DependencyResult",
        "ToolChecker",
    ],
    "dekk.detection.conda": [
        "COMMON_INSTALL_PATHS",
        "CondaDetector",
        "CondaEnvironment",
        "CondaValidation",
    ],
    # -- Configuration (core) --
    "dekk.core.config": ["ConfigManager", "ConfigReconciler", "ConfigSource"],
    # -- CI --
    "dekk.detection.ci": ["CIDetector", "CIInfo", "CIProvider", "CIBuildAdvisor", "CIBuildHints"],
    # -- Workspace --
    "dekk.detection.workspace": [
        "WorkspaceDetector",
        "WorkspaceInfo",
        "WorkspaceKind",
        "SubProject",
    ],
    # -- Versioning --
    "dekk.core.version": [
        "Version",
        "VersionSpec",
        "VersionConstraint",
        "compare_versions",
        "version_satisfies",
    ],
    "dekk.detection.version_managers": [
        "VersionManagerDetector",
        "VersionManagerInfo",
        "ManagedVersion",
    ],
    # -- Lockfiles --
    "dekk.detection.lockfile": [
        "LockfileParser",
        "LockfileInfo",
        "LockfileKind",
        "LockedDependency",
    ],
    # -- Compiler & Build --
    "dekk.detection.compiler": [
        "CompilerDetector",
        "CompilerFamily",
        "CompilerInfo",
        "ToolchainInfo",
    ],
    "dekk.detection.build": [
        "BuildSystemDetector",
        "BuildSystemInfo",
        "BuildSystem",
        "BuildTarget",
    ],
    "dekk.detection.cache": ["BuildCacheDetector", "BuildCacheInfo", "CacheKind"],
    # -- Shell --
    "dekk.shell": [
        "ShellDetector",
        "ShellInfo",
        "ShellKind",
        "ActivationScriptBuilder",
        "ActivationConfig",
        "EnvVar",
        "CompletionGenerator",
        "CompletionSpec",
        "PromptHelper",
        "AliasSuggestor",
    ],
    # -- Toolchain --
    "dekk.execution.toolchain": [
        "ToolchainProfile",
        "EnvVarBuilder",
        "CMakeToolchain",
        "CondaToolchain",
    ],
    # -- OS Abstraction --
    "dekk.execution.os": ["DekkOS", "PosixDekkOS", "WindowsDekkOS", "get_dekk_os"],
    # -- Environment --
    "dekk.execution.env": ["EnvSnapshot"],
    # -- Diagnostics --
    "dekk.diagnostics.diagnostic": [
        "DiagnosticReport",
        "DiagnosticCheck",
        "CheckRegistry",
        "DiagnosticRunner",
    ],
    "dekk.diagnostics.formatters": [
        "TextFormatter",
        "JsonFormatter",
        "MarkdownFormatter",
    ],
    "dekk.diagnostics.diagnostic_checks": [
        "PlatformCheck",
        "DependencyCheck",
        "CIEnvironmentCheck",
    ],
    # -- Library Paths --
    "dekk.detection.libpath": ["LibraryPathInfo", "LibraryPathResolver"],
    # -- Commands --
    "dekk.core.commands": [
        "CommandStatus",
        "CommandMeta",
        "CommandProvider",
        "CommandRegistry",
        "command",
    ],
    # -- Validation --
    "dekk.diagnostics.validate": [
        "CheckStatus",
        "CheckResult",
        "ValidationReport",
        "EnvironmentValidator",
    ],
    # -- Remediation --
    "dekk.diagnostics.remediate": [
        "IssueSeverity",
        "FixStatus",
        "DetectedIssue",
        "FixResult",
        "Remediator",
        "RemediatorRegistry",
    ],
    # -- Scaffold --
    "dekk.detection.scaffold": [
        "ProjectLanguage",
        "ProjectFramework",
        "ProjectType",
        "ProjectTypeDetector",
        "FileTemplate",
        "TemplateSet",
        "TemplateRegistry",
        "SetupStep",
        "SetupScript",
        "SetupScriptBuilder",
    ],
    # -- Execution Context --
    "dekk.core.context": [
        "ExecutionContext",
        "ContextWorkspaceInfo",
        "GitInfo",
        "CPUInfo",
        "GPUInfo",
        "MemoryInfo",
        "SystemLibrary",
        "ContextDiff",
    ],
    # -- CLI Framework --
    "dekk.cli.typer_app": ["Typer", "Option", "Argument", "Exit", "Context"],
    # -- CLI Commands --
    "dekk.cli.cli_commands": ["run_doctor", "run_version", "run_env"],
    # -- CLI Styling & Output --
    "dekk.cli.styles": [
        "console",
        "err_console",
        "Colors",
        "Symbols",
        "print_success",
        "print_error",
        "print_warning",
        "print_info",
        "print_debug",
        "print_header",
        "print_step",
        "print_section",
        "print_blank",
        "print_table",
        "print_numbered_list",
        "print_next_steps",
        "PROMPT_TOKENS",
    ],
    # -- CLI Output Formatting --
    "dekk.cli.output": ["OutputFormatter", "OutputFormat", "print_dep_results"],
    # -- CLI Error Handling --
    "dekk.cli.errors": [
        "DekkError",
        "ExitCodes",
        "NotFoundError",
        "ValidationError",
        "ConfigError",
        "DependencyError",
        "DekkTimeoutError",
        "DekkPermissionError",
        "DekkRuntimeError",
    ],
    # -- CLI Progress --
    "dekk.cli.progress": ["progress_bar", "spinner"],
    # -- CLI Runner --
    "dekk.cli.runner": ["RunResult", "run_logged"],
    # -- Project & Worktree --
    "dekk.project": [
        "WorktreeCreateResult",
        "WorktreeInfo",
        "create_worktree",
        "find_git_root",
        "list_worktrees",
        "prune_worktrees",
        "remove_worktree",
        "run_project_command",
    ],
    # -- Script Runner --
    "dekk.execution.runner": ["run_script"],
}

# ---------------------------------------------------------------------------
# Build reverse lookup: name -> module_path
# ---------------------------------------------------------------------------

_ATTR_TO_MODULE: dict[str, str] = {
    name: mod for mod, names in _MODULE_ATTRS.items() for name in names
}

# ---------------------------------------------------------------------------
# PEP 562 lazy loading
# ---------------------------------------------------------------------------


def __getattr__(name: str) -> Any:  # noqa: N807
    if name in _ATTR_TO_MODULE:
        import importlib

        mod_path = _ATTR_TO_MODULE[name]
        module = importlib.import_module(mod_path)
        # Bulk-cache ALL names from this module to avoid repeated __getattr__ calls
        for attr_name in _MODULE_ATTRS[mod_path]:
            try:
                globals()[attr_name] = getattr(module, attr_name)
            except AttributeError:
                pass
        return globals()[name]

    raise AttributeError(f"module 'dekk' has no attribute {name!r}")


def __dir__() -> list[str]:  # noqa: N807
    return list(_ATTR_TO_MODULE.keys()) + ["__version__"]


__all__ = sorted(set(list(_ATTR_TO_MODULE) + ["__version__"]))
