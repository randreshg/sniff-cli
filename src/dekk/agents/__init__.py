"""Agent configuration management for dekk.

Single source of truth: ``.agents/`` (or custom) directory.
Generates configs for Claude Code, Codex, Cursor, Copilot, and machine-readable manifests.

Usage::

    from dekk.agents import create_agents_app, AgentConfigManager
    from dekk.agents.discovery import discover_skills, discover_rules

    # In a dekk-based CLI:
    agents_app = create_agents_app(source_dir=".carts", parent_app=app)
    app.add_typer(agents_app, name="agents")

    # Programmatic generation:
    manager = AgentConfigManager(project_root=Path.cwd())
    manager.generate()
"""

from __future__ import annotations

from dekk.agents.app import create_agents_app
from dekk.agents.discovery import (
    RuleDefinition,
    SkillDefinition,
    discover_rules,
    discover_skills,
    parse_frontmatter,
)
from dekk.agents.generators import AgentConfigManager
from dekk.agents.installer import install_codex_skills
from dekk.agents.scaffold import scaffold_agents_dir

__all__ = [
    "AgentConfigManager",
    "RuleDefinition",
    "SkillDefinition",
    "create_agents_app",
    "discover_rules",
    "discover_skills",
    "install_codex_skills",
    "parse_frontmatter",
    "scaffold_agents_dir",
]
