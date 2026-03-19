# dekk Documentation

**One config. Zero activation. Any project.**

dekk is a development environment library and CLI framework. Declare your
environment in `.dekk.toml`, and dekk handles detection, activation, and
wrapper generation -- for any language, any shell, any CI provider.

Start with:

```bash
pipx install dekk
dekk doctor
dekk init --example quickstart
```

If your scripts directory is not on `PATH` yet:

```bash
python -m dekk --help
```

## Three Pillars

- **Detect** -- Platform, conda, build systems, compilers, CI, shells, workspaces.
- **Activate** -- Read `.dekk.toml`, resolve conda paths, set env vars, validate tools. Example: `eval "$(dekk activate --shell bash)"` or `Invoke-Expression (& dekk activate --shell powershell | Out-String)`.
- **Wrap** -- Generate a self-contained launcher that bakes in the full environment. No manual activation ever again.

## Docs

- **[Getting Started](getting-started.md)** -- Installation, quick start, core concepts
- **[.dekk.toml Specification](spec.md)** -- Canonical reference for the config file format
- **[Wrapper Generation](wrapper.md)** -- How `dekk wrap` creates zero-activation executables
- **[Quick Reference](cheatsheet.md)** -- One-page cheat sheet for `.dekk.toml` and CLI commands
- **[Examples by Language](examples-by-language.md)** -- Configs for Python, Rust, C++, Node, Go, Java, and multi-language projects
- **[Architecture](architecture.md)** -- Module organization, tiers, extension points
- **[Contributing](contributing.md)** -- How to contribute

For API details, use the library’s docstrings and type hints; the code is the source of truth.
