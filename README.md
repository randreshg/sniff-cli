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
