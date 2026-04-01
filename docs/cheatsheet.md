# .dekk.toml Quick Reference

One-page cheat sheet for install, first-run commands, and `.dekk.toml`
syntax.

---

## Basic Structure

```toml
[project]
name = "myapp"

[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }

[env]
MY_VAR = "{environment}/lib"

[paths]
bin = ["{project}/bin"]

[commands]
test = { run = "pytest -q", description = "Run tests" }

[agents]
source = ".agents"
targets = ["claude", "codex", "copilot", "cursor"]
```

---

## All Sections

### `[project]` -- required

```toml
[project]
name = "myapp"              # Required. Used as default conda env name.
description = "My project"  # Optional.
```

### `[environment]` -- optional

```toml
[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"
```

### `[tools]` -- optional

```toml
# String shorthand
[tools]
make = "make"

# Inline dict
[tools]
python = { command = "python", version = ">=3.10" }
cargo  = { command = "cargo", optional = true }

# Sub-table (equivalent)
[tools.cmake]
command = "cmake"
version = ">=3.20"
optional = false
```

### `[env]` -- optional

```toml
[env]
CMAKE_PREFIX_PATH = "{environment}"
PYTHONPATH = "{project}/src"
NODE_ENV   = "development"
```

### `[paths]` -- optional

```toml
[paths]
bin = ["{project}/bin", "{environment}/bin"]
```

### `[commands]` -- optional

```toml
[commands]
server = { run = "python -m myapp.api", description = "Start API server" }
test = { run = "pytest -q", description = "Run tests" }
```

### `[agents]` -- optional

```toml
[agents]
source = ".agents"
targets = ["claude", "codex", "copilot", "cursor"]
```

---

## Variable Expansion

| Pattern | Resolves to | Example value |
|---------|-------------|---------------|
| `{project}` | Project root | `/home/user/projects/myapp` |
| `{environment}` | Environment prefix | `/home/user/projects/myapp/.dekk/env` |
| `{home}` | `$HOME` | `/home/user` |

```toml
CMAKE_PREFIX_PATH = "{environment}"
CONFIG   = "{home}/.config/myapp"
BIN      = "{project}/target/release"
```

---

## CLI Commands

```bash
pipx install dekk
# or: python -m pip install --upgrade dekk
```

```bash
dekk init                              # Create .dekk.toml from a chosen template
dekk init --example quickstart         # Start from a built-in template
dekk init --force                      # Overwrite existing .dekk.toml

dekk install ./tools/cli.py            # Install a Python CLI; auto-creates .dekk.toml if missing
dekk install ./bin/myapp --name myapp  # Install a wrapped binary command; auto-creates .dekk.toml if missing
dekk install ./tools/cli.py --update-shell   # Optional: add install dir to shell rc

eval "$(dekk activate --shell bash)"      # Activate environment in the current POSIX shell
dekk activate --shell powershell          # Emit PowerShell activation script

dekk wrap myapp ./bin/myapp               # Generate wrapper in ./.install; auto-creates .dekk.toml if missing
dekk wrap myapp ./cli.py \
  --python /path/to/python3        # Wrap a Python script
dekk wrap myapp ./bin/myapp \
  -d /usr/local/bin                # Custom install directory

dekk example quickstart                # Print starter config to stdout
dekk doctor                            # Run system health checks
dekk version                           # Show dekk version and platform
dekk env                               # Show environment details
dekk myapp                             # Show project-aware help
dekk myapp --help                      # Same as above
dekk myapp setup                       # Create the configured project runtime
dekk myapp server --port 8080          # Run command from nearest .dekk.toml

dekk agents init                       # Scaffold .agents/ and seed .dekk.toml if needed
dekk agents generate --target all      # Generate AGENTS.md / CLAUDE.md / etc.
dekk agents clean --target all         # Remove generated agent files, keep .agents/
dekk agents status                     # Show source + generated file state
dekk agents install                    # Install Codex skills to ~/.codex/skills
```

```powershell
Invoke-Expression (& dekk activate --shell powershell | Out-String)
dekk install .\dist\myapp.exe --name myapp
```

## Worktree-Friendly Routing

```bash
dekk myapp server
dekk myapp test -k smoke
```

- `dekk` walks up to the nearest `.dekk.toml`
- `myapp` must match `[project].name`
- the command runs from that project root
- activation/env vars come from that project before execution

This keeps command routing safe across nested directories and separate Git
worktrees.

---

## Common Patterns

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

[env]
PYTHONPATH = "{project}/src"

[commands]
server = { run = "python -m ml_pipeline.api", description = "Start API server" }
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

### C++ (CMake + Conda)

```toml
[project]
name = "physics-sim"

[environment]
type = "conda"
path = "{project}/.dekk/env"

[tools]
cmake = { command = "cmake", version = ">=3.20" }
ninja = { command = "ninja" }

[env]
CMAKE_PREFIX_PATH = "{environment}"
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

---

## Tool Spec Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `command` | string | key name | CLI command to look up |
| `version` | string | -- | Semver constraint (`>=3.20`) |
| `optional` | bool | `false` | Warning instead of error if missing |

---

## See Also

- [Full Specification](spec.md)
- [Agent Workflows](agents.md)
- [Wrapper Generation](wrapper.md)
- [Examples by Language](examples-by-language.md)
