"""
sniff-cli - One config. Zero activation. Any project.

Detect your project's environment, activate it from a .sniff-cli.toml spec,
and generate self-contained wrapper binaries that just work.

All public symbols are lazily loaded on first access via PEP 562 __getattr__.
This means ``import sniff_cli`` is near-instant (<5ms) regardless of which
optional tracking integrations are installed.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sniff-cli")
except PackageNotFoundError:
    __version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Lazy import registry: module_path -> list of exported names
# ---------------------------------------------------------------------------

_MODULE_ATTRS: dict[str, list[str]] = {
    # -- Automatic Environment Setup --
    "sniff_cli.envspec": ["EnvironmentSpec", "CondaSpec", "ToolSpec", "find_envspec"],
    "sniff_cli.activation": ["EnvironmentActivator", "ActivationResult"],
    "sniff_cli.install": ["BinaryInstaller", "InstallResult"],
    "sniff_cli.wrapper": ["WrapperGenerator"],
    # -- Detection & Platform --
    "sniff_cli.detect": ["PlatformDetector", "PlatformInfo"],
    "sniff_cli.deps": ["DependencyChecker", "DependencySpec", "DependencyResult", "ToolChecker"],
    "sniff_cli.conda": [
        "COMMON_INSTALL_PATHS", "CondaDetector", "CondaEnvironment", "CondaValidation",
    ],
    # -- Configuration (core) --
    "sniff_cli.config": ["ConfigManager", "ConfigReconciler", "ConfigSource"],
    # -- CI --
    "sniff_cli.ci": ["CIDetector", "CIInfo", "CIProvider", "CIBuildAdvisor", "CIBuildHints"],
    # -- Workspace --
    "sniff_cli.workspace": ["WorkspaceDetector", "WorkspaceInfo", "WorkspaceKind", "SubProject"],
    # -- Versioning --
    "sniff_cli.version": [
        "Version", "VersionSpec", "VersionConstraint",
        "compare_versions", "version_satisfies",
    ],
    "sniff_cli.version_managers": ["VersionManagerDetector", "VersionManagerInfo", "ManagedVersion"],
    # -- Lockfiles --
    "sniff_cli.lockfile": ["LockfileParser", "LockfileInfo", "LockfileKind", "LockedDependency"],
    # -- Compiler & Build --
    "sniff_cli.compiler": ["CompilerDetector", "CompilerFamily", "CompilerInfo", "ToolchainInfo"],
    "sniff_cli.build": ["BuildSystemDetector", "BuildSystemInfo", "BuildSystem", "BuildTarget"],
    "sniff_cli.cache": ["BuildCacheDetector", "BuildCacheInfo", "CacheKind"],
    # -- Shell --
    "sniff_cli.shell": [
        "ShellDetector", "ShellInfo", "ShellKind",
        "ActivationScriptBuilder", "ActivationConfig", "EnvVar",
        "CompletionGenerator", "CompletionSpec",
        "PromptHelper", "AliasSuggestor",
    ],
    # -- Toolchain --
    "sniff_cli.toolchain": ["ToolchainProfile", "EnvVarBuilder", "CMakeToolchain", "CondaToolchain"],
    # -- OS Abstraction --
    "sniff_cli.sniff_os": ["SniffOS", "PosixSniffOS", "WindowsSniffOS", "get_sniff_os"],
    # -- Environment --
    "sniff_cli.env": ["EnvSnapshot"],
    # -- Diagnostics --
    "sniff_cli.diagnostic": [
        "DiagnosticReport", "DiagnosticCheck", "CheckRegistry",
        "DiagnosticRunner", "TextFormatter", "JsonFormatter", "MarkdownFormatter",
    ],
    "sniff_cli.diagnostic_checks": ["PlatformCheck", "DependencyCheck", "CIEnvironmentCheck"],
    # -- Library Paths --
    "sniff_cli.libpath": ["LibraryPathInfo", "LibraryPathResolver"],
    # -- Commands --
    "sniff_cli.commands": ["CommandStatus", "CommandMeta", "CommandProvider", "CommandRegistry", "command"],
    # -- Validation --
    "sniff_cli.validate": ["CheckStatus", "CheckResult", "ValidationReport", "EnvironmentValidator"],
    # -- Remediation --
    "sniff_cli.remediate": [
        "IssueSeverity", "FixStatus", "DetectedIssue", "FixResult",
        "Remediator", "RemediatorRegistry",
    ],
    # -- Scaffold --
    "sniff_cli.scaffold": [
        "ProjectLanguage", "ProjectFramework", "ProjectType", "ProjectTypeDetector",
        "FileTemplate", "TemplateSet", "TemplateRegistry",
        "SetupStep", "SetupScript", "SetupScriptBuilder",
    ],
    # -- Execution Context --
    "sniff_cli.context": [
        "ExecutionContext", "ContextWorkspaceInfo", "GitInfo",
        "CPUInfo", "GPUInfo", "MemoryInfo", "SystemLibrary", "ContextDiff",
    ],
    # -- CLI Framework --
    "sniff_cli.typer_app": ["Typer", "Option", "Argument", "Exit"],
    # -- CLI Commands --
    "sniff_cli.cli_commands": ["run_doctor", "run_version", "run_env"],
    # -- CLI Styling & Output --
    "sniff_cli.cli.styles": [
        "console", "err_console", "Colors", "Symbols",
        "print_success", "print_error", "print_warning", "print_info", "print_debug",
        "print_header", "print_step", "print_section", "print_blank",
        "print_table", "print_numbered_list", "print_next_steps",
    ],
    # -- CLI Output Formatting --
    "sniff_cli.cli.output": ["OutputFormatter", "OutputFormat", "print_dep_results"],
    # -- CLI Error Handling --
    "sniff_cli.cli.errors": [
        "SniffError", "ExitCodes", "NotFoundError", "ValidationError",
        "ConfigError", "DependencyError",
    ],
    # -- CLI Progress --
    "sniff_cli.cli.progress": ["progress_bar", "spinner"],
    # -- CLI Runner --
    "sniff_cli.cli.runner": ["RunResult", "run_logged"],
    # -- Script Runner --
    "sniff_cli.runner": ["run_script"],
}

# Renamed/aliased exports: alias -> (module_path, real_name)
_RENAMES: dict[str, tuple[str, str]] = {
    "DiagnosticCheckStatus": ("sniff_cli.diagnostic", "CheckStatus"),
    "DiagnosticCheckResult": ("sniff_cli.diagnostic", "CheckResult"),
    "SniffTimeoutError": ("sniff_cli.cli.errors", "TimeoutError"),
    "SniffPermissionError": ("sniff_cli.cli.errors", "PermissionError"),
    "SniffRuntimeError": ("sniff_cli.cli.errors", "RuntimeError"),
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

    raise AttributeError(f"module 'sniff_cli' has no attribute {name!r}")


def __dir__():  # noqa: N807
    return list(_ATTR_TO_MODULE.keys()) + list(_RENAMES.keys()) + ["__version__"]


__all__ = sorted(set(list(_ATTR_TO_MODULE) + list(_RENAMES) + ["__version__"]))
