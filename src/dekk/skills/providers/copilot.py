"""GitHub Copilot provider implementation."""

from __future__ import annotations

import json
from pathlib import Path

from dekk.skills.constants import (
    CLAUDE_MCP_DIR,
    COPILOT_DIR,
    COPILOT_EXTENSIONS_DIR,
    COPILOT_INSTRUCTIONS,
    COPILOT_PER_DIR,
    COPILOT_RULE_SUFFIX,
    MCP_COMMAND,
    MCP_KEY_ARGS,
    MCP_KEY_COMMAND,
    MCP_SERVER_SUFFIX,
    PLUGIN_KEY_DESCRIPTION,
    PLUGIN_KEY_MCP,
    PLUGIN_KEY_NAME,
    PLUGIN_KEY_TOOLS,
    PLUGIN_KEY_VERSION,
    TARGET_COPILOT,
)
from dekk.skills.discovery import RuleDefinition
from dekk.skills.providers.base import AgentContext, DekkAgent
from dekk.skills.providers.shared import remove_dir_if_empty, remove_file, remove_tree


def generate_copilot_per_directory(project_root: Path, rules: list[RuleDefinition]) -> None:
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
        results = [
            f"{COPILOT_DIR}/{COPILOT_INSTRUCTIONS}",
            f"{COPILOT_DIR}/{COPILOT_PER_DIR}/ ({len(context.rules)} rules)",
        ]

        if context.enrichment and context.enrichment.mcp_tools:
            results.extend(self._generate_extension(context))

        return results

    def _generate_extension(self, context: AgentContext) -> list[str]:
        """Generate ``.github/extensions/`` MCP server reference."""
        enrichment = context.enrichment
        assert enrichment is not None

        ext_dir = context.project_root / COPILOT_DIR / COPILOT_EXTENSIONS_DIR
        ext_dir.mkdir(parents=True, exist_ok=True)

        server_script = (
            f"{context.source_dir_name}/{CLAUDE_MCP_DIR}/"
            f"{enrichment.project_name}{MCP_SERVER_SUFFIX}"
        )
        extension_manifest = {
            PLUGIN_KEY_NAME: enrichment.project_name,
            PLUGIN_KEY_DESCRIPTION: (
                enrichment.project_description or f"{enrichment.project_name} tools"
            ),
            PLUGIN_KEY_VERSION: enrichment.version,
            PLUGIN_KEY_MCP: {
                MCP_KEY_COMMAND: MCP_COMMAND,
                MCP_KEY_ARGS: [server_script],
            },
            PLUGIN_KEY_TOOLS: [
                {
                    PLUGIN_KEY_NAME: t.name,
                    PLUGIN_KEY_DESCRIPTION: t.description,
                }
                for t in enrichment.mcp_tools
            ],
        }

        manifest_path = ext_dir / f"{enrichment.project_name}.json"
        manifest_path.write_text(
            json.dumps(extension_manifest, indent=2) + "\n", encoding="utf-8"
        )
        return [f"{COPILOT_DIR}/{COPILOT_EXTENSIONS_DIR}/{enrichment.project_name}.json"]

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
        # Remove only our project's extension file, not the whole extensions/ dir.
        ext_file = f"{context.project_name}.json"
        ext_label = f"{COPILOT_DIR}/{COPILOT_EXTENSIONS_DIR}/{ext_file}"
        removed.extend(
            remove_file(
                context.project_root / COPILOT_DIR / COPILOT_EXTENSIONS_DIR / ext_file,
                ext_label,
            )
        )
        remove_dir_if_empty(
            context.project_root / COPILOT_DIR / COPILOT_EXTENSIONS_DIR
        )
        remove_dir_if_empty(context.project_root / COPILOT_DIR)
        return removed


__all__ = ["CopilotAgent", "generate_copilot_per_directory"]
