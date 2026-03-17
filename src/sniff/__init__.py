"""
sniff - One config. Zero activation. Any project.

Detect your project's environment, activate it from a .sniff.toml spec,
and generate self-contained wrapper binaries that just work.

All public symbols are lazily loaded on first access via PEP 562 __getattr__.
This means ``import sniff`` is near-instant (<5ms) regardless of which
optional dependencies (Rich, Typer) are installed.
"""

__version__ = "3.2.0"

# ---------------------------------------------------------------------------
# Lazy import registry: module_path -> list of exported names
# ---------------------------------------------------------------------------

_MODULE_ATTRS: dict[str, list[str]] = {
    # -- Automatic Environment Setup --
    "sniff.envspec": ["EnvironmentSpec", "CondaSpec", "ToolSpec", "find_envspec"],
    "sniff.activation": ["EnvironmentActivator", "ActivationResult"],
    "sniff.install": ["BinaryInstaller", "InstallResult"],
    "sniff.wrapper": ["WrapperGenerator"],
    # -- Detection & Platform --
    "sniff.detect": ["PlatformDetector", "PlatformInfo"],
    "sniff.deps": ["DependencyChecker", "DependencySpec", "DependencyResult", "ToolChecker"],
    "sniff.conda": [
        "COMMON_INSTALL_PATHS", "CondaDetector", "CondaEnvironment", "CondaValidation",
    ],
    # -- Configuration (core) --
    "sniff.config": ["ConfigManager", "ConfigReconciler", "ConfigSource"],
    # -- CI --
    "sniff.ci": ["CIDetector", "CIInfo", "CIProvider", "CIBuildAdvisor", "CIBuildHints"],
    # -- Workspace --
    "sniff.workspace": ["WorkspaceDetector", "WorkspaceInfo", "WorkspaceKind", "SubProject"],
    # -- Versioning --
    "sniff.version": [
        "Version", "VersionSpec", "VersionConstraint",
        "compare_versions", "version_satisfies",
    ],
    "sniff.version_managers": ["VersionManagerDetector", "VersionManagerInfo", "ManagedVersion"],
    # -- Lockfiles --
    "sniff.lockfile": ["LockfileParser", "LockfileInfo", "LockfileKind", "LockedDependency"],
    # -- Compiler & Build --
    "sniff.compiler": ["CompilerDetector", "CompilerFamily", "CompilerInfo", "ToolchainInfo"],
    "sniff.build": ["BuildSystemDetector", "BuildSystemInfo", "BuildSystem", "BuildTarget"],
    "sniff.cache": ["BuildCacheDetector", "BuildCacheInfo", "CacheKind"],
    # -- Shell --
    "sniff.shell": [
        "ShellDetector", "ShellInfo", "ShellKind",
        "ActivationScriptBuilder", "ActivationConfig", "EnvVar",
        "CompletionGenerator", "CompletionSpec",
        "PromptHelper", "AliasSuggestor",
    ],
    # -- Toolchain --
    "sniff.toolchain": ["ToolchainProfile", "EnvVarBuilder", "CMakeToolchain", "CondaToolchain"],
    # -- Environment --
    "sniff.env": ["EnvSnapshot"],
    # -- Diagnostics --
    "sniff.diagnostic": [
        "DiagnosticReport", "DiagnosticCheck", "CheckRegistry",
        "DiagnosticRunner", "TextFormatter", "JsonFormatter", "MarkdownFormatter",
    ],
    "sniff.diagnostic_checks": ["PlatformCheck", "DependencyCheck", "CIEnvironmentCheck"],
    # -- Library Paths --
    "sniff.libpath": ["LibraryPathInfo", "LibraryPathResolver"],
    # -- Commands --
    "sniff.commands": ["CommandStatus", "CommandMeta", "CommandProvider", "CommandRegistry", "command"],
    # -- Validation --
    "sniff.validate": ["CheckStatus", "CheckResult", "ValidationReport", "EnvironmentValidator"],
    # -- Remediation --
    "sniff.remediate": [
        "IssueSeverity", "FixStatus", "DetectedIssue", "FixResult",
        "Remediator", "RemediatorRegistry",
    ],
    # -- Scaffold --
    "sniff.scaffold": [
        "ProjectLanguage", "ProjectFramework", "ProjectType", "ProjectTypeDetector",
        "FileTemplate", "TemplateSet", "TemplateRegistry",
        "SetupStep", "SetupScript", "SetupScriptBuilder",
    ],
    # -- Execution Context --
    "sniff.context": [
        "ExecutionContext", "ContextWorkspaceInfo", "GitInfo",
        "CPUInfo", "GPUInfo", "MemoryInfo", "SystemLibrary", "ContextDiff",
    ],
    # -- CLI Framework (requires sniff[cli]) --
    "sniff.typer_app": ["Typer", "Option", "Argument", "Exit"],
    # -- CLI Commands --
    "sniff.cli_commands": ["run_doctor", "run_version", "run_env"],
    # -- CLI Styling & Output --
    "sniff.cli.styles": [
        "console", "err_console", "Colors", "Symbols",
        "print_success", "print_error", "print_warning", "print_info", "print_debug",
        "print_header", "print_step", "print_section", "print_blank",
        "print_table", "print_numbered_list", "print_next_steps",
    ],
    # -- CLI Output Formatting --
    "sniff.cli.output": ["OutputFormatter", "OutputFormat", "print_dep_results"],
    # -- CLI Error Handling --
    "sniff.cli.errors": [
        "SniffError", "ExitCodes", "NotFoundError", "ValidationError",
        "ConfigError", "DependencyError",
    ],
    # -- CLI Progress --
    "sniff.cli.progress": ["progress_bar", "spinner"],
    # -- CLI Runner --
    "sniff.cli.runner": ["RunResult", "run_logged"],
    # -- Script Runner --
    "sniff.runner": ["run_script"],
}

# Renamed/aliased exports: alias -> (module_path, real_name)
_RENAMES: dict[str, tuple[str, str]] = {
    "DiagnosticCheckStatus": ("sniff.diagnostic", "CheckStatus"),
    "DiagnosticCheckResult": ("sniff.diagnostic", "CheckResult"),
    "SniffTimeoutError": ("sniff.cli.errors", "TimeoutError"),
    "SniffPermissionError": ("sniff.cli.errors", "PermissionError"),
    "SniffRuntimeError": ("sniff.cli.errors", "RuntimeError"),
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

    raise AttributeError(f"module 'sniff' has no attribute {name!r}")


def __dir__():  # noqa: N807
    return list(_ATTR_TO_MODULE.keys()) + list(_RENAMES.keys()) + ["__version__"]


__all__ = sorted(set(list(_ATTR_TO_MODULE) + list(_RENAMES) + ["__version__"]))
