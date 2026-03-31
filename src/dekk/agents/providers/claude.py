"""Claude Code provider implementation."""

from __future__ import annotations

from pathlib import Path

from dekk.agents.constants import (
    CLAUDE_MD,
    CLAUDE_RULES_DIR,
    CLAUDE_SKILLS_DIR,
    TARGET_CLAUDE,
)
from dekk.agents.discovery import RuleDefinition
from dekk.agents.providers.base import AgentContext, DekkAgent
from dekk.agents.providers.shared import (
    install_skills_to_dir,
    remove_dir_if_empty,
    remove_file,
    remove_tree,
)


def generate_claude_rules(project_root: Path, rules: list[RuleDefinition]) -> None:
    """Generate `.claude/rules/` from rules with Claude `paths:` frontmatter."""
    rules_dir = project_root / CLAUDE_RULES_DIR
    rules_dir.mkdir(parents=True, exist_ok=True)
    for rule in rules:
        paths_yaml = "\n".join(f'  - "{p}"' for p in rule.paths)
        content = f"---\npaths:\n{paths_yaml}\n---\n{rule.body}"
        (rules_dir / f"{rule.name}.md").write_text(content, encoding="utf-8")


class ClaudeCodeAgent(DekkAgent):
    """Claude Code target generation."""

    target = TARGET_CLAUDE

    def generate(self, context: AgentContext) -> list[str]:
        claude_md = context.project_root / CLAUDE_MD
        claude_md.write_text(context.project_content, encoding="utf-8")

        claude_skills = context.project_root / CLAUDE_SKILLS_DIR
        install_skills_to_dir(context.skills, claude_skills)
        generate_claude_rules(context.project_root, context.rules)

        return [
            CLAUDE_MD,
            f"{CLAUDE_SKILLS_DIR}/ ({len(context.skills)} skills)",
            f"{CLAUDE_RULES_DIR}/ ({len(context.rules)} rules)",
        ]

    def clean(self, context: AgentContext) -> list[str]:
        removed: list[str] = []
        removed.extend(remove_file(context.project_root / CLAUDE_MD, CLAUDE_MD))
        removed.extend(remove_tree(context.project_root / CLAUDE_SKILLS_DIR, f"{CLAUDE_SKILLS_DIR}/"))
        removed.extend(remove_tree(context.project_root / CLAUDE_RULES_DIR, f"{CLAUDE_RULES_DIR}/"))
        remove_dir_if_empty(context.project_root / Path(CLAUDE_SKILLS_DIR).parts[0])
        return removed


__all__ = ["ClaudeCodeAgent", "generate_claude_rules"]
