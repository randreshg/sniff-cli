# Examples

The built-in examples are the fastest way to get started with `dekk`.

## Recommended Order

1. Install the package: `pipx install dekk`
2. Verify the command works: `dekk --help`
3. Check the current machine: `dekk doctor`
4. Create a starter config: `dekk init --example quickstart`
5. Build one real target in your project
6. Wrap that target: `dekk wrap myapp ./bin/myapp`

If `dekk` is not on `PATH` yet, use `python -m dekk --help` first.

## Built-in Templates

- `.dekk.toml.quickstart` is the best default for most projects.
- `.dekk.toml.minimal` is the smallest valid config.
- `.dekk.toml.conda` is the best starting point for conda-backed projects.

You can print them directly:

```bash
dekk example quickstart
dekk example minimal
dekk example conda
```

Or write one into the current directory:

```bash
dekk init --example quickstart
dekk example conda --output .dekk.toml
```

## Example Flows

Minimal Python script:

```bash
dekk init --example quickstart
dekk wrap myapp ./tools/cli.py --python /path/to/python
myapp --help
```

Compiled binary:

```bash
dekk init --example minimal
dekk wrap myapp ./target/release/myapp
myapp --version
```

Windows PowerShell:

```powershell
dekk --help
dekk init --example quickstart
dekk wrap myapp .\dist\myapp.exe
myapp --help
```
