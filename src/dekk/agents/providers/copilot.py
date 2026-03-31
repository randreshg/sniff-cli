"""GitHub Copilot provider implementation."""

from __future__ import annotations

from dekk.agents.constants import (
    COPILOT_DIR,
    COPILOT_INSTRUCTIONS,
    COPILOT_PER_DIR,
    COPILOT_RULE_SUFFIX,
    TARGET_COPILOT,
)
from dekk.agents.discovery import RuleDefinition
from dekk.agents.providers.base import AgentContext, DekkAgent
from dekk.agents.providers.shared import remove_dir_if_empty, remove_file, remove_tree


def generate_copilot_per_directory(project_root, rules: list[RuleDefinition]) -> None:
    """Generate `.github/instructions/` from rules with Copilot `applyTo:` frontmatter."""
    instr_dir = project_root / COPILOT_DIR / COPILOT_PER_DIR
    instr_dir.mkdir(parents=True, exist_ok=True)
    for rule in rules:
        apply_to = ",".join(rule.paths)
        content = f"---\napplyTo: {apply_to}\n---\n{rule.body}"
        (instr_dir / f"{rule.name}{COPILOT_RULE_SUFFIX}").write_text(content, encoding="utf-8")


class CopilotAgent(DekkAgent):
    """GitHub Copilot target generation."""

    target = TARGET_COPILOT

    def generate(self, context: AgentContext) -> list[str]:
        copilot_dir = context.project_root / COPILOT_DIR
        copilot_dir.mkdir(parents=True, exist_ok=True)
        copilot_path = copilot_dir / COPILOT_INSTRUCTIONS
        copilot_path.write_text(context.project_content, encoding="utf-8")
        generate_copilot_per_directory(context.project_root, context.rules)
        return [
            f"{COPILOT_DIR}/{COPILOT_INSTRUCTIONS}",
            f"{COPILOT_DIR}/{COPILOT_PER_DIR}/ ({len(context.rules)} rules)",
        ]

    def clean(self, context: AgentContext) -> list[str]:
        removed: list[str] = []
        removed.extend(
            remove_file(
                context.project_root / COPILOT_DIR / COPILOT_INSTRUCTIONS,
                f"{COPILOT_DIR}/{COPILOT_INSTRUCTIONS}",
            )
        )
        removed.extend(
            remove_tree(
                context.project_root / COPILOT_DIR / COPILOT_PER_DIR,
                f"{COPILOT_DIR}/{COPILOT_PER_DIR}/",
            )
        )
        remove_dir_if_empty(context.project_root / COPILOT_DIR)
        return removed


__all__ = ["CopilotAgent", "generate_copilot_per_directory"]
