# Git Worktree Management

dekk provides worktree management as a built-in command that downstream CLIs
inherit. Any CLI built with `dekk.Typer(add_worktree_command=True)` gets the
full `worktree` sub-app.

## Commands

```bash
<cli> worktree list                          # list all worktrees
<cli> worktree create <branch>               # new worktree + branch from HEAD
<cli> worktree create <branch> --base main   # branch from main
<cli> worktree create <branch> --existing    # checkout existing branch
<cli> worktree create <branch> --no-setup    # skip dekk setup
<cli> worktree remove <name>                 # remove worktree
<cli> worktree remove <name> --force         # force-remove with modifications
<cli> worktree prune                         # clean stale references
```

Replace `<cli>` with your project's CLI name (e.g., `apxm worktree list`).

## Enabling in Your CLI

```python
from dekk import Typer

app = Typer(
    name="myapp",
    add_worktree_command=True,   # adds `myapp worktree` sub-app
    add_agents_command=True,     # adds `myapp agents` sub-app
    add_doctor_command=True,
)
```

## Automatic Environment Setup

When a worktree is created and `.dekk.toml` exists in the new worktree,
`dekk setup` runs automatically to prepare the environment. Skip this with
`--no-setup`.

## Worktree Layout

By default, worktrees are created at `../<repo>-worktrees/<branch>`:

```
~/projects/
  myapp/                          # main worktree
  myapp-worktrees/
    feature-login/                # worktree create feature/login
    bugfix-crash/                 # worktree create bugfix-crash
```

Branch names with slashes (e.g., `feature/login`) are sanitized to hyphens
in the directory name.

## Project Command Routing

Worktrees are fully integrated with dekk's project command system:

- The CLI walks up from the current directory to find the nearest `.dekk.toml`
- All project commands work from any worktree
- Each worktree gets its own working directory for builds, tests, etc.
- The `.agents/` source of truth is shared across worktrees (same git repo)

## Agent Skill

`<cli> agents init` auto-scaffolds a `worktree` skill for git repos. This
teaches AI coding agents about worktree management so they can create
parallel work environments when appropriate.

The skill is created at `.agents/skills/worktree/SKILL.md` and is never
overwritten if it already exists.
