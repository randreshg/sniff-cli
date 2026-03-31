# .dekk.toml Specification

**Version:** 1.0

Canonical reference for `.dekk.toml`, the declarative environment configuration file read by `dekk`. One file describes your entire project environment -- runtime environment, tools, paths, variables -- and dekk handles detection, activation, and wrapper generation.

---

## Design Principles

1. **Declarative** -- describe the desired state, not how to achieve it
2. **Reproducible** -- same config produces same environment on any machine
3. **Language-agnostic** -- works for Python, Rust, C++, Node, Go, Java, or any mix
4. **Minimal by default** -- only `[project].name` is required; add sections as needed
5. **Expansion-friendly** -- variable substitution for paths and values

---

## Variable Expansion

All string values support `{variable}` expansion at runtime.

### Built-in Variables

| Variable | Resolves to | Example |
|----------|-------------|---------|
| `{project}` | Project root (directory containing `.dekk.toml`) | `/home/user/projects/myapp` |
| `{environment}` | Environment prefix path | `/home/user/projects/myapp/.dekk/env` |
| `{home}` | User home directory (`$HOME`) | `/home/user` |

### Rules

- Variables are resolved at **runtime**, not at parse time.
- An undefined variable with no default causes an error.
- Recursive expansion is not supported (prevents infinite loops).

### Examples

```toml
CMAKE_PREFIX_PATH = "{environment}"
# -> /home/user/projects/myapp/.dekk/env

DATA_DIR = "{project}/data"
# -> /home/user/projects/myapp/data

CONFIG   = "{home}/.config/myapp"
# -> /home/user/.config/myapp
```

---

## Section Reference

### `[project]` -- Project Identity (required)

Every `.dekk.toml` must have a `[project]` section with at least a `name`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | **yes** | Project name. Used in generated wrappers and manifests. |
| `description` | string | no | Human-readable project description. |

```toml
[project]
name = "myapp"
description = "REST API server"
```

**Implementation:** `dekk.environment.spec.EnvironmentSpec`

---

### `[environment]` -- Runtime Environment

Declares the runtime environment to resolve and activate.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | **yes** | Environment provider type (currently: `conda`). |
| `path` | string | **yes** | Environment prefix path (recommended: project-local). |
| `file` | string | no | Path to `environment.yaml` for creation (conda). |
| `name` | string | no | Display name (optional). |

```toml
[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"
```

When present, `dekk activate` and `dekk wrap` use this `path` deterministically (no named-env lookup).

**Implementation:** `dekk.environment.resolver.resolve_environment`

---

### `[tools]` -- Required CLI Tools

Specifies command-line tools your project depends on. Each key is a logical tool name; the value is either a **string** (shorthand) or a **dict** (full specification).

#### String form (command name only)

```toml
[tools]
make = "make"
```

Equivalent to `{ command = "make" }`.

#### Dict form (full specification)

```toml
[tools]
python = { command = "python", version = ">=3.10" }
cargo  = { command = "cargo", version = ">=1.70", optional = true }
```

Or as a sub-table:

```toml
[tools.cmake]
command = "cmake"
version = ">=3.20"
optional = false
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | string | yes | CLI command to check (looked up via `which`). |
| `version` | string | no | Semver constraint (e.g., `>=3.20`, `>=1.70`). |
| `optional` | bool | no | If `true`, a missing tool is a warning, not an error. Default: `false`. |

**Implementation:** `dekk.detection.deps.DependencyChecker`, `dekk.version.VersionSpec`

---

### `[env]` -- Environment Variables

Key-value pairs set during activation and baked into wrappers. Values support variable expansion.

```toml
[env]
CMAKE_PREFIX_PATH = "{environment}"
PYTHONPATH = "{project}/src"
NODE_ENV = "development"
```

All keys are exported as environment variables (`export KEY="value"` in generated scripts).

**Implementation:** `dekk.execution.toolchain.EnvVarBuilder`

---

### `[paths]` -- PATH Prepends

Lists of directories to prepend to `PATH` during activation and in wrappers.

```toml
[paths]
bin = ["{project}/bin", "{project}/target/release", "{environment}/bin"]
```

Each key maps to a list of directories. The `bin` key is treated specially: its entries are prepended to `PATH`. Other keys are available for custom use by downstream tools.

**Implementation:** `dekk.environment.activation.EnvironmentActivator`

---

### `[commands]` -- Project Command Map

Defines project commands used by `dekk <app_name> <command> [args...]`.

```toml
[commands]
server = { run = "python -m clic.api", description = "Start API server" }
test = { run = "pytest -q", description = "Run tests" }
```

Rules:

- `dekk` resolves the nearest `.dekk.toml` from current working directory.
- `<app_name>` must match `[project].name`, or dekk exits with a mismatch error.
- Unknown command keys return an error with available command names.

**Implementation:** `dekk.project.runner.run_project_command`

---

### `[agents]` -- Agent Generation Settings

Controls the source-of-truth directory and which target formats dekk should
generate for agent tooling.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | no | Source-of-truth directory. Default: `.agents`. |
| `targets` | list[string] | no | Generation targets. Default: `["claude", "codex", "copilot", "cursor"]`. |

```toml
[agents]
source = ".agents"
targets = ["claude", "codex", "copilot", "cursor"]
```

Notes:

- `dekk agents init` scaffolds `source/project.md` and starter skills.
- Commands declared in `[commands]` are converted into starter skill templates
  during `dekk agents init`.
- `dekk agents generate` produces files such as `AGENTS.md`, `CLAUDE.md`,
  `.cursorrules`, `.github/copilot-instructions.md`, and `.agents.json`.

**Implementation:** `dekk.environment.spec.AgentsSpec`, `dekk.agents.generators.AgentConfigManager`

---

## Validation Rules

1. `[project].name` is **required**. Parsing fails without it.
2. Tool commands are validated with `shutil.which()`. Missing required tools cause activation to fail.
3. Version constraints use semver syntax: `>=`, `>`, `<=`, `<`, `=`, and bare versions.
4. Undefined variables (`{environment}` when no environment prefix exists) raise an error.
5. TOML syntax errors produce a clear `ConfigError` with file path and details.

---

## Module Mapping

| `.dekk.toml` Section | `dekk` Module | Primary Classes |
|-----------------------|--------------|-----------------|
| `[project]` | `dekk.environment.spec` | `EnvironmentSpec` |
| `[environment]` | `dekk.environment.providers`, `dekk.environment.resolver` | `DekkEnv`, `resolve_environment` |
| `[tools]` | `dekk.detection.deps`, `dekk.version` | `DependencyChecker`, `VersionSpec` |
| `[env]` | `dekk.execution.toolchain` | `EnvVarBuilder` |
| `[paths]` | `dekk.environment.activation` | `EnvironmentActivator` |
| `[commands]` | `dekk.project.runner` | `run_project_command` |
| `[agents]` | `dekk.environment.spec`, `dekk.agents.generators` | `AgentsSpec`, `AgentConfigManager` |
| *(activation)* | `dekk.environment.activation` | `EnvironmentActivator` |
| *(wrappers)* | `dekk.execution.wrapper` | `WrapperGenerator` |

---

## Complete Examples

### Minimal

```toml
[project]
name = "hello"
```

### Python + Conda

```toml
[project]
name = "ml-pipeline"

[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }
jupyter = { command = "jupyter" }

[env]
PYTHONPATH = "{project}/src"

[agents]
targets = ["claude", "codex"]
```

### Rust

```toml
[project]
name = "my-rust-app"

[tools]
cargo = { command = "cargo", version = ">=1.70" }
rustc = { command = "rustc" }

[paths]
bin = ["{project}/target/release"]
```

### C++ with CMake + Conda

```toml
[project]
name = "physics-sim"

[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"

[tools]
cmake = { command = "cmake", version = ">=3.20" }
ninja = { command = "ninja" }
clang = { command = "clang", version = ">=17" }

[env]
CMAKE_PREFIX_PATH = "{environment}"
CMAKE_BUILD_TYPE  = "Release"
```

### Node.js

```toml
[project]
name = "web-app"

[tools]
node = { command = "node", version = ">=18" }
npm  = { command = "npm" }

[env]
NODE_ENV = "development"
```

### Go

```toml
[project]
name = "api-server"

[tools]
go = { command = "go", version = ">=1.21" }

[env]
GOPATH = "{home}/go"

[paths]
bin = ["{home}/go/bin"]
```

### Multi-Language (Python + Rust + LLVM)

```toml
[project]
name = "compiler-toolkit"

[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }
cargo  = { command = "cargo", version = ">=1.80" }
cmake  = { command = "cmake", version = ">=3.20" }

[env]
CMAKE_PREFIX_PATH = "{environment}"

[paths]
bin = ["{environment}/bin", "{project}/bin", "{project}/target/release"]
```

---

## See Also

- [Wrapper Generation](wrapper.md) -- how wrappers bake this config into executables
- [Quick Reference](cheatsheet.md) -- one-page cheat sheet
- [Examples by Language](examples-by-language.md) -- language-specific configs with wrapper patterns
