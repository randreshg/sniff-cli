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

If `.dekk.toml` is missing, `dekk install` and `dekk wrap` create a starter
file from the repo context first.

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

## Project Command Routing

All project commands go through `dekk <appname>`, which finds the nearest
`.dekk.toml` and runs with `cwd` set to that project root:

```bash
dekk myapp                   # project-aware help
dekk myapp --help
dekk myapp server --port 8080
dekk myapp build
dekk myapp test
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

## Built-in Project Tools

Built-in tools (`setup`, `agents`, `worktree`) are project-scoped — they require
the app name so dekk knows which project context to use:

```bash
dekk myapp setup
dekk myapp agents init
dekk myapp agents generate --target all
dekk myapp worktree create feature-x --base main
dekk myapp worktree list
```

Why the app name? Because `dekk` resolves paths from your current directory.
The app name selects the project (validates against `[project].name` in
`.dekk.toml`), and all paths resolve relative to that project root. This
makes every command worktree-safe — it works correctly from any checkout.

### Agents

Source of truth: `.agents/`

```bash
dekk myapp agents init
dekk myapp agents generate --target all
dekk myapp agents clean --target codex
dekk myapp agents install        # optional (installs Codex skills to ~/.codex/skills)
```

Generated files: `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md`, `.agents.json`

### Worktrees

```bash
dekk myapp worktree create feature-x --base main
dekk myapp worktree list
dekk myapp worktree remove feature-x
dekk myapp worktree prune
```

Worktrees with `.dekk.toml` get automatic environment setup on creation.
Auto-scaffolded as an agent skill via `dekk myapp agents init` for git repos.

## Inheriting Tools in Downstream CLIs

CLIs built with `dekk.Typer` can also inherit these tools directly,
useful when worktree isolation is not a concern:

```python
from dekk import Typer

app = Typer(
    name="myapp",
    auto_activate=True,
    add_doctor_command=True,
    add_version_command=True,
    add_worktree_command=True,
    add_agents_command=True,
)
```

## Docs

- [Getting Started](docs/getting-started.md)
- [.dekk.toml Specification](docs/spec.md)
- [Agent Workflows](docs/agents.md)
- [Worktree Management](docs/worktree.md)
