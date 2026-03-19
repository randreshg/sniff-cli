# Examples

The built-in examples are the fastest way to get started with `sniff-cli`.

## Recommended Order

1. Install the package: `pipx install sniff-cli`
2. Verify the command works: `sniff --help`
3. Check the current machine: `sniff doctor`
4. Create a starter config: `sniff init --example quickstart`
5. Build one real target in your project
6. Wrap that target: `sniff wrap myapp ./bin/myapp`

If `sniff` is not on `PATH` yet, use `python -m sniff_cli --help` first.

## Built-in Templates

- `.sniff-cli.toml.quickstart` is the best default for most projects.
- `.sniff-cli.toml.minimal` is the smallest valid config.
- `.sniff-cli.toml.conda` is the best starting point for conda-backed projects.

You can print them directly:

```bash
sniff example quickstart
sniff example minimal
sniff example conda
```

Or write one into the current directory:

```bash
sniff init --example quickstart
sniff example conda --output .sniff-cli.toml
```

## Example Flows

Minimal Python script:

```bash
sniff init --example quickstart
sniff wrap myapp ./tools/cli.py --python /path/to/python
myapp --help
```

Compiled binary:

```bash
sniff init --example minimal
sniff wrap myapp ./target/release/myapp
myapp --version
```

Windows PowerShell:

```powershell
sniff --help
sniff init --example quickstart
sniff wrap myapp .\dist\myapp.exe
myapp --help
```
