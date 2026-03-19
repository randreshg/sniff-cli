# dekk

**Make project CLIs runnable with one config and zero manual activation.**

dekk turns project setup into a reusable runtime layer. Declare the
environment once in `.dekk.toml`, then use `dekk` to detect tools,
activate the environment, install wrappers, and make project commands
work on fresh machines without hand-written setup steps.

## Install And Start

Recommended for end users:

```bash
pipx install dekk
```

Fallback if you already manage Python packages directly:

```bash
python -m pip install --upgrade dekk
```

After installation:

- Use `dekk` for the CLI.
- Use `python -m dekk` as a fallback if your scripts directory is not on `PATH` yet.

## The Problem

Every project needs environment setup: conda environments, PATH entries,
environment variables, tool versions. Developers manually activate things.
AI agents waste thousands of tokens describing setup steps. CI pipelines
duplicate configuration.

## The Solution

Declare your environment once in `.dekk.toml`. dekk handles detection,
activation, wrapper generation, and installed command setup from that
single source of truth.

```toml
[project]
name = "myapp"

[conda]
name = "myapp"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }
cmake  = { command = "cmake", version = ">=3.20" }
cargo  = { command = "cargo" }

[env]
MLIR_DIR = "{conda}/lib/cmake/mlir"

[paths]
bin = ["{project}/bin"]
```

## Three Pillars

### 1. Detect

Zero-dependency detection of your entire development environment:

- **Platform**: OS, architecture, Linux distro, WSL, containers
- **Package managers**: conda/mamba, with environment validation
- **Build systems**: 25+ (Cargo, CMake, npm, Poetry, Maven, Gradle, ...)
- **Compilers**: GCC, Clang, Rust, Go with versions and targets
- **CI providers**: 14 (GitHub Actions, GitLab CI, Jenkins, ...)
- **Shells**: 9 types (bash, zsh, fish, tcsh, PowerShell, ...)
- **Workspaces**: Monorepo detection with dependency graphs

```python
from dekk import PlatformDetector, CondaDetector, BuildSystemDetector

platform = PlatformDetector().detect()
# PlatformInfo(os='Linux', arch='x86_64', distro='ubuntu', ...)

conda = CondaDetector().find_environment("myenv")
# CondaEnvironment(name='myenv', prefix=Path('/opt/conda/envs/myenv'))

builds = BuildSystemDetector().detect(Path("."))
# [BuildSystemInfo(system=BuildSystem.CARGO, root=Path("."), ...)]
```

### 2. Activate

Read `.dekk.toml`, resolve conda paths, set environment variables, validate tools:

```python
from dekk import EnvironmentActivator

activator = EnvironmentActivator.from_cwd()
result = activator.activate()
# ActivationResult(env_vars={'CONDA_PREFIX': '...', 'MLIR_DIR': '...'}, ...)
```

Or from the CLI:
```
$ eval "$(dekk activate --shell bash)"
```

On Windows PowerShell:
```powershell
PS> Invoke-Expression (& dekk activate --shell powershell | Out-String)
```

### 3. Wrap

Generate a self-contained launcher that bakes in the full environment.
**This is what makes dekk zero-friction.**

```
$ dekk wrap myapp ./bin/myapp
  Generated myapp -> /path/to/project/.install/myapp

$ myapp doctor    # just works -- no activation needed
```

On POSIX, the wrapper is a simple shell script with hardcoded paths:
```sh
#!/bin/sh
export CONDA_PREFIX="/home/user/miniforge3/envs/myapp"
export PATH="/home/user/miniforge3/envs/myapp/bin:$PATH"
export MLIR_DIR="/home/user/miniforge3/envs/myapp/lib/cmake/mlir"
exec "/home/user/miniforge3/envs/myapp/bin/python3" \
     "/home/user/projects/myapp/tools/cli.py" "$@"
```

On Windows, dekk installs a `.cmd` launcher in the project's `.install`
directory so the command works from both Command Prompt and PowerShell
without requiring `Activate.ps1`.

From Python:
```python
from dekk import WrapperGenerator

result = WrapperGenerator.install_from_spec(
    spec_file=Path(".dekk.toml"),
    target=Path("tools/cli.py"),
    python=Path("/opt/conda/envs/myapp/bin/python3"),
    name="myapp",
)
```

## Installation

```bash
pipx install dekk
python -m pip install --upgrade dekk
python -m pip install --upgrade "dekk[tracking]"
python -m pip install --upgrade "dekk[all]"
```

## First Run

The default path should be simple:

```bash
dekk --help
dekk doctor
dekk init --example quickstart
```

That gives you a working CLI immediately, a system check, and a starter
`.dekk.toml` in the current directory.

If `dekk` is not found yet, use `python -m dekk --help` immediately.

If you want a built-in starter without writing files yet:

```bash
dekk example quickstart
dekk example conda --output .dekk.toml
```

Built-in templates live in
[examples/.dekk.toml.quickstart](examples/.dekk.toml.quickstart),
[examples/.dekk.toml.minimal](examples/.dekk.toml.minimal),
and [examples/.dekk.toml.conda](examples/.dekk.toml.conda).

Typical next steps:

```bash
# Python CLI from a repo with pyproject.toml
dekk install ./tools/cli.py

# POSIX shells
eval "$(dekk activate --shell bash)"

# Install a launcher after your project builds a target
dekk install ./bin/myapp --name myapp

# Remove a launcher again
dekk uninstall myapp
```

For Python scripts, `dekk install ./tools/cli.py` uses `pyproject.toml` to
create or refresh `.venv` automatically on first run. For binaries and
conda-backed projects, `dekk install` uses `.dekk.toml` to bake the
required environment into the installed command. When the install directory is
not already on `PATH`, dekk also appends the project's `.install` directory to
the active shell config when it can, then asks for a shell restart once.

Use `dekk uninstall <name>` to remove an installed launcher. Pass
`--remove-path` when you also want dekk to remove that project's PATH export
from the shell config.

```powershell
# PowerShell
Invoke-Expression (& dekk activate --shell powershell | Out-String)
dekk install .\dist\myapp.exe --name myapp
```

## Naming Conventions

dekk uses one name per surface area:

- **PyPI package**: `dekk`
- **Python import**: `dekk`
- **CLI command**: `dekk`
- **Project config file**: `.dekk.toml`
- **Default wrapper location**: `.install/` in the current project

That keeps installation, imports, command usage, and project setup distinct and predictable.

## CLI Framework

dekk includes a production-quality CLI framework built on Rich and Typer.
Use it as the foundation for your own CLI tools:

```python
from dekk import Typer, Option

app = Typer(
    name="myapp",
    auto_activate=True,      # auto-setup from .dekk.toml
    add_doctor_command=True,  # built-in health check
    add_version_command=True, # built-in version info
)

@app.command()
def build(release: bool = Option(True, "--release/--debug")):
    """Build the project."""
    ...

if __name__ == "__main__":
    app()
```

### Styled output

```python
from dekk import print_success, print_error, print_warning, print_info
from dekk import print_header, print_step, print_table

print_header("Building MyApp")
print_step("Compiling...")
print_success("Build complete!")
print_warning("Debug symbols not stripped")
```

### Progress indicators

```python
from dekk import spinner, progress_bar

with spinner("Installing dependencies..."):
    install_deps()

with progress_bar("Processing", total=100) as bar:
    for item in items:
        process(item)
        bar.advance()
```

### Structured errors

```python
from dekk import NotFoundError, DependencyError

raise NotFoundError(
    "Compiler not found",
    hint="Install the required toolchain for this project",
)
# Displays styled error with hint, exits with code 3
```

### Multi-format output

```python
from dekk import OutputFormatter, OutputFormat

fmt = OutputFormatter(format=OutputFormat.JSON)
fmt.print_result({"status": "ok", "version": "1.0"})
```

### LLM-friendly subprocess runner

```python
from dekk import run_logged

result = run_logged(
    ["cargo", "build", "--release"],
    log_path=Path(".logs/build.log"),
    spinner_text="Building...",
)
# Shows spinner, captures output to log, prints path for agents to read
```

## .dekk.toml Reference

### [project] -- required

```toml
[project]
name = "myapp"
description = "Optional description"
```

### [conda] -- conda/mamba environment

```toml
[conda]
name = "myapp"
file = "environment.yaml"
```

### [tools] -- required CLI tools

```toml
[tools]
python = { command = "python", version = ">=3.10" }
cmake  = { command = "cmake", version = ">=3.20" }
ninja  = { command = "ninja" }
cargo  = { command = "cargo", optional = true }
```

### [env] -- environment variables

```toml
[env]
MLIR_DIR = "{conda}/lib/cmake/mlir"
LLVM_DIR = "{conda}/lib/cmake/llvm"
MY_HOME  = "{project}"
```

Placeholders: `{project}` (project root), `{conda}` (conda prefix), `{home}` (user home)

### [paths] -- PATH prepends

```toml
[paths]
bin = ["{project}/bin", "{project}/target/release"]
```

## Examples by Language

### Python + Conda
```toml
[project]
name = "ml-pipeline"

[conda]
name = "ml-pipeline"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }
jupyter = { command = "jupyter" }

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

### C++ with CMake
```toml
[project]
name = "physics-sim"

[conda]
name = "physics-sim"
file = "environment.yaml"

[tools]
cmake = { command = "cmake", version = ">=3.20" }
ninja = { command = "ninja" }
clang = { command = "clang", version = ">=17" }

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

## For AI Agents

dekk reduces environment setup from 2000-5000 tokens to ~150 tokens:

**Before** (what agents had to explain):
> Check if conda is installed. If not, install miniforge. Create environment
> with `conda env create -f environment.yaml`. Activate with `conda activate
> myenv`. Set MLIR_DIR to the conda prefix. Export LD_LIBRARY_PATH...

**After**:
> Run `myapp install`. The wrapper handles everything.

## Detection API Summary

| Module | What it detects |
|--------|----------------|
| `PlatformDetector` | OS, arch, distro, WSL, containers, package manager |
| `CondaDetector` | Conda/mamba environments, packages, validation |
| `BuildSystemDetector` | 25+ build systems with targets and workspaces |
| `CompilerDetector` | GCC, Clang, Rust, Go with versions and targets |
| `CIDetector` | 14 CI providers with git metadata and runner info |
| `ShellDetector` | 9 shell types with config files and capabilities |
| `WorkspaceDetector` | Monorepos with dependency graphs and build order |
| `DependencyChecker` | CLI tool versions against constraints |
| `VersionManagerDetector` | pyenv, nvm, asdf, rbenv, rustup |
| `LockfileParser` | 7 lockfile formats across ecosystems |

## Architecture

dekk is organized in three tiers:

- **Tier 1 (Core)**: Foundational detection and config modules. Platform, conda, deps, workspace, config, remediation.
- **Tier 2 (Extended)**: Paths, build systems, compilers, shells, toolchains, versions, CI.
- **Tier 3 (Frameworks)**: Diagnostics, commands, scaffolding.

The CLI framework ships in the base `dekk` install.

## Documentation

- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [.dekk.toml Specification](docs/spec.md)
- [Wrapper Generation](docs/wrapper.md)
- [Examples by Language](docs/examples-by-language.md)
- [Contributing](docs/contributing.md)

## License

MIT
