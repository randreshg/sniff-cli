# Agent Workflows

`dekk` can manage agent-facing project instructions from a single source of
truth. The workflow starts with a project-local `.agents/` directory and then
generates target-specific outputs for Claude, Codex, Cursor, and Copilot.

## Model

`dekk` treats `.agents/` as the editable source of truth:

- `project.md` holds repo-wide guidance.
- `skills/<name>/SKILL.md` holds reusable task-specific instructions.
- `rules/*.md` can hold target-specific or per-directory guidance.
- `agents-reference.md` is optional and, when present, becomes the source for
  generated `AGENTS.md`.

Generated outputs are derived from that source directory:

- `AGENTS.md`
- `CLAUDE.md`
- `.cursorrules`
- `.github/copilot-instructions.md`
- `.agents.json`

## CLI

Initialize the source-of-truth directory:

```bash
dekk agents init
```

If `.dekk.toml` is missing, `dekk agents init` auto-creates a starter file from
`pyproject.toml`, `package.json`, `Cargo.toml`, `environment.yaml`, or the repo
name before scaffolding `.agents/`.

Generate agent config files:

```bash
dekk agents generate --target all
```

Clean generated files while keeping `.agents/` as the source of truth:

```bash
dekk agents clean --target all
dekk agents clean --target codex
```

Install Codex skills into the local Codex skills directory:

```bash
dekk agents install
```

Inspect the current source and generated outputs:

```bash
dekk agents status
dekk agents list
```

Generate flow scaffolding:

```bash
dekk agents flow review
dekk agents flow triage
```

## `.dekk.toml`

Two sections matter for agent workflows.

`[commands]` defines runnable project commands. When `dekk agents init`
scaffolds `.agents/`, those commands are converted into starter skill
templates.

```toml
[commands]
build = { run = "make", description = "Build from source" }
test = { run = "pytest -q", description = "Run test suite" }
```

`[agents]` customizes the source directory and generation targets:

```toml
[agents]
source = ".agents"
targets = ["claude", "codex", "copilot", "cursor"]
```

If omitted, those values are the defaults.

Example auto-generated starter config for a Python repo:

```toml
[project]
name = "demo-app"

[tools]
python = { command = "python" }

[python]
pyproject = "pyproject.toml"

[commands]
build = { run = "python -m build", description = "Build the project" }
test = { run = "pytest -q", description = "Run the test suite" }
```

## Recommended Flow

1. Run `dekk agents init`.
2. Let dekk auto-create `.dekk.toml` if the repo does not have one yet.
3. Edit `.dekk.toml` if you want to refine `[commands]` or `[agents]`.
4. Edit `.agents/project.md` and any generated `skills/*/SKILL.md`.
5. Run `dekk agents generate --target all`.
6. Commit both `.agents/` and the generated target files if your repo expects
   those outputs to stay in sync.

## Agent Abstraction

Generation targets implement a small `DekkAgent` contract. The built-in
targets are Claude Code, Codex, Cursor, and Copilot, and `AgentConfigManager`
can also accept custom agents for additional targets.

The built-ins now live in dedicated provider modules under
`src/dekk/agents/providers/` instead of one large generator file.

## Notes

- `AGENTS.md` is the Codex-facing generated file in the project root.
- `dekk agents install` is only for Codex skill installation into the local
  Codex home; it does not replace generated project files.
- The feature is project-root aware and walks upward to find either `.agents/`
  or `.dekk.toml`, so it works correctly from nested directories inside a repo.
