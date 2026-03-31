"""Constants for the agents module.

All filenames, directory names, environment variable names, and agent target
identifiers used throughout ``dekk.agents`` are defined here.  No other
module in this package should contain hardcoded path fragments or config keys.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Source-of-truth directory layout
# ---------------------------------------------------------------------------

DEFAULT_SOURCE_DIR: Final = ".agents"
SKILLS_DIR_NAME: Final = "skills"
RULES_DIR_NAME: Final = "rules"
SKILL_FILENAME: Final = "SKILL.md"
PROJECT_MD: Final = "project.md"
AGENTS_REFERENCE_MD: Final = "agents-reference.md"
RULES_GLOB: Final = "*.md"

# Frontmatter required fields
REQUIRED_SKILL_FIELDS: Final = ("name", "description")

# ---------------------------------------------------------------------------
# Project detection markers
# ---------------------------------------------------------------------------

DEKK_TOML: Final = ".dekk.toml"

# ---------------------------------------------------------------------------
# Agent target names
# ---------------------------------------------------------------------------

TARGET_ALL: Final = "all"
TARGET_CLAUDE: Final = "claude"
TARGET_CODEX: Final = "codex"
TARGET_CURSOR: Final = "cursor"
TARGET_COPILOT: Final = "copilot"

ALL_TARGETS: Final = (TARGET_CLAUDE, TARGET_CODEX, TARGET_CURSOR, TARGET_COPILOT)

# ---------------------------------------------------------------------------
# Generated output filenames / paths
# ---------------------------------------------------------------------------

# Claude Code
CLAUDE_MD: Final = "CLAUDE.md"
CLAUDE_SKILLS_DIR: Final = ".claude/skills"
CLAUDE_RULES_DIR: Final = ".claude/rules"

# Codex / AGENTS.md
AGENTS_MD: Final = "AGENTS.md"

# Cursor
CURSORRULES: Final = ".cursorrules"

# Copilot
COPILOT_DIR: Final = ".github"
COPILOT_INSTRUCTIONS: Final = "copilot-instructions.md"
COPILOT_PER_DIR: Final = "instructions"
COPILOT_RULE_SUFFIX: Final = ".instructions.md"

# Machine-readable manifest
AGENTS_JSON: Final = ".agents.json"

# ---------------------------------------------------------------------------
# Codex environment
# ---------------------------------------------------------------------------

CODEX_HOME_ENV: Final = "CODEX_HOME"
CODEX_HOME_DEFAULT: Final = ".codex"
CODEX_SKILLS_DIR_NAME: Final = "skills"

# ---------------------------------------------------------------------------
# Flow generation
# ---------------------------------------------------------------------------

DEFAULT_FLOWS_DIR: Final = "flows"

# TOML keys for project name lookup
TOML_PROJECT_KEY: Final = "project"
TOML_NAME_KEY: Final = "name"
TOML_COMMANDS_KEY: Final = "commands"
TOML_RUN_KEY: Final = "run"
TOML_DESCRIPTION_KEY: Final = "description"

# ---------------------------------------------------------------------------
# Default CLI name (for standalone dekk usage)
# ---------------------------------------------------------------------------

DEFAULT_CLI_NAME: Final = "dekk"
