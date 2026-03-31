# Git Worktree Management

`dekk worktree` wraps `git worktree` with automatic environment setup and
agent skill discovery.

## Commands

```bash
dekk worktree list                          # list all worktrees
dekk worktree create <branch>               # new worktree + branch from HEAD
dekk worktree create <branch> --base main   # branch from main
dekk worktree create <branch> --existing    # checkout existing branch
dekk worktree create <branch> --no-setup    # skip dekk setup
dekk worktree remove <name>                 # remove worktree
dekk worktree remove <name> --force         # force-remove with modifications
dekk worktree prune                         # clean stale references
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
    feature-login/                # dekk worktree create feature/login
    bugfix-crash/                 # dekk worktree create bugfix-crash
```

Branch names with slashes (e.g., `feature/login`) are sanitized to hyphens
in the directory name.

## Project Command Routing

Worktrees are fully integrated with dekk's project command system:

- `dekk` walks up from the current directory to find the nearest `.dekk.toml`
- All project commands (`dekk <app> <cmd>`) work from any worktree
- Each worktree gets its own working directory for builds, tests, etc.
- The `.agents/` source of truth is shared across worktrees (same git repo)

## Agent Skill

`dekk agents init` auto-scaffolds a `worktree` skill for git repos. This
teaches AI coding agents about worktree management so they can create
parallel work environments when appropriate.

The skill is created at `.agents/skills/worktree/SKILL.md` and is never
overwritten if it already exists.
