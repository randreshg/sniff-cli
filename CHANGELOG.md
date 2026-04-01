# Changelog

All notable changes to `dekk` will be documented in this file.

## 1.5.1 - 2026-03-31

- Added native project help for `dekk <app>` / `dekk <app> --help` /
  `dekk <app> help [command]`, with command descriptions sourced from
  `.dekk.toml` plus built-in project tools.
- Added project-scoped `dekk <app> setup` routing so runtime setup works in the
  same worktree-safe command model as other project commands.
- Fixed missing-runtime hints to suggest `dekk <app> setup` instead of the
  global `dekk setup` path.
- Updated worktree auto-setup to prefer `dekk <app> setup` when the worktree
  contains a readable `.dekk.toml`.
- Updated docs to reflect the project-aware help and setup flows.

## 1.3.0 - 2026-03-31

- Refactored environment, agents, and path infrastructure into sub-packages
  (`dekk.environment`, `dekk.execution`, `dekk.detection`, `dekk.diagnostics`).
- Added `dekk setup`: automated conda env creation and npm package provisioning
  via new `[conda.packages]` and `[npm]` sections in `.dekk.toml`.
- Added `dekk agents flow <template>` command for acpx flow template generation
  (review, triage, echo starters customized with project skills).
- Added worktree-safe project command routing with `dekk.project.runner`.
- Documented worktree-safe project command routing in guides and architecture docs.

## 1.2.0 - 2026-03-30

- Added `dekk agents` module: single source-of-truth agent config generation.
- `create_agents_app()` factory for init/generate/install/status/list commands.
- Skill and rule discovery with YAML frontmatter parsing.
- Per-target generators for Claude Code, Codex, Cursor, and Copilot.
- Codex skill installation to `~/.codex/skills/`.
- Smart scaffolding from Typer introspection and `.dekk.toml` commands.
- `agent_skill=True` decorator support for command-to-skill conversion.
- Added `CommandSpec` and `AgentsSpec` dataclasses for `.dekk.toml`.

## 1.1.0 - 2026-03-20

- Export `Context` from `dekk.typer_app` so consumers can use `from dekk import Context`
  instead of importing directly from `typer`.

## 1.0.1 - 2026-03-19

- Added project-local install and uninstall APIs for generated launchers.
- Centralized shell PATH updates in `dekk` for wrapper and shim installs.
- Added OS-aware shell config handling through the shared installer layer.
- Refreshed CI workflows and fixed repo lint, typing, and test drift.

## 1.0.0 - 2026-03-19

First public `dekk` release.

- Renamed the published distribution to `dekk`.
- Renamed the Python import package to `dekk`.
- Renamed the default config file to `.dekk.toml`.
- Standardized the console entrypoint as `dekk`.
- Cleaned up repository metadata, developer docs, and packaging surfaces for reuse.
- Added CI coverage for linting, typing, tests, and package builds.
