"""Codex provider implementation."""

from __future__ import annotations

from dekk.agents.constants import AGENTS_MD, AGENTS_REFERENCE_MD, TARGET_CODEX
from dekk.agents.discovery import SkillDefinition
from dekk.agents.providers.base import AgentContext, DekkAgent
from dekk.agents.providers.shared import remove_file


def render_codex_skill(skill: SkillDefinition) -> str:
    """Render a skill in Codex format with minimal frontmatter."""
    return (
        "---\n"
        f"name: {skill.name}\n"
        f"description: {skill.description}\n"
        "---\n\n"
        f"{skill.body.lstrip()}"
    )


class CodexAgent(DekkAgent):
    """Codex target generation."""

    target = TARGET_CODEX

    def generate(self, context: AgentContext) -> list[str]:
        agents_ref = context.source_dir / AGENTS_REFERENCE_MD
        content = (
            agents_ref.read_text(encoding="utf-8")
            if agents_ref.is_file()
            else context.project_content
        )
        agents_md = context.project_root / AGENTS_MD
        agents_md.write_text(content, encoding="utf-8")
        return [AGENTS_MD]

    def clean(self, context: AgentContext) -> list[str]:
        return remove_file(context.project_root / AGENTS_MD, AGENTS_MD)


__all__ = ["CodexAgent", "render_codex_skill"]
