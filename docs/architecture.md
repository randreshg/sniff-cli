# dekk Architecture

## Overview

dekk is a development environment detection library and CLI framework.
It detects platforms, conda environments, build systems, compilers, CI providers,
shells, and workspaces -- then provides activation and wrapper generation via
`.dekk.toml` configuration files.

---

## Core Principles

1. **Lazy by default** -- `import dekk` takes <1ms. All modules use PEP 562
   `__getattr__` for deferred loading. Rich and Typer are only imported when
   CLI features are actually used.

2. **Detection-only** -- detectors never modify state. No file writes, no env
   var mutations, no package installs. Side effects exist only in explicit
   activation and wrapper generation.

3. **Frozen dataclasses** -- all result types are `@dataclass(frozen=True)`.
   Immutable results can be cached, shared across threads, and used as dict keys.

4. **Always succeeds** -- every `detect()` method returns a valid result, never
   raises. Missing data produces `None` fields, not exceptions.

---

## Module Organization

```
src/dekk/
├── __init__.py          # PEP 562 lazy re-exports (auto-generated __all__)
├── _compat.py           # TOML compat, load_toml, load_json, deep_merge, walk_up
│
│   # ── Detection ─────────────────────────────────────────
├── detection/
│   ├── __init__.py      # Detection exports
│   ├── detect.py        # PlatformDetector, PlatformInfo
│   ├── deps.py          # DependencyChecker, DependencySpec, DependencyResult, ToolChecker
│   ├── conda.py         # CondaDetector, CondaEnvironment, CondaValidation
│   ├── ci.py            # CIDetector, CIInfo, CIProvider, CIBuildAdvisor, CIBuildHints
│   ├── workspace.py     # WorkspaceDetector, WorkspaceInfo, WorkspaceKind
│   ├── build.py         # BuildSystemDetector, BuildSystemInfo, BuildSystem
│   ├── compiler.py      # CompilerDetector, CompilerFamily, CompilerInfo
│   ├── cache.py         # BuildCacheDetector, BuildCacheInfo, CacheKind
│   ├── version_managers.py  # VersionManagerDetector, VersionManagerInfo
│   ├── lockfile.py      # LockfileParser, LockfileInfo, LockfileKind
│   └── libpath.py       # LibraryPathInfo, LibraryPathResolver
├── config.py            # ConfigManager, ConfigReconciler, ConfigSource
├── version.py           # Version, VersionSpec, VersionConstraint
├── shell.py             # ShellDetector, ShellInfo, ActivationScriptBuilder
│
│   # ── Environment Setup ─────────────────────────────────
├── environment/
│   ├── __init__.py      # Environment exports
│   ├── types.py         # EnvironmentKind, normalization helpers
│   ├── spec.py          # EnvironmentSpec, ToolSpec, find_envspec
│   ├── resolver.py      # Resolve a DekkEnv from config
│   ├── providers/       # Per-environment implementations
│   ├── activation.py    # EnvironmentActivator, ActivationResult
│   └── setup.py         # SetupResult, run_setup
├── execution/
│   ├── __init__.py      # Execution exports
│   ├── install.py       # BinaryInstaller, InstallResult
│   ├── wrapper.py       # WrapperGenerator
│   ├── runner.py        # Python script bootstrap runner
│   ├── test_runner.py   # Project test planning and execution
│   ├── toolchain/       # Builder + per-toolchain implementations
│   ├── env.py           # EnvSnapshot
│   └── os/              # Host OS interface + per-OS implementations
├── context.py           # ExecutionContext, CPUInfo, GPUInfo, MemoryInfo
├── project/
│   ├── __init__.py      # Project routing exports
│   └── runner.py        # Worktree-safe command routing
│
│   # ── Frameworks ────────────────────────────────────────
├── agents/
│   ├── __init__.py      # Agent-facing public exports
│   ├── app.py           # `dekk agents` subcommand factory
│   ├── discovery.py     # Parse skills, rules, and frontmatter
│   ├── generators.py    # Orchestrate agent providers + manifests
│   ├── installer.py     # Install Codex skills into Codex home
│   ├── providers/       # Per-agent implementations
│   ├── scaffold.py      # Scaffold `.agents/` from repo metadata + commands
│   ├── flows.py         # Generate reusable flow templates
│   └── constants.py     # Shared filenames and defaults
│
│   # ── Diagnostics ───────────────────────────────────────
├── diagnostics/
│   ├── __init__.py      # Diagnostics exports
│   ├── diagnostic.py    # DiagnosticReport, DiagnosticRunner, CheckRegistry
│   ├── diagnostic_checks.py # PlatformCheck, DependencyCheck, CIEnvironmentCheck
│   ├── validate.py      # EnvironmentValidator, ValidationReport
│   ├── remediate.py     # Remediator, RemediatorRegistry, DetectedIssue
│   └── validation_cache.py # Cached activation validation data
├── scaffold.py          # ProjectTypeDetector, TemplateRegistry, SetupScriptBuilder
├── commands.py          # CommandRegistry, CommandProvider
│
│   # ── CLI Framework ──────────────────────────────────────────
├── typer_app.py         # Typer wrapper with auto-activation
├── cli_commands.py      # run_doctor, run_version, run_env
├── cli/
│   ├── __init__.py      # Lazy re-exports for cli subpackage
│   ├── styles.py        # Colors, Symbols, print_success/error/warning/info/...
│   ├── output.py        # OutputFormatter (TABLE/JSON/YAML/TEXT), print_dep_results
│   ├── errors.py        # DekkError, ExitCodes, typed error classes
│   ├── progress.py      # progress_bar, spinner context managers
│   ├── runner.py        # run_logged (subprocess with logging)
│   ├── config.py        # CLI-layer ConfigManager (TOML I/O, walk-up discovery)
│   ├── commands.py      # CLI command handlers (activate, init, uninstall, wrap)
│   └── main.py          # Typer app definition and subcommand registration
```

---

## Lazy Loading

All public symbols are registered in `__init__.py`'s `_MODULE_ATTRS` dict
and loaded on first access via PEP 562 `__getattr__`:

```python
_MODULE_ATTRS = {
    "dekk.detection.detect": ["PlatformDetector", "PlatformInfo"],
    "dekk.detection.deps": ["DependencyChecker", "DependencySpec", ...],
    ...
}

def __getattr__(name):
    if name in _ATTR_TO_MODULE:
        module = importlib.import_module(_ATTR_TO_MODULE[name])
        # Bulk-cache all names from this module
        ...
```

Rich console singletons in `cli/styles.py` use the same pattern:
`_get_console()` / `_get_err_console()` create instances on first call.

---

## Shared Utilities (`_compat.py`)

Consolidated compatibility layer used by 6+ modules:

- `tomllib` -- stdlib on 3.11+, `tomli` fallback, `None` if unavailable
- `load_toml(path)` -- load TOML file, returns `None` on failure
- `load_json(path)` -- load JSON file, returns `None` on failure
- `deep_merge(base, override)` -- recursive dict merge (returns new dict)
- `walk_up(start, marker)` -- walk up directory tree looking for a file

---

## OS Abstraction (`execution/os/`)

Windows-specific behavior used to be scattered across wrapper generation,
toolchain setup, runner bootstrap, and install-path defaults. `execution/os/`
centralizes those decisions behind a small interface:

- `PosixDekkOS` owns POSIX wrapper generation, `bin/` venv layout, and
  Unix conda/runtime path conventions.
- `WindowsDekkOS` owns `.cmd` wrapper generation, `Scripts/` venv layout,
  Windows conda runtime path layout, and user scripts installation defaults.
- `get_dekk_os()` selects the host implementation once, so higher-level
  modules do not duplicate platform checks.

Modules that rely on this layer:

- `execution/wrapper.py` delegates launcher format, filename suffixes, and
  default installation directories to `dekk_os`.
- `execution/install.py` asks `dekk_os` for Python command candidates instead
  of branching on platform strings directly.
- `execution/runner.py` uses `dekk_os` to find `python` and `pip` inside a venv.
- `execution/toolchain/` uses `dekk_os` for runtime paths, CMake layout, and
  OS-specific library path behavior.

The design rule is: platform-sensitive filesystem and launcher behavior lives
in `execution/os/`; higher-level modules stay focused on environment
semantics.

---

## Worktree-Safe Command Routing (`project/runner.py`)

`dekk <app_name> <command> [args...]` is designed to be safe in nested repos
and Git worktrees:

- it walks up from the current directory to the nearest `.dekk.toml`
- it validates that `<app_name>` matches `[project].name`
- it activates env vars from that project config
- it runs the command with `cwd` set to the resolved project root

That keeps command dispatch local to the current project context instead of
depending on the caller's shell state or current subdirectory.

---

## CLI Framework

The CLI layer (included in the base `dekk` install) provides:

- **`dekk.cli.styles`** -- 12 semantic output functions (`print_success`,
  `print_error`, etc.) covering 89% of CLI output patterns. Colors and Symbols
  enums for consistent styling.

- **`dekk.cli.output`** -- `OutputFormatter` with TABLE/JSON/YAML/TEXT modes,
  quiet/verbose support, and `print_dep_results` for dependency checks.

- **`dekk.cli.progress`** -- `progress_bar` and `spinner` context managers
  wrapping Rich progress indicators.

- **`dekk.cli.errors`** -- `DekkError` base class with typed subclasses
  (`NotFoundError`, `ValidationError`, `ConfigError`, `DependencyError`).

- **`dekk.typer_app`** -- `Typer` wrapper that adds auto-activation from
  `.dekk.toml` as a pre-command hook.

---

## Extension Points

dekk uses the **provider pattern**: dekk defines Protocol interfaces,
consumers register implementations.

Agent generation follows a different rule: `.agents/` is the source of truth,
and generated files in the repo root are derived artifacts. The design goal is
that project guidance is edited once and rendered into each agent ecosystem’s
expected format.

| Extension Point | Protocol | Registry | Use Case |
|----------------|----------|----------|----------|
| Remediation | `Remediator` | `RemediatorRegistry` | Fix detected issues |
| Commands | `CommandProvider` | `CommandRegistry` | Discover/register commands |
| Diagnostics | `DiagnosticCheck` | `CheckRegistry` | Custom health checks |
| Scaffolding | `TemplateRegistry` | `SetupScriptBuilder` | Project scaffolding |

---

## Performance

| Metric | Target | Actual |
|--------|--------|--------|
| `import dekk` | < 5ms | 0.4ms |
| `PlatformDetector().detect()` | < 5ms | ~2ms |
| `CIDetector().detect()` | < 1ms | ~0.5ms |
| `dekk --help` | < 500ms | ~200ms |

Strategies:
- PEP 562 lazy loading for all modules
- Lazy Rich/Typer imports (only when CLI features used)
- Frozen dataclass results (cacheable)
- Subprocess timeouts (configurable, default 10s)

---

## See Also

- [Getting Started](getting-started.md) -- Installation and quick start
- [.dekk.toml Specification](spec.md) -- Config file format reference
- [Wrapper Generation](wrapper.md) -- How `dekk wrap` works
- [Contributing](contributing.md) -- Development setup and code style
