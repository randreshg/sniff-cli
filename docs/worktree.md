# Git Worktree Management

dekk provides worktree management as a built-in project tool. All worktree
commands require the app name so dekk resolves the correct project context:

```bash
dekk myapp worktree <command>
```

## Commands

```bash
dekk myapp worktree list                          # list all worktrees
dekk myapp worktree create <branch>               # new worktree + branch from HEAD
dekk myapp worktree create <branch> --base main   # branch from main
dekk myapp worktree create <branch> --existing    # checkout existing branch
dekk myapp worktree create <branch> --no-setup    # skip environment setup
dekk myapp worktree remove <name>                 # remove worktree
dekk myapp worktree remove <name> --force         # force-remove with modifications
dekk myapp worktree prune                         # clean stale references
```

Replace `myapp` with your project name from `[project].name` in `.dekk.toml`.

**Alternative** — downstream CLIs can inherit the command via
`Typer(add_worktree_command=True)`, but the `dekk` entry point is
preferred for worktree safety.

## Automatic Environment Setup

When a worktree is created and `.dekk.toml` exists in the new worktree,
`dekk <appname> setup` runs automatically to prepare the environment. Skip this
with `--no-setup`.

## Worktree Layout

By default, worktrees are created at `../<repo>-worktrees/<branch>`:

```
~/projects/
  myapp/                          # main worktree
  myapp-worktrees/
    feature-login/                # dekk myapp worktree create feature/login
    bugfix-crash/                 # dekk myapp worktree create bugfix-crash
```

Branch names with slashes (e.g., `feature/login`) are sanitized to hyphens
in the directory name.

## Why `dekk <appname>` Instead of Direct Binaries

Installed wrapper binaries (e.g., `myapp`) bake absolute paths into the
script at install time. From a worktree, those paths still point to the
original checkout.

`dekk` resolves dynamically: it walks up from your current directory to find
the nearest `.dekk.toml`, then runs with `cwd` set to that project root. This
means `dekk myapp worktree`, `dekk myapp build`, and all other dekk commands
work correctly from any worktree without reconfiguration.

## Project Command Routing

Worktrees are fully integrated with dekk's project command system:

```bash
cd ~/projects/myapp-worktrees/feature-login
dekk myapp build          # finds this worktree's .dekk.toml
dekk myapp test           # runs in this worktree, not the main checkout
```

- Each worktree gets its own working directory for builds, tests, etc.
- The `.agents/` source of truth is shared across worktrees (same git repo)

## Agent Skill

`dekk myapp agents init` auto-scaffolds a `worktree` skill for git repos. This
teaches AI coding agents about worktree management so they can create
parallel work environments when appropriate.

The skill is created at `.agents/skills/worktree/SKILL.md` and is never
overwritten if it already exists.
