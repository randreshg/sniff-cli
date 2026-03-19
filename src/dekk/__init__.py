"""
dekk - One config. Zero activation. Any project.

Detect your project's environment, activate it from a .dekk.toml spec,
and generate self-contained wrapper binaries that just work.

All public symbols are lazily loaded on first access via PEP 562 __getattr__.
This means ``import dekk`` is near-instant (<5ms) regardless of which
optional tracking integrations are installed.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dekk")
except PackageNotFoundError:
    __version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Lazy import registry: module_path -> list of exported names
# ---------------------------------------------------------------------------

_MODULE_ATTRS: dict[str, list[str]] = {
    # -- Automatic Environment Setup --
    "dekk.envspec": ["EnvironmentSpec", "CondaSpec", "ToolSpec", "find_envspec"],
    "dekk.activation": ["EnvironmentActivator", "ActivationResult"],
    "dekk.install": ["BinaryInstaller", "InstallResult"],
    "dekk.wrapper": ["WrapperGenerator"],
    # -- Detection & Platform --
    "dekk.detect": ["PlatformDetector", "PlatformInfo"],
    "dekk.deps": ["DependencyChecker", "DependencySpec", "DependencyResult", "ToolChecker"],
    "dekk.conda": [
        "COMMON_INSTALL_PATHS", "CondaDetector", "CondaEnvironment", "CondaValidation",
    ],
    # -- Configuration (core) --
    "dekk.config": ["ConfigManager", "ConfigReconciler", "ConfigSource"],
    # -- CI --
    "dekk.ci": ["CIDetector", "CIInfo", "CIProvider", "CIBuildAdvisor", "CIBuildHints"],
    # -- Workspace --
    "dekk.workspace": ["WorkspaceDetector", "WorkspaceInfo", "WorkspaceKind", "SubProject"],
    # -- Versioning --
    "dekk.version": [
        "Version", "VersionSpec", "VersionConstraint",
        "compare_versions", "version_satisfies",
    ],
    "dekk.version_managers": ["VersionManagerDetector", "VersionManagerInfo", "ManagedVersion"],
    # -- Lockfiles --
    "dekk.lockfile": ["LockfileParser", "LockfileInfo", "LockfileKind", "LockedDependency"],
    # -- Compiler & Build --
    "dekk.compiler": ["CompilerDetector", "CompilerFamily", "CompilerInfo", "ToolchainInfo"],
    "dekk.build": ["BuildSystemDetector", "BuildSystemInfo", "BuildSystem", "BuildTarget"],
    "dekk.cache": ["BuildCacheDetector", "BuildCacheInfo", "CacheKind"],
    # -- Shell --
    "dekk.shell": [
        "ShellDetector", "ShellInfo", "ShellKind",
        "ActivationScriptBuilder", "ActivationConfig", "EnvVar",
        "CompletionGenerator", "CompletionSpec",
        "PromptHelper", "AliasSuggestor",
    ],
    # -- Toolchain --
    "dekk.toolchain": ["ToolchainProfile", "EnvVarBuilder", "CMakeToolchain", "CondaToolchain"],
    # -- OS Abstraction --
    "dekk.dekk_os": ["DekkOS", "PosixDekkOS", "WindowsDekkOS", "get_dekk_os"],
    # -- Environment --
    "dekk.env": ["EnvSnapshot"],
    # -- Diagnostics --
    "dekk.diagnostic": [
        "DiagnosticReport", "DiagnosticCheck", "CheckRegistry",
        "DiagnosticRunner", "TextFormatter", "JsonFormatter", "MarkdownFormatter",
    ],
    "dekk.diagnostic_checks": ["PlatformCheck", "DependencyCheck", "CIEnvironmentCheck"],
    # -- Library Paths --
    "dekk.libpath": ["LibraryPathInfo", "LibraryPathResolver"],
    # -- Commands --
    "dekk.commands": ["CommandStatus", "CommandMeta", "CommandProvider", "CommandRegistry", "command"],
    # -- Validation --
    "dekk.validate": ["CheckStatus", "CheckResult", "ValidationReport", "EnvironmentValidator"],
    # -- Remediation --
    "dekk.remediate": [
        "IssueSeverity", "FixStatus", "DetectedIssue", "FixResult",
        "Remediator", "RemediatorRegistry",
    ],
    # -- Scaffold --
    "dekk.scaffold": [
        "ProjectLanguage", "ProjectFramework", "ProjectType", "ProjectTypeDetector",
        "FileTemplate", "TemplateSet", "TemplateRegistry",
        "SetupStep", "SetupScript", "SetupScriptBuilder",
    ],
    # -- Execution Context --
    "dekk.context": [
        "ExecutionContext", "ContextWorkspaceInfo", "GitInfo",
        "CPUInfo", "GPUInfo", "MemoryInfo", "SystemLibrary", "ContextDiff",
    ],
    # -- CLI Framework --
    "dekk.typer_app": ["Typer", "Option", "Argument", "Exit"],
    # -- CLI Commands --
    "dekk.cli_commands": ["run_doctor", "run_version", "run_env"],
    # -- CLI Styling & Output --
    "dekk.cli.styles": [
        "console", "err_console", "Colors", "Symbols",
        "print_success", "print_error", "print_warning", "print_info", "print_debug",
        "print_header", "print_step", "print_section", "print_blank",
        "print_table", "print_numbered_list", "print_next_steps",
    ],
    # -- CLI Output Formatting --
    "dekk.cli.output": ["OutputFormatter", "OutputFormat", "print_dep_results"],
    # -- CLI Error Handling --
    "dekk.cli.errors": [
        "DekkError", "ExitCodes", "NotFoundError", "ValidationError",
        "ConfigError", "DependencyError",
    ],
    # -- CLI Progress --
    "dekk.cli.progress": ["progress_bar", "spinner"],
    # -- CLI Runner --
    "dekk.cli.runner": ["RunResult", "run_logged"],
    # -- Script Runner --
    "dekk.runner": ["run_script"],
}

# Renamed/aliased exports: alias -> (module_path, real_name)
_RENAMES: dict[str, tuple[str, str]] = {
    "DiagnosticCheckStatus": ("dekk.diagnostic", "CheckStatus"),
    "DiagnosticCheckResult": ("dekk.diagnostic", "CheckResult"),
    "DekkTimeoutError": ("dekk.cli.errors", "TimeoutError"),
    "DekkPermissionError": ("dekk.cli.errors", "PermissionError"),
    "DekkRuntimeError": ("dekk.cli.errors", "RuntimeError"),
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


def __getattr__(name: str):  # noqa: N807
    # Check renamed aliases first
    if name in _RENAMES:
        import importlib

        mod_path, real_name = _RENAMES[name]
        module = importlib.import_module(mod_path)
        value = getattr(module, real_name)
        globals()[name] = value
        return value

    # Check normal attributes
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


def __dir__():  # noqa: N807
    return list(_ATTR_TO_MODULE.keys()) + list(_RENAMES.keys()) + ["__version__"]


__all__ = sorted(set(list(_ATTR_TO_MODULE) + list(_RENAMES) + ["__version__"]))
