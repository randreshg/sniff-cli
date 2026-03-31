# Agent Config Management

The `agents` sub-app manages agent-facing project instructions from a single
source of truth. You edit one directory (`.agents/`), and it generates
target-specific outputs for Claude Code, Codex, Cursor, Copilot, and a
machine-readable manifest.

> **Note:** Throughout this doc, `<cli>` refers to your project's CLI name
> (e.g., `myapp`). Enable with `Typer(add_agents_command=True)`.

## Data Flow

```
.dekk.toml [commands]
       │
       ▼
 <cli> agents init ──► .agents/             (source of truth — user curated)
                       ├── project.md
                       ├── skills/
                       │   ├── build/SKILL.md
                       │   └── test/SKILL.md
                       └── rules/
                           └── tests.md
       │
       ▼
 <cli> agents generate ──► target configs   (generated — can be regenerated)
                           ├── CLAUDE.md
                           ├── .claude/skills/          (synced skills)
                           │   └── skills_index.md      (auto-generated routing)
                           ├── .claude/rules/           (path-scoped rules)
                           ├── AGENTS.md
                           ├── .cursorrules
                           ├── .github/copilot-instructions.md
                           ├── .github/instructions/    (per-directory rules)
                           └── .agents.json             (machine-readable manifest)
```

## Quick Start

```bash
<cli> agents init                  # scaffold .agents/ from project detection
<cli> agents generate --target all # generate all agent configs
<cli> agents status                # verify everything is in sync
```

## Source of Truth: `.agents/`

The `.agents/` directory is the single place you edit. **Commit it to git.**
Everything else (`CLAUDE.md`, `.cursorrules`, etc.) is derived and can be
regenerated at any time with `<cli> agents generate`.

`<cli> agents init` will prompt for confirmation if `.agents/` already exists
to prevent accidental changes. Use `--force` to bypass the prompt.

### Directory structure

```
.agents/
├── project.md                     # repo-wide guidance (required)
├── agents-reference.md            # optional override for AGENTS.md content
├── skills/
│   ├── build/
│   │   └── SKILL.md               # skill definition
│   └── test/
│       └── SKILL.md
└── rules/
    └── tests.md                   # path-scoped rule
```

### `project.md`

The main project instruction file. Its content becomes the body of each
generated agent config (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`,
`copilot-instructions.md`). Write it as generic agent guidance — build
instructions, project conventions, architecture notes.

### `skills/<name>/SKILL.md`

Each skill lives in its own directory under `skills/`. The `SKILL.md` file
uses YAML frontmatter followed by markdown instructions.

**Frontmatter fields:**

| Field           | Required | Description                              |
|-----------------|----------|------------------------------------------|
| `name`          | yes      | Skill identifier (must match folder name)|
| `description`   | yes      | One-line description of what the skill does |
| `user-invocable`| no       | `true` if the skill can be triggered via `/skill-name` |

**Example:**

```markdown
---
name: build
description: Build the project from source
user-invocable: true
---

# Build

Run `make` to compile the project.

## Prerequisites

- GCC 12+ or Clang 15+
- CMake 3.20+
```

The body after the `---` closing fence is the skill's full instruction set.
Agents load this when they need the skill's detailed steps.

Skills can contain additional files alongside `SKILL.md` (scripts, templates,
etc.) — they will be synced to target skill directories.

### Skills Index (routing layer)

`<cli> agents generate` auto-generates a `skills_index.md` file in each
target's skills directory (e.g., `.claude/skills/skills_index.md`). This gives
agents a lightweight lookup table so they can pick the right skill before
loading full SKILL.md instructions:

```markdown
## Available Skills

### build
Use when: Build the project from source.

### test
Use when: Run the test suite.
```

**Why this matters.** In skill-heavy repos, agents often miss the right skill,
reimplement existing workflows, or load large skill docs before knowing which
skill applies. The index creates a "decision surface" — agents read a small
file, pick the relevant skill(s), and only then open the full SKILL.md.

The index is a generated output — it lives alongside vendor configs, not in
the `.agents/` SSOT. It regenerates on every `<cli> agents generate` run from
each skill's `description` frontmatter field. To improve routing, make those
descriptions more specific.

For best results, pair the index with a mandatory skill usage policy (see
[Recommended Workflow](#recommended-workflow) below).

### `rules/<name>.md`

Rules are path-scoped instructions. Each rule file has a `paths:` YAML
frontmatter list that specifies which files/directories the rule applies to.

**Example** (`rules/tests.md`):

```markdown
---
paths:
  - "tests/**/*"
  - "test/**/*"
---

Use descriptive test names. Prefer `pytest.raises` over try/except in tests.
```

During generation, the `paths:` frontmatter is converted to each agent's
native format:

| Agent   | Conversion                              |
|---------|-----------------------------------------|
| Claude  | `.claude/rules/<name>.md` with `paths:` frontmatter (native format) |
| Copilot | `.github/instructions/<name>.instructions.md` with `applyTo:` frontmatter |
| Cursor  | Appended to `.cursorrules` (Cursor has no per-path rules) |
| Codex   | Included in `AGENTS.md` body            |

### `agents-reference.md` (optional Codex override)

When present, `agents-reference.md` replaces `project.md` as the source for
the generated `AGENTS.md` file. Use this when you want Codex to see different
or more detailed instructions than other agents.

## CLI Reference

### `<cli> agents init`

Scaffold the `.agents/` source-of-truth directory.

```bash
<cli> agents init [--force]
```

- Auto-detects project language, build system, and test framework
- Reads `[commands]` from `.dekk.toml` and converts them to skill templates
- Auto-scaffolds a `worktree` skill for git repos (teaches agents about
  `dekk worktree` commands)
- Creates `project.md`, `skills/`, and `rules/` directories
- If `.dekk.toml` is missing, auto-creates one from `pyproject.toml`,
  `package.json`, `Cargo.toml`, `environment.yaml`, or the repo name
- `--force` overwrites existing `project.md`

### `<cli> agents generate`

Generate agent config files from the source-of-truth directory.

```bash
<cli> agents generate [--target TARGET]
```

- `--target`: `claude`, `codex`, `copilot`, `cursor`, or `all` (default: `all`)
- Generates the skills index (`skills/skills_index.md`) from discovered skills
- Respects `[agents].targets` filtering from `.dekk.toml`

### `<cli> agents clean`

Remove generated agent config files while keeping `.agents/`.

```bash
<cli> agents clean [--target TARGET]
```

- `--target`: `claude`, `codex`, `copilot`, `cursor`, or `all` (default: `all`)
- Cleans generated files and directories (e.g., `.claude/skills/`, `.claude/rules/`)

### `<cli> agents install`

Install skills into `~/.codex/skills/` for the Codex agent.

```bash
<cli> agents install [--codex-dir DIR] [--force/--no-force]
```

- Copies skill files with simplified frontmatter (name + description only)
- `--codex-dir` overrides the default `$CODEX_HOME/skills` or `~/.codex/skills`

### `<cli> agents status`

Show agent config and skill installation status.

```bash
<cli> agents status [--codex-dir DIR]
```

Example output:

```
Source of truth: .agents/
  project.md: present
  skills/: 3 skill(s)

Agent config files:
  CLAUDE.md: present
  AGENTS.md: present
  .cursorrules: present
  .github/copilot-instructions.md: present
  .agents.json: present

Skills:
  build  claude=ok  codex=ok
  test   claude=ok  codex=stale
  lint   claude=ok  codex=missing
```

### `<cli> agents list`

List available skills from the source-of-truth directory.

```bash
<cli> agents list
```

Example output:

```
Source: /path/to/project/.agents

build
  Build the project from source
test
  Run the test suite
lint
  Run linter checks
```

## Generated Outputs

Each target receives different files, all derived from the same `.agents/`
source.

### Claude Code

| Output | Source |
|--------|--------|
| `CLAUDE.md` | `project.md` content |
| `.claude/skills/<name>/SKILL.md` | Synced 1:1 from `.agents/skills/` |
| `.claude/skills/skills_index.md` | Generated routing index from skill descriptions |
| `.claude/rules/<name>.md` | Rules with `paths:` YAML frontmatter |

### Codex

| Output | Source |
|--------|--------|
| `AGENTS.md` | `agents-reference.md` if present, otherwise `project.md` |

Skills are installed separately via `<cli> agents install` into `~/.codex/skills/`.
Codex skills use simplified frontmatter (only `name` and `description`, no
`user-invocable`).

### Cursor

| Output | Source |
|--------|--------|
| `.cursorrules` | `project.md` content |

### Copilot

| Output | Source |
|--------|--------|
| `.github/copilot-instructions.md` | `project.md` content |
| `.github/instructions/<name>.instructions.md` | Rules with `applyTo:` frontmatter |

### Manifest

| Output | Source |
|--------|--------|
| `.agents.json` | Machine-readable JSON with project name, skill list, target paths |

Example `.agents.json`:

```json
{
  "project": "my-project",
  "source_of_truth": ".agents/",
  "agent_configs": {
    "claude": { "instructions": "CLAUDE.md", "skills": ".claude/skills/" },
    "codex": { "instructions": "AGENTS.md", "skills": "~/.codex/skills/" },
    "copilot": { "instructions": ".github/copilot-instructions.md" },
    "cursor": { "instructions": ".cursorrules" }
  },
  "skills": [
    { "name": "build", "description": "Build the project" },
    { "name": "test", "description": "Run the test suite" }
  ]
}
```

## `.dekk.toml` Configuration

### `[commands]` — auto-converted to skills

Commands defined here become skill templates when `<cli> agents init` scaffolds
the `.agents/` directory.

```toml
[commands]
build = { run = "make", description = "Build from source" }
test  = { run = "pytest -q", description = "Run test suite" }
lint  = { run = "ruff check .", description = "Run linter" }
```

Shorthand (run-only, no description):

```toml
[commands]
clean = "rm -rf build"
```

### `[agents]` — source directory and target filtering

```toml
[agents]
source = ".agents"                              # default
targets = ["claude", "codex", "copilot", "cursor"]  # default: all four
```

- `source` — the SSOT directory name (override for dekk-based CLIs like CARTS
  that use `.carts/` instead of `.agents/`)
- `targets` — when set, `<cli> agents generate --target all` only generates for
  the listed targets

## Recommended Workflow

1. **`<cli> agents init`** — scaffold `.agents/` from project detection.
2. **Edit `.dekk.toml`** — refine `[commands]` or `[agents]` if needed.
3. **Edit `.agents/project.md`** — add project-specific guidance.
4. **Edit `skills/*/SKILL.md`** — customize generated skill templates.
5. **Add rules** — create `rules/<name>.md` with `paths:` frontmatter for
   path-scoped instructions.
6. **`<cli> agents generate --target all`** — produce all agent configs.
7. **Commit** both `.agents/` and the generated target files.

### Skill Routing Policy (recommended for skill-heavy repos)

For repos with many skills, add a mandatory rule that instructs agents to
consult the skills index before executing work. Create a rule file in each
agent's always-on rules location (e.g., `.claude/rules/skill-routing.md`):

```markdown
---
paths:
  - "**/*"
---

## Mandatory Skill Usage Policy

This repo defines reusable AI skills in `.agents/skills/`.

### Hard Rules
- Agents MUST consult `skills/skills_index.md` before executing substantive work.
- If one or more relevant skills exist, agents MUST use them.
- Reimplementing an existing skill's workflow is considered a defect.

### Execution Flow
1. Read `skills/skills_index.md`
2. Select applicable skill(s)
3. Open the selected `SKILL.md` file(s)
4. Execute using the skill instructions
5. If no skill applies, state why in 1-2 sentences
```

Tips for the skills index:

- Keep "Use when:" lines **specific and mutually exclusive**
- If agents still pick the wrong skill, rewrite the `description` field in
  each SKILL.md frontmatter to be more precise
- Treat `skills_index.md` as a generated file — it regenerates on each
  `<cli> agents generate` run from skill descriptions

## Agent Abstraction

Generation targets implement a `DekkAgent` contract. The built-in targets are
Claude Code, Codex, Cursor, and Copilot. `AgentConfigManager` can accept
custom agents for additional targets:

```python
from dekk.agents import AgentConfigManager, DekkAgent, AgentContext

class MyAgent(DekkAgent):
    target = "my-target"

    def generate(self, context: AgentContext) -> list[str]:
        output = context.project_root / "MY_AGENT.md"
        output.write_text(context.project_content, encoding="utf-8")
        return ["MY_AGENT.md"]

manager = AgentConfigManager(project_root, agents=(MyAgent(),))
manager.generate("my-target")
```

Built-in provider modules live under `src/dekk/agents/providers/`.

## Notes

- `AGENTS.md` is the Codex-facing generated file in the project root.
- `<cli> agents install` is only for Codex skill installation into the local
  Codex home; it does not replace generated project files.
- The feature is project-root aware and walks upward to find either `.agents/`
  or `.dekk.toml`, so it works correctly from nested directories inside a repo.
