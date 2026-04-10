"""Shared abstractions for agent-specific generation targets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from dekk.skills.discovery import RuleDefinition, SkillDefinition

if TYPE_CHECKING:
    from dekk.environment.spec import SkillsSpec
    from dekk.skills.providers.enrichment import EnrichmentData


@dataclass(frozen=True)
class AgentContext:
    """Shared generation context for a concrete agent target."""

    project_root: Path
    source_dir: Path
    source_dir_name: str
    project_name: str
    cli_name: str | None
    project_content: str
    skills: list[SkillDefinition]
    rules: list[RuleDefinition]
    project_description: str = ""
    enrichment: EnrichmentData | None = None
    skills_spec: SkillsSpec | None = None


class DekkAgent(ABC):
    """Contract implemented by each agent-specific target generator."""

    target: str

    @abstractmethod
    def generate(self, context: AgentContext) -> list[str]:
        """Generate target-specific files and return user-facing output labels."""

    def clean(self, context: AgentContext) -> list[str]:
        """Remove target-specific generated files and return removed labels."""
        return []


__all__ = ["AgentContext", "DekkAgent"]
