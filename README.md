# dekk

Make project CLIs runnable with one config and zero manual activation.

## Install

```bash
pipx install dekk
```

Fallback:

```bash
python -m pip install --upgrade dekk
```

## Minimal Setup

```bash
dekk install ./tools/cli.py
```

If `.dekk.toml` is missing, `dekk install`, `dekk wrap`, and `dekk agents init`
create a starter file from the repo context first.

Explicit template-driven setup is still available:

```bash
dekk init --example conda
eval "$(dekk activate --shell bash)"
```

Optional (no activation after this):

```bash
dekk wrap myapp ./tools/cli.py
```

Worktree-safe default:

```bash
dekk install ./tools/cli.py        # no shell rc PATH edits by default
dekk install ./tools/cli.py --update-shell
```

Project command routing (uses nearest `.dekk.toml`):

```bash
dekk myapp server --port 8080
```

This is worktree-friendly by default:

- `dekk` walks up from your current directory to find the nearest `.dekk.toml`
- the app name must match `[project].name`
- the command runs with `cwd` set to that project root, not whatever nested
  directory you happened to be in
- activation is scoped to that project config before the command runs

That means `dekk myapp server` works correctly from a repo root, a nested
subpackage, or a separate Git worktree for the same project, without relying
on global shell state.

## Agents

Source of truth: `.agents/`

```bash
dekk agents init
dekk agents generate --target all
dekk agents clean --target codex
dekk agents install        # optional (installs Codex skills to ~/.codex/skills)
```

Generated files (examples): `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md`, `.agents.json`

## Docs

- [Getting Started](docs/getting-started.md)
- [.dekk.toml Specification](docs/spec.md)
- [Agent Workflows](docs/agents.md)
