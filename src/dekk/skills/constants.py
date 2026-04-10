"""Constants for the skills module.

All filenames, directory names, environment variable names, and agent target
identifiers used throughout ``dekk.skills`` are defined here.  No other
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

# Built-in skill names for auto-discovery
WORKTREE_SKILL_NAME: Final = "worktree"

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
# Enriched generation — Claude Code
# ---------------------------------------------------------------------------

CLAUDE_PLUGIN_MANIFEST_DIR: Final = ".claude-plugin"
CLAUDE_PLUGIN_MANIFEST: Final = "plugin.json"
CLAUDE_MCP_JSON: Final = ".mcp.json"
CLAUDE_HOOKS_DIR: Final = "hooks"
CLAUDE_HOOKS_JSON: Final = "hooks.json"
CLAUDE_MCP_DIR: Final = "mcp"
CLAUDE_SETTINGS_DIR: Final = ".claude"
CLAUDE_SETTINGS_JSON: Final = "settings.json"

# ---------------------------------------------------------------------------
# Enriched generation — Cursor
# ---------------------------------------------------------------------------

CURSOR_DIR: Final = ".cursor"
CURSOR_MCP_JSON: Final = "mcp.json"

# ---------------------------------------------------------------------------
# Enriched generation — Codex
# ---------------------------------------------------------------------------

CODEX_AGENTS_DIR: Final = "agents"
CODEX_AGENT_YAML: Final = "openai.yaml"

# ---------------------------------------------------------------------------
# Enriched generation — Copilot
# ---------------------------------------------------------------------------

COPILOT_EXTENSIONS_DIR: Final = "extensions"

# ---------------------------------------------------------------------------
# Enriched generation — shared MCP
# ---------------------------------------------------------------------------

MCP_REQUIREMENTS: Final = "requirements.txt"
MCP_SERVER_SUFFIX: Final = "_server.py"
MCP_COMMAND: Final = "python3"

# ---------------------------------------------------------------------------
# MCP / plugin JSON schema keys (platform-defined, shared across providers)
# ---------------------------------------------------------------------------

MCP_KEY_SERVERS: Final = "mcpServers"
MCP_KEY_COMMAND: Final = "command"
MCP_KEY_ARGS: Final = "args"

PLUGIN_KEY_NAME: Final = "name"
PLUGIN_KEY_DESCRIPTION: Final = "description"
PLUGIN_KEY_VERSION: Final = "version"
PLUGIN_KEY_USER_CONFIG: Final = "userConfig"
PLUGIN_KEY_DEFAULT: Final = "default"
PLUGIN_KEY_MCP: Final = "mcp"
PLUGIN_KEY_TOOLS: Final = "tools"
PLUGIN_KEY_SERVER: Final = "server"

SETTINGS_KEY_PLUGINS: Final = "plugins"
SETTINGS_KEY_MCP_SERVERS: Final = "mcpServers"
SETTINGS_KEY_HOOKS: Final = "hooks"

HOOKS_KEY_HOOKS: Final = "hooks"
HOOKS_KEY_EVENT: Final = "event"
HOOKS_KEY_COMMAND: Final = "command"
HOOKS_KEY_DESCRIPTION: Final = "description"
HOOKS_KEY_MATCHER: Final = "matcher"
HOOKS_KEY_TYPE: Final = "type"
HOOKS_KEY_TYPE_COMMAND: Final = "command"
HOOKS_KEY_TOOL_NAME: Final = "tool_name"
HOOKS_KEY_FILE_PATTERN: Final = "file_pattern"
HOOKS_KEY_COMMAND_PATTERN: Final = "command_pattern"

# ---------------------------------------------------------------------------
# Skills index (routing layer)
# ---------------------------------------------------------------------------

SKILLS_INDEX_MD: Final = "skills_index.md"

# ---------------------------------------------------------------------------
# TOML keys for project name lookup
# ---------------------------------------------------------------------------

TOML_PROJECT_KEY: Final = "project"
TOML_NAME_KEY: Final = "name"
TOML_COMMANDS_KEY: Final = "commands"
TOML_RUN_KEY: Final = "run"
TOML_DESCRIPTION_KEY: Final = "description"
TOML_SKILL_KEY: Final = "skill"
TOML_GROUP_KEY: Final = "group"

# ---------------------------------------------------------------------------
# Default CLI name (for standalone dekk usage)
# ---------------------------------------------------------------------------

DEFAULT_CLI_NAME: Final = "dekk"
