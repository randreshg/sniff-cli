# Wrapper Generation

## Overview

`dekk` can generate self-contained wrapper launchers that bake your entire
project environment into a single executable command. The wrapper sets conda
paths, environment variables, and PATH entries, then launches your target
binary.

No `conda activate`. No `source ~/.bashrc`. No manual PATH setup.

## Smallest Working Flow

If you are new to `dekk`, use this sequence first:

```bash
dekk init --example quickstart
```

Edit `.dekk.toml` so it matches your project, build your target, then:

```bash
dekk install ./bin/myapp --name myapp
myapp --help
```

That is the intended end state: users run the generated wrapper directly,
without activating anything first.

## How It Works

1. `dekk` reads your `.dekk.toml`
2. Resolves conda prefix, env vars, and paths via `EnvironmentSpec.expand_placeholders()`
3. Generates a platform-appropriate launcher with hardcoded absolute paths
4. Installs it to the user scripts directory, or to a custom directory you choose

The generated wrapper looks like this on POSIX:

```sh
#!/bin/sh
export CONDA_PREFIX="/home/user/miniforge3/envs/myapp"
export PATH="/home/user/miniforge3/envs/myapp/bin:/home/user/projects/myapp/bin:$PATH"
export MLIR_DIR="/home/user/miniforge3/envs/myapp/lib/cmake/mlir"
exec "/home/user/miniforge3/envs/myapp/bin/python3" \
     "/home/user/projects/myapp/tools/cli.py" "$@"
```

On Windows, `dekk` installs a `.cmd` launcher in Python's user scripts
directory by default. That is the `Scripts` directory under
`python -m site --user-base`. It matches the standard user-level scripts
directory used by Python packaging tools and avoids relying on `Activate.ps1`.

Every environment detail is resolved once at generation time and written as
literal strings. At runtime the launcher is trivial: set variables, prepend
paths, then run the target.

## CLI Usage

```text
dekk wrap <name> <target> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `name` | Name for the wrapper binary (what you type to run it) |
| `target` | Path to the binary or script to wrap |

**Options:**

| Option | Description |
|--------|-------------|
| `--python PATH` | Python interpreter for script targets |
| `--install-dir PATH`, `-d` | Installation directory (default: user scripts directory) |
| `--spec PATH`, `-s` | Path to `.dekk.toml` (default: auto-detect from cwd) |

**Examples:**

```bash
# Wrap a compiled binary
dekk wrap myapp ./target/release/myapp

# Wrap a Python script with a specific interpreter
dekk wrap myapp ./tools/cli.py --python /opt/conda/envs/myapp/bin/python3

# Install to a custom directory
dekk wrap myapp ./bin/myapp --install-dir /usr/local/bin

# Use a specific .dekk.toml
dekk wrap myapp ./bin/myapp --spec /path/to/.dekk.toml
```

```powershell
# Windows executable target
dekk wrap myapp .\dist\myapp.exe

# Windows Python script target
dekk wrap myapp .\tools\cli.py --python C:\miniforge3\envs\myapp\python.exe
```

After running, the wrapper is executable and ready to use:

```
$ myapp --version
myapp 1.0.0
```

## Python API

### WrapperGenerator.install_from_spec

The primary API for programmatic wrapper generation:

```python
from pathlib import Path
from dekk import WrapperGenerator

result = WrapperGenerator.install_from_spec(
    spec_file=Path(".dekk.toml"),
    target=Path("tools/cli.py"),
    python=Path("/opt/conda/envs/myapp/bin/python3"),
    name="myapp",
    install_dir=Path("/custom/install/dir"),  # optional
)

print(result.message)    # "Installed wrapper myapp -> /custom/install/dir/myapp"
print(result.bin_path)   # Path("/custom/install/dir/myapp")
print(result.in_path)    # True if the install dir is in PATH
```

### BinaryInstaller.install_wrapper

Lower-level API available via `BinaryInstaller`:

```python
from pathlib import Path
from dekk import BinaryInstaller

installer = BinaryInstaller(project_root=Path("."))
result = installer.install_wrapper(
    target=Path("./bin/myapp"),
    name="myapp",
)
```

## How Projects Use It

A typical project install command generates the wrapper as part of setup:

```python
# In your project's install command
from pathlib import Path
from dekk import WrapperGenerator

def install():
    """Build and install the project."""
    # ... build steps ...

    # Generate wrapper that bakes in the full environment
    WrapperGenerator.install_from_spec(
        spec_file=Path(".dekk.toml"),
        target=Path("target/release/myapp"),
        name="myapp",
    )
```

End users then just run:

```bash
$ myapp doctor    # works immediately -- no activation needed
$ myapp build     # full environment is set up by the wrapper
```

## Regeneration

When your environment changes (conda update, new dependencies, new env vars
in `.dekk.toml`), re-run your project's install command or `dekk wrap` to
regenerate the wrapper. The old wrapper is overwritten in place.

```bash
# After updating conda or .dekk.toml
dekk wrap myapp ./bin/myapp
```

## Technical Details

- Uses `#!/bin/sh` on POSIX and `.cmd` launchers on Windows
- Hardcoded absolute paths -- no runtime detection overhead
- `exec` replaces the wrapper process (clean PID, proper signal handling)
- `"$@"` passes all arguments through to the target unchanged
- Proper shell escaping for values with special characters
- POSIX wrappers are marked executable (`chmod 755`) automatically
- Default install directory follows Python's user scripts convention
- If the install directory is not in `PATH`, `dekk` reports this and suggests adding it
