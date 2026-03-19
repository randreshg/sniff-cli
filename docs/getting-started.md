# Getting Started with sniff-cli

`sniff-cli` is both a command-line tool and a reusable Python package. Start
with the CLI flow first. Once that works, move to the detection and library
APIs.

## Installation

```bash
# Recommended for the CLI tool
pipx install sniff-cli

# Standard Python install
python -m pip install --upgrade sniff-cli
```

Verify the command first:

```bash
sniff --help
sniff doctor
```

If your scripts directory is not on `PATH` yet, use:

```bash
python -m sniff_cli --help
```

On Windows, use PowerShell for activation output:

```powershell
sniff --help
Invoke-Expression (& sniff activate --shell powershell | Out-String)
```

## First Commands

```bash
sniff --help
sniff doctor
sniff init --example quickstart
```

That sequence is the intended onboarding path:

- `sniff --help` confirms the command is installed correctly.
- `sniff doctor` checks the current machine and toolchain state.
- `sniff init --example quickstart` creates a starter `.sniff-cli.toml` in the current directory.

For ready-to-use starter configs, see
[`examples/.sniff-cli.toml.quickstart`](../examples/.sniff-cli.toml.quickstart)
and [`examples/.sniff-cli.toml.minimal`](../examples/.sniff-cli.toml.minimal), or print them directly with:

```bash
sniff example quickstart
sniff example conda
```

## First End-to-End Flow

This is the smallest reliable workflow for a new project:

1. Install `sniff-cli`.
2. Confirm the command works with `sniff --help`.
3. Run `sniff doctor`.
4. Create a starter config with `sniff init --example quickstart`.
5. Edit `.sniff-cli.toml` so it matches your project.
6. Build one real target in your repo.
7. Run `sniff install <target>` or `sniff wrap <name> <target>`.
8. Run the generated wrapper directly.

Example:

```bash
sniff install ./tools/cli.py

sniff init --example quickstart
sniff install ./bin/myapp --name myapp
myapp --help
```

PowerShell example:

```powershell
sniff init --example quickstart
sniff install .\dist\myapp.exe --name myapp
myapp --help
```

For Python scripts, `sniff install ./tools/cli.py` expects a nearby
`pyproject.toml` and bootstraps `.venv` automatically on first run.
For binaries and conda-backed projects, prefer `.sniff-cli.toml` plus
`sniff install <target>`.

## Using The Library APIs

### Platform Detection

```python
from sniff_cli import PlatformDetector

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
from sniff_cli import DependencyChecker, DependencySpec

checker = DependencyChecker()
result = checker.check(DependencySpec("Python", "python3", min_version="3.11"))

if result.ok:
    print(f"Python {result.version} found at {result.path}")
else:
    print(f"Python not found or below minimum version")
```

### Detect Conda Environment

```python
from sniff_cli import CondaDetector

detector = CondaDetector()
env = detector.find_active()

if env:
    print(f"Active conda env: {env.name}")
    print(f"Python: {env.python_version}")
    print(f"Location: {env.prefix}")
```

### CI/CD Detection

```python
from sniff_cli import CIDetector

detector = CIDetector()
ci = detector.detect()

if ci.is_ci:
    print(f"Running in {ci.provider} CI")
    print(f"Branch: {ci.branch}")
    print(f"Commit: {ci.commit_sha}")
```

### Workspace/Monorepo Detection

```python
from sniff_cli import WorkspaceDetector
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
from sniff_cli import ConfigManager

config = ConfigManager("myapp", defaults={"database": {"path": "/tmp/db"}})

# Read config (checks env vars, project config, user config, system config)
db_path = config.get("database.path")

# Set config
config.set("api.timeout", 30)
config.save()  # Writes to project config file
```

### Tool Version Checking

```python
from sniff_cli import ToolChecker

checker = ToolChecker()

# Check if tool exists
cmake_path = checker.which("cmake")
if cmake_path:
    version = checker.get_version("cmake")
    print(f"CMake {version} at {cmake_path}")
```

## Core Concepts

### Detection-Only Philosophy

sniff-cli never modifies your environment. All detectors are **pure**:
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
from sniff_cli import PlatformDetector, CondaDetector, CIDetector

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
from sniff_cli import PlatformDetector, DependencyChecker, DependencySpec

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
from sniff_cli import PlatformDetector

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
from sniff_cli import WorkspaceDetector, CondaDetector, CIDetector
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

sniff-cli is detection-only, but provides a Protocol for consumers to implement fixes:

```python
from sniff_cli.remediate import Remediator, DetectedIssue, FixResult
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

See `src/sniff_cli/remediate.py` for the full Protocol definition.

## Next Steps

- **[Architecture](architecture.md)** — Module organization and extension points
- **[Examples by Language](examples-by-language.md)** — Configs for Python, Rust, C++, Node, Go, Java
- **README** — CLI framework usage (`sniff_cli.Typer`, `sniff_cli.cli.styles`, errors, progress)
