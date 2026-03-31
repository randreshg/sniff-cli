# Getting Started with dekk

`dekk` is both a command-line tool and a reusable Python package. Start
with the CLI flow first. Once that works, move to the detection and library
APIs.

## Installation

```bash
# Recommended for the CLI tool
pipx install dekk

# Standard Python install
python -m pip install --upgrade dekk
```

Verify the command first:

```bash
dekk --help
dekk doctor
```

If `dekk` is not on `PATH` yet, use:

```bash
python -m dekk --help
```

On Windows, use PowerShell for activation output:

```powershell
dekk --help
Invoke-Expression (& dekk activate --shell powershell | Out-String)
```

## First Commands

```bash
dekk --help
dekk doctor
dekk install ./tools/cli.py
```

That sequence is the intended onboarding path:

- `dekk --help` confirms the command is installed correctly.
- `dekk doctor` checks the current machine and toolchain state.
- `dekk install ./tools/cli.py` will auto-create `.dekk.toml` if the repo does not have one yet.

Use `dekk init --example quickstart` when you want to start from an explicit template instead of detection.

For ready-to-use starter configs, see
[`examples/.dekk.toml.quickstart`](../examples/.dekk.toml.quickstart)
and [`examples/.dekk.toml.minimal`](../examples/.dekk.toml.minimal), or print them directly with:

```bash
dekk example quickstart
dekk example conda
```

For agent-oriented projects, there is also a built-in agent template:

```bash
dekk agents init
dekk agents generate --target all
```

## First End-to-End Flow

This is the smallest reliable workflow for a new project:

1. Install `dekk`.
2. Confirm the command works with `dekk --help`.
3. Run `dekk doctor`.
4. Build one real target in your repo.
5. Run `dekk install <target>` or `dekk wrap <name> <target>`.
6. Let dekk auto-create `.dekk.toml` from the repo if needed.
7. Edit `.dekk.toml` only if you want to refine commands, tools, or environment settings.
8. Run the generated wrapper directly.

Example:

```bash
dekk install ./tools/cli.py
dekk install ./bin/myapp --name myapp
myapp --help
```

PowerShell example:

```powershell
dekk install .\dist\myapp.exe --name myapp
myapp --help
```

For Python projects, dekk uses `pyproject.toml` to seed `.dekk.toml` and wraps
the target with the active project interpreter, local `.venv`, or an explicit
`--python` override. For binaries and conda-backed projects, dekk uses the
nearest build files plus any `environment.yaml` it finds. In all cases, the
launcher is written to `./.install` by default and dekk can add that directory
to your shell config automatically.

## Agent Setup

If the repo needs agent instructions checked into source control, use the
agent workflow:

```bash
dekk agents init
dekk agents generate --target all
dekk agents status
```

`dekk agents init` will auto-create `.dekk.toml` first when needed, then create
`.agents/` and starter skills from `[commands]`.

See [Agent Workflows](agents.md) for the full model.

## Using The Library APIs

### Platform Detection

```python
from dekk import PlatformDetector

detector = PlatformDetector()
platform = detector.detect()

print(platform.os)          # "Linux"
print(platform.arch)        # "x86_64"
print(platform.distro)      # "ubuntu"
print(platform.is_wsl)      # False
print(platform.is_container) # True/False
```

### Check Dependencies

```python
from dekk import DependencyChecker, DependencySpec

checker = DependencyChecker()
result = checker.check(DependencySpec("Python", "python3", min_version="3.11"))

if result.ok:
    print(f"Python {result.version} found at {result.path}")
else:
    print(f"Python not found or below minimum version")
```

### Detect Conda Environment

```python
from dekk import CondaDetector

detector = CondaDetector()
env = detector.find_active()

if env:
    print(f"Active conda env: {env.name}")
    print(f"Python: {env.python_version}")
    print(f"Location: {env.prefix}")
```

### CI/CD Detection

```python
from dekk import CIDetector

detector = CIDetector()
ci = detector.detect()

if ci.is_ci:
    print(f"Running in {ci.provider} CI")
    print(f"Branch: {ci.branch}")
    print(f"Commit: {ci.commit_sha}")
```

### Workspace/Monorepo Detection

```python
from dekk import WorkspaceDetector
from pathlib import Path

detector = WorkspaceDetector()
workspaces = detector.detect(Path.cwd())

for ws in workspaces:
    print(f"{ws.kind} workspace with {ws.project_count} projects")
    for project in ws.projects:
        print(f"  - {project.name} at {project.path}")
```

### Configuration Management

```python
from dekk import ConfigManager

config = ConfigManager("myapp", defaults={"database": {"path": "/tmp/db"}})

# Read config (checks env vars, project config, user config, system config)
db_path = config.get("database.path")

# Set config
config.set("api.timeout", 30)
config.save()  # Writes to project config file
```

### Tool Version Checking

```python
from dekk import ToolChecker

checker = ToolChecker()

# Check if tool exists
cmake_path = checker.which("cmake")
if cmake_path:
    version = checker.get_version("cmake")
    print(f"CMake {version} at {cmake_path}")
```

## Core Concepts

### Detection-Only Philosophy

dekk never modifies your environment. All detectors are **pure**:
- No subprocess calls that change state
- No file writes (unless explicitly saving config)
- No network requests
- Returns frozen dataclasses (immutable)

### Always Succeeds

Detection methods never raise exceptions for "not found" cases:

```python
platform = detector.detect()  # Always returns PlatformInfo
env = conda.find_active()      # Returns None if no conda env active
result = checker.check(spec)   # Returns DependencyResult with found=False
```

### Composable Detectors

Each detector is independent:

```python
from dekk import PlatformDetector, CondaDetector, CIDetector

platform = PlatformDetector().detect()
conda = CondaDetector().find_active()
ci = CIDetector().detect()

# Build complete picture
print(f"Platform: {platform.os} {platform.arch}")
print(f"Conda: {conda.name if conda else 'not active'}")
print(f"CI: {ci.provider if ci.is_ci else 'local'}")
```

## Common Patterns

### Environment Health Check

```python
from dekk import PlatformDetector, DependencyChecker, DependencySpec

platform = PlatformDetector().detect()
checker = DependencyChecker()

required_tools = [
    DependencySpec("Python", "python3", min_version="3.11"),
    DependencySpec("Git", "git"),
    DependencySpec("Docker", "docker"),
]

print(f"Platform: {platform.os} {platform.arch}")
for spec in required_tools:
    result = checker.check(spec)
    status = "✓" if result.ok else "✗"
    print(f"{status} {spec.name}: {result.version or 'not found'}")
```

### Adaptive Install Commands

```python
from dekk import PlatformDetector

platform = PlatformDetector().detect()

if platform.pkg_manager == "apt":
    print("sudo apt install cmake")
elif platform.pkg_manager == "brew":
    print("brew install cmake")
elif platform.pkg_manager == "dnf":
    print("sudo dnf install cmake")
```

### Project Context Detection

```python
from dekk import WorkspaceDetector, CondaDetector, CIDetector
from pathlib import Path

workspace = WorkspaceDetector().detect_first(Path.cwd())
conda = CondaDetector().find_active()
ci = CIDetector().detect()

if workspace:
    print(f"Project type: {workspace.kind}")
    print(f"Projects: {workspace.project_count}")

if conda:
    print(f"Python env: conda ({conda.name})")
elif ci.is_ci:
    print(f"Python env: CI ({ci.provider})")
else:
    print("Python env: system")
```

## Extension: Remediation

dekk is detection-only, but provides a Protocol for consumers to implement fixes:

```python
from dekk.diagnostics.remediate import Remediator, DetectedIssue, FixResult
from typing_extensions import runtime_checkable

@runtime_checkable
class MyRemediator(Remediator):
    @property
    def name(self) -> str:
        return "my-fixer"

    def can_fix(self, issue: DetectedIssue) -> bool:
        return issue.category == "missing_python"

    def fix(self, issue: DetectedIssue, dry_run: bool = False) -> FixResult:
        # Implement fix logic (e.g., conda install python=3.11)
        ...
```

See `src/dekk/remediate.py` for the full Protocol definition.

## Next Steps

- **[Architecture](architecture.md)** — Module organization and extension points
- **[Examples by Language](examples-by-language.md)** — Configs for Python, Rust, C++, Node, Go, Java
- **README** — CLI framework usage (`dekk.Typer`, `dekk.cli.styles`, errors, progress)
