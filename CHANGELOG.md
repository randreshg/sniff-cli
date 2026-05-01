# Changelog

All notable changes to `dekk` will be documented in this file.

## 1.10.9 - 2026-05-01

- Fixed generated MCP server stubs to point regeneration instructions at
  `dekk <project> skills generate` instead of the removed `agents generate`
  command path.

## 1.10.8 - 2026-05-01

- Fixed embedded project `skills` commands to honor the configured
  `[agents].source` / `[skills].source` path for `generate`, `view`, `clean`,
  `status`, and `list` instead of assuming `.agents/`.
- Made `dekk <project> skills` default to `status`, so project skill discovery
  works as a useful no-argument command.
- Updated successful command skill hints to point at the configured source
  directory and shared skill path constants.
- Updated embedded skills help so usage displays as
  `dekk <project> skills ...`.

## 1.10.7 - 2026-04-17

- Fixed Claude Code hook commands to survive launch-from-subdirectory.
  Previously, `.claude/settings.json` emitted the `PreToolUse:Bash` guard
  with a project-relative path (e.g. `<src>/hooks/guard-build-tools.sh`),
  which failed with exit 127 ("No such file or directory") whenever
  Claude was started outside the project root — surfaced to the user as
  `PreToolUse:Bash hook error`. Settings-level hooks are now anchored to
  `$CLAUDE_PROJECT_DIR`:
  - Guard hook uses the absolute path `$CLAUDE_PROJECT_DIR/<src>/hooks/…`.
  - Auto-detected hooks (formatter / doctor) are wrapped with
    `cd "$CLAUDE_PROJECT_DIR" && …` so any project-relative references
    in the command body resolve correctly.
- Fixed the auto-formatter hook: replaced the non-existent `$FILEPATH`
  env var with a `jq`-based extraction of `.tool_input.file_path` from
  Claude Code's hook stdin payload, and short-circuits when the field is
  absent so the hook is safe for tools that don't carry `file_path`.
- Hardened the build-tool guard script: detects a missing `jq` and exits
  0 (allow) instead of 127 (error), so the hook never breaks the user's
  workflow on minimal systems. Switched `echo` to `printf '%s'` when
  piping the tool payload to `jq` to avoid backslash interpretation.
- Added regression tests under `tests/test_skills.py::TestClaudeHookGeneration`
  covering: formatter stdin parsing, settings.json guard anchoring to
  `$CLAUDE_PROJECT_DIR`, plugin `hooks.json` guard anchoring to
  `${CLAUDE_PLUGIN_ROOT}`, and uniform cwd-anchoring of all detected
  hooks in `settings.json`.

## 1.10.6 - 2026-04-12

- Fixed project commands losing `DYLD_LIBRARY_PATH` /
  `DYLD_FALLBACK_LIBRARY_PATH` on macOS. `run_project_command` now dispatches
  the `run` string directly via `subprocess.run(..., shell=False)` when it
  has no shell metacharacters, bypassing `/bin/sh` — which is SIP-restricted
  on Darwin and strips `DYLD_*` from the environment on exec, silently
  breaking env-based dylib resolution for project-local binaries.
- Added `command_needs_shell(cmd) -> bool` to the `DekkOS` OS-abstraction
  Protocol, implemented for POSIX (shell metachars: `| & ; < > $ \` * ? ~ \n`)
  and Windows (cmd.exe metachars + `.bat`/`.cmd` invocations). Commands that
  genuinely need a shell still route through `shell=True`.
- Replaced domain-flavored fixture names (`llm`, "LLM credentials",
  `register`/`credential`, `openai`) in tests and docstrings with neutral
  placeholders (`group`/`sub1`/`sub2`). dekk has no credential-handling
  feature; the prior examples implied one.

## 1.7.0 - 2026-04-02

- Added inline package declarations (`channels`, `packages`, `pip`) to
  `RuntimeEnvironmentSpec`, making `.dekk.toml` the single source of truth for
  environment dependencies. Projects no longer need a separate `environment.yaml`.
- Added `requires` field to `ComponentSpec` for declaring required tools;
  components with missing tools are skipped with a warning during install.
- `CondaEnv` now generates conda YAML at install time from inline package specs
  via `_generate_env_file()`, supporting three modes: external file, inline
  packages, or bare create.
- Threaded `channels`, `packages`, and `pip` through `DekkEnv` base class,
  resolver, and factory — all as plain primitives (project-agnostic).

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
