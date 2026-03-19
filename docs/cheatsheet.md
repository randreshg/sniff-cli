# .sniff-cli.toml Quick Reference

One-page cheat sheet for install, first-run commands, and `.sniff-cli.toml`
syntax.

---

## Basic Structure

```toml
[project]
name = "myapp"

[conda]
name = "myapp"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }

[env]
MY_VAR = "{conda}/lib"

[paths]
bin = ["{project}/bin"]
```

---

## All Sections

### `[project]` -- required

```toml
[project]
name = "myapp"              # Required. Used as default conda env name.
description = "My project"  # Optional.
```

### `[conda]` -- optional

```toml
[conda]
name = "myapp"              # Defaults to project.name
file = "environment.yaml"   # For conda env create
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
MLIR_DIR   = "{conda}/lib/cmake/mlir"
PYTHONPATH = "{project}/src"
NODE_ENV   = "development"
```

### `[paths]` -- optional

```toml
[paths]
bin = ["{project}/bin", "{conda}/bin"]
```

---

## Variable Expansion

| Pattern | Resolves to | Example value |
|---------|-------------|---------------|
| `{project}` | Project root | `/home/user/projects/myapp` |
| `{conda}` | `$CONDA_PREFIX` | `/home/user/miniforge3/envs/myapp` |
| `{home}` | `$HOME` | `/home/user` |

```toml
MLIR_DIR = "{conda}/lib/cmake/mlir"
CONFIG   = "{home}/.config/myapp"
BIN      = "{project}/target/release"
```

---

## CLI Commands

```bash
pipx install sniff-cli
# or: python -m pip install --upgrade sniff-cli
```

```bash
sniff init                              # Create .sniff-cli.toml in current directory
sniff init --example quickstart         # Start from a built-in template
sniff init --force                      # Overwrite existing .sniff-cli.toml

sniff install ./tools/cli.py            # Install a Python CLI; first run bootstraps .venv from pyproject.toml
sniff install ./bin/myapp --name myapp  # Install a wrapped binary command

eval "$(sniff activate --shell bash)"      # Activate environment in the current POSIX shell
sniff activate --shell powershell          # Emit PowerShell activation script

sniff wrap myapp ./bin/myapp               # Generate wrapper in the default user scripts dir
sniff wrap myapp ./cli.py \
  --python /path/to/python3        # Wrap a Python script
sniff wrap myapp ./bin/myapp \
  -d /usr/local/bin                # Custom install directory

sniff example quickstart                # Print starter config to stdout
sniff doctor                            # Run system health checks
sniff version                           # Show sniff-cli version and platform
sniff env                               # Show environment details
```

```powershell
Invoke-Expression (& sniff activate --shell powershell | Out-String)
sniff install .\dist\myapp.exe --name myapp
```

---

## Common Patterns

### Python + Conda

```toml
[project]
name = "ml-pipeline"

[conda]
name = "ml-pipeline"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }

[env]
PYTHONPATH = "{project}/src"
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

[conda]
name = "physics-sim"

[tools]
cmake = { command = "cmake", version = ">=3.20" }
ninja = { command = "ninja" }

[env]
CMAKE_PREFIX_PATH = "{conda}"
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
- [Wrapper Generation](wrapper.md)
- [Examples by Language](examples-by-language.md)
