"""Per-target agent configuration generators.

Reads a source-of-truth directory (``.agents/`` or ``.carts/``) and produces
agent-specific config files for Claude Code, Codex, Cursor, Copilot, and
a machine-readable ``.agents.json`` manifest.

Extracted from ``carts/tools/scripts/agents.py`` into a generic library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dekk.agents.constants import (
    AGENTS_JSON,
    AGENTS_MD,
    CLAUDE_MD,
    CLAUDE_SKILLS_DIR,
    COPILOT_DIR,
    COPILOT_INSTRUCTIONS,
    COPILOT_PER_DIR,
    CURSORRULES,
    DEFAULT_SOURCE_DIR,
    PROJECT_MD,
    TARGET_ALL,
    TARGET_CLAUDE,
    TARGET_CODEX,
    TARGET_COPILOT,
    TARGET_CURSOR,
)
from dekk.agents.discovery import SkillDefinition, discover_rules, discover_skills
from dekk.agents.providers import (
    AgentContext,
    ClaudeCodeAgent,
    CodexAgent,
    CopilotAgent,
    CursorAgent,
    DekkAgent,
    default_agents,
    render_codex_skill,
)
from dekk.agents.providers.shared import remove_file


@dataclass
class GenerateResult:
    """Summary of what was generated."""

    generated: list[str] = field(default_factory=list)
    skill_count: int = 0
    rule_count: int = 0


@dataclass
class CleanResult:
    """Summary of what was removed."""

    removed: list[str] = field(default_factory=list)


def _generate_agents_json(
    project_root: Path,
    skills: list[SkillDefinition],
    project_name: str,
    source_dir_name: str,
    cli_name: str | None = None,
) -> None:
    """Generate ``.agents.json`` machine-readable manifest."""
    manifest: dict[str, Any] = {
        "project": project_name,
        "source_of_truth": f"{source_dir_name}/",
        "agent_configs": {
            TARGET_CLAUDE: {
                "instructions": CLAUDE_MD,
                "skills": f"{CLAUDE_SKILLS_DIR}/",
            },
            TARGET_CODEX: {
                "instructions": AGENTS_MD,
                "skills": "~/.codex/skills/",
            },
            TARGET_COPILOT: {
                "instructions": f"{COPILOT_DIR}/{COPILOT_INSTRUCTIONS}",
                "per_directory": f"{COPILOT_DIR}/{COPILOT_PER_DIR}/",
            },
            TARGET_CURSOR: {
                "instructions": CURSORRULES,
            },
        },
        "skills": [{"name": s.name, "description": s.description} for s in skills],
    }
    if cli_name:
        manifest["cli"] = cli_name

    agents_json = project_root / AGENTS_JSON
    agents_json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


class AgentConfigManager:
    """Orchestrates agent config generation from a source-of-truth directory.

    Args:
        project_root: Root directory of the project.
        source_dir: Name of the source-of-truth directory (default: ".agents").
        project_name: Project name for manifests (auto-detected from source_dir or dir name).
        cli_name: Optional CLI command name (e.g., "carts") for manifest.
    """

    def __init__(
        self,
        project_root: Path,
        source_dir: str = DEFAULT_SOURCE_DIR,
        project_name: str | None = None,
        cli_name: str | None = None,
        agents: tuple[DekkAgent, ...] | None = None,
    ) -> None:
        self.project_root = project_root
        self.source_dir_name = source_dir
        self.source_dir = project_root / source_dir
        self.cli_name = cli_name
        self.project_name = project_name or project_root.name
        self._abstractions = {
            agent.target: agent
            for agent in (agents or default_agents())
        }

    def _read_project_md(self) -> str | None:
        """Read project.md from the source directory."""
        project_md = self.source_dir / PROJECT_MD
        if not project_md.is_file():
            return None
        return project_md.read_text(encoding="utf-8")

    def generate(self, target: str = TARGET_ALL) -> GenerateResult:
        """Generate agent configs for the specified target(s).

        Args:
            target: One of "claude", "codex", "cursor", "copilot", "all".

        Returns:
            GenerateResult with list of generated files.
        """
        effective_target = target.lower()
        result = GenerateResult()

        skills = discover_skills(self.source_dir)
        result.skill_count = len(skills)

        project_content = self._read_project_md()
        if not project_content:
            msg = f"{self.source_dir_name}/{PROJECT_MD} not found"
            raise FileNotFoundError(msg)

        rules = discover_rules(self.source_dir)
        result.rule_count = len(rules)

        context = AgentContext(
            project_root=self.project_root,
            source_dir=self.source_dir,
            source_dir_name=self.source_dir_name,
            project_name=self.project_name,
            cli_name=self.cli_name,
            project_content=project_content,
            skills=skills,
            rules=rules,
        )

        if effective_target == TARGET_ALL:
            for target_name in (TARGET_CLAUDE, TARGET_CODEX, TARGET_CURSOR, TARGET_COPILOT):
                result.generated.extend(self._abstractions[target_name].generate(context))
        elif effective_target in self._abstractions:
            result.generated.extend(self._abstractions[effective_target].generate(context))

        if effective_target == TARGET_ALL:
            self._generate_manifest(skills)
            result.generated.append(AGENTS_JSON)

        return result

    def clean(self, target: str = TARGET_ALL) -> CleanResult:
        """Remove generated files for the specified target(s)."""
        effective_target = target.lower()
        context = AgentContext(
            project_root=self.project_root,
            source_dir=self.source_dir,
            source_dir_name=self.source_dir_name,
            project_name=self.project_name,
            cli_name=self.cli_name,
            project_content="",
            skills=[],
            rules=[],
        )
        result = CleanResult()

        if effective_target == TARGET_ALL:
            for target_name in (TARGET_CLAUDE, TARGET_CODEX, TARGET_CURSOR, TARGET_COPILOT):
                result.removed.extend(self._abstractions[target_name].clean(context))
            result.removed.extend(remove_file(self.project_root / AGENTS_JSON, AGENTS_JSON))
        elif effective_target in self._abstractions:
            result.removed.extend(self._abstractions[effective_target].clean(context))

        return result

    def _generate_manifest(self, skills: list[SkillDefinition]) -> None:
        """Generate .agents.json machine-readable manifest."""
        _generate_agents_json(
            self.project_root,
            skills,
            self.project_name,
            self.source_dir_name,
            self.cli_name,
        )


__all__ = [
    "AgentConfigManager",
    "AgentContext",
    "CleanResult",
    "ClaudeCodeAgent",
    "CodexAgent",
    "CopilotAgent",
    "CursorAgent",
    "DekkAgent",
    "GenerateResult",
    "default_agents",
    "render_codex_skill",
]
