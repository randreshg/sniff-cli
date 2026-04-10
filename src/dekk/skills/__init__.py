"""Agent configuration management for dekk.

Single source of truth: ``.agents/`` (or custom) directory.
Generates configs for Claude Code, Codex, Cursor, Copilot, and machine-readable manifests.

Usage::

    from dekk.skills import create_agents_app, AgentConfigManager
    from dekk.skills.discovery import discover_skills, discover_rules

    # In a dekk-based CLI:
    agents_app = create_agents_app(source_dir=".carts", parent_app=app)
    app.add_typer(agents_app, name="agents")

    # Programmatic generation:
    manager = AgentConfigManager(project_root=Path.cwd())
    manager.generate()
"""

from __future__ import annotations

from dekk.skills.app import create_agents_app
from dekk.skills.discovery import (
    RuleDefinition,
    SkillDefinition,
    discover_rules,
    discover_skills,
    parse_frontmatter,
)
from dekk.skills.generators import (
    AgentConfigManager,
    ClaudeCodeAgent,
    CodexAgent,
    CopilotAgent,
    CursorAgent,
)
from dekk.skills.providers import DekkAgent
from dekk.skills.scaffold import scaffold_agents_dir

__all__ = [
    "AgentConfigManager",
    "ClaudeCodeAgent",
    "CodexAgent",
    "CopilotAgent",
    "CursorAgent",
    "DekkAgent",
    "RuleDefinition",
    "SkillDefinition",
    "create_agents_app",
    "discover_rules",
    "discover_skills",
    "parse_frontmatter",
    "scaffold_agents_dir",
]
