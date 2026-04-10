"""Claude Code provider implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dekk.skills.constants import (
    CLAUDE_HOOKS_DIR,
    CLAUDE_HOOKS_JSON,
    CLAUDE_MCP_DIR,
    CLAUDE_MCP_JSON,
    CLAUDE_MD,
    CLAUDE_PLUGIN_MANIFEST,
    CLAUDE_PLUGIN_MANIFEST_DIR,
    CLAUDE_RULES_DIR,
    CLAUDE_SETTINGS_DIR,
    CLAUDE_SETTINGS_JSON,
    CLAUDE_SKILLS_DIR,
    HOOKS_KEY_COMMAND,
    HOOKS_KEY_DESCRIPTION,
    HOOKS_KEY_EVENT,
    HOOKS_KEY_HOOKS,
    HOOKS_KEY_MATCHER,
    MCP_COMMAND,
    MCP_KEY_ARGS,
    MCP_KEY_COMMAND,
    MCP_KEY_SERVERS,
    MCP_REQUIREMENTS,
    MCP_SERVER_SUFFIX,
    PLUGIN_KEY_DEFAULT,
    PLUGIN_KEY_DESCRIPTION,
    PLUGIN_KEY_NAME,
    PLUGIN_KEY_USER_CONFIG,
    PLUGIN_KEY_VERSION,
    SETTINGS_KEY_HOOKS,
    SETTINGS_KEY_MCP_SERVERS,
    SETTINGS_KEY_PLUGINS,
    SKILLS_INDEX_MD,
    TARGET_CLAUDE,
)
from dekk.skills.discovery import RuleDefinition
from dekk.skills.providers.base import AgentContext, DekkAgent
from dekk.skills.providers.shared import (
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

        # Generate skills index directly in the output directory.
        if context.skills:
            from dekk.skills.generators import render_skills_index

            (claude_skills / SKILLS_INDEX_MD).write_text(
                render_skills_index(context.skills), encoding="utf-8"
            )

        results = [
            CLAUDE_MD,
            f"{CLAUDE_SKILLS_DIR}/ ({len(context.skills)} skills)",
            f"{CLAUDE_RULES_DIR}/ ({len(context.rules)} rules)",
        ]

        if context.enrichment:
            results.extend(self._generate_enriched(context))

        return results

    # -----------------------------------------------------------------
    # Enriched generation
    # -----------------------------------------------------------------

    def _generate_enriched(self, context: AgentContext) -> list[str]:
        """Generate plugin.json, .mcp.json, hooks, MCP server, and settings."""
        from dekk.skills.providers.enrichment import (
            generate_mcp_requirements,
            generate_mcp_server_stub,
        )

        enrichment = context.enrichment
        assert enrichment is not None
        source = context.source_dir
        results: list[str] = []

        # 1. plugin.json
        plugin_dir = source / CLAUDE_PLUGIN_MANIFEST_DIR
        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, object] = {
            PLUGIN_KEY_NAME: enrichment.project_name,
            PLUGIN_KEY_DESCRIPTION: (
                enrichment.project_description or f"{enrichment.project_name} plugin"
            ),
            PLUGIN_KEY_VERSION: enrichment.version,
        }
        if enrichment.env_vars:
            manifest[PLUGIN_KEY_USER_CONFIG] = {
                k: {
                    PLUGIN_KEY_DESCRIPTION: f"Environment variable {k}",
                    PLUGIN_KEY_DEFAULT: v,
                }
                for k, v in enrichment.env_vars.items()
            }
        (plugin_dir / CLAUDE_PLUGIN_MANIFEST).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        results.append(
            f"{context.source_dir_name}/{CLAUDE_PLUGIN_MANIFEST_DIR}/{CLAUDE_PLUGIN_MANIFEST}"
        )

        # 2. .mcp.json
        if enrichment.mcp_tools:
            server_script = (
                f"{context.source_dir_name}/{CLAUDE_MCP_DIR}/"
                f"{enrichment.project_name}{MCP_SERVER_SUFFIX}"
            )
            mcp_config = {
                MCP_KEY_SERVERS: {
                    enrichment.project_name: {
                        MCP_KEY_COMMAND: MCP_COMMAND,
                        MCP_KEY_ARGS: [server_script],
                    }
                }
            }
            (source / CLAUDE_MCP_JSON).write_text(
                json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8"
            )
            results.append(f"{context.source_dir_name}/{CLAUDE_MCP_JSON}")

        # 3. hooks/hooks.json
        if enrichment.hooks:
            hooks_dir = source / CLAUDE_HOOKS_DIR
            hooks_dir.mkdir(parents=True, exist_ok=True)
            hooks_data: list[dict[str, object]] = []
            for hook in enrichment.hooks:
                entry: dict[str, object] = {
                    HOOKS_KEY_EVENT: hook.event,
                    HOOKS_KEY_COMMAND: hook.command,
                    HOOKS_KEY_DESCRIPTION: hook.description,
                }
                if hook.matcher:
                    entry[HOOKS_KEY_MATCHER] = hook.matcher
                hooks_data.append(entry)
            (hooks_dir / CLAUDE_HOOKS_JSON).write_text(
                json.dumps({HOOKS_KEY_HOOKS: hooks_data}, indent=2) + "\n",
                encoding="utf-8",
            )
            results.append(
                f"{context.source_dir_name}/{CLAUDE_HOOKS_DIR}/{CLAUDE_HOOKS_JSON}"
            )

        # 4. MCP server stub + requirements.txt
        if enrichment.mcp_tools:
            mcp_dir = source / CLAUDE_MCP_DIR
            mcp_dir.mkdir(parents=True, exist_ok=True)
            server_file = f"{enrichment.project_name}{MCP_SERVER_SUFFIX}"
            (mcp_dir / server_file).write_text(
                generate_mcp_server_stub(enrichment.project_name, enrichment.mcp_tools),
                encoding="utf-8",
            )
            (mcp_dir / MCP_REQUIREMENTS).write_text(
                generate_mcp_requirements(), encoding="utf-8"
            )
            results.append(f"{context.source_dir_name}/{CLAUDE_MCP_DIR}/{server_file}")
            results.append(f"{context.source_dir_name}/{CLAUDE_MCP_DIR}/{MCP_REQUIREMENTS}")

        # 5. .claude/settings.json (merge with existing)
        settings_dir = context.project_root / CLAUDE_SETTINGS_DIR
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_path = settings_dir / CLAUDE_SETTINGS_JSON
        settings: dict[str, Any] = {}
        if settings_path.is_file():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                settings = {}

        # Register plugin
        settings.setdefault(SETTINGS_KEY_PLUGINS, [])
        plugin_ref = f"{context.source_dir_name}/"
        if plugin_ref not in settings[SETTINGS_KEY_PLUGINS]:
            settings[SETTINGS_KEY_PLUGINS].append(plugin_ref)

        # Register MCP server
        if enrichment.mcp_tools:
            settings.setdefault(SETTINGS_KEY_MCP_SERVERS, {})
            server_script = (
                f"{context.source_dir_name}/{CLAUDE_MCP_DIR}/"
                f"{enrichment.project_name}{MCP_SERVER_SUFFIX}"
            )
            settings[SETTINGS_KEY_MCP_SERVERS][enrichment.project_name] = {
                MCP_KEY_COMMAND: MCP_COMMAND,
                MCP_KEY_ARGS: [server_script],
            }

        # Register hooks
        if enrichment.hooks:
            hooks_ref = (
                f"{context.source_dir_name}/{CLAUDE_HOOKS_DIR}/{CLAUDE_HOOKS_JSON}"
            )
            settings[SETTINGS_KEY_HOOKS] = hooks_ref

        settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
        results.append(f"{CLAUDE_SETTINGS_DIR}/{CLAUDE_SETTINGS_JSON}")

        return results

    def clean(self, context: AgentContext) -> list[str]:
        removed: list[str] = []
        removed.extend(remove_file(context.project_root / CLAUDE_MD, CLAUDE_MD))
        removed.extend(
            remove_tree(context.project_root / CLAUDE_SKILLS_DIR, f"{CLAUDE_SKILLS_DIR}/")
        )
        removed.extend(remove_tree(context.project_root / CLAUDE_RULES_DIR, f"{CLAUDE_RULES_DIR}/"))

        # Enriched artifacts (inside source dir)
        if context.source_dir.is_dir():
            removed.extend(
                remove_tree(
                    context.source_dir / CLAUDE_PLUGIN_MANIFEST_DIR,
                    f"{context.source_dir_name}/{CLAUDE_PLUGIN_MANIFEST_DIR}/",
                )
            )
            removed.extend(
                remove_file(
                    context.source_dir / CLAUDE_MCP_JSON,
                    f"{context.source_dir_name}/{CLAUDE_MCP_JSON}",
                )
            )
            removed.extend(
                remove_tree(
                    context.source_dir / CLAUDE_HOOKS_DIR,
                    f"{context.source_dir_name}/{CLAUDE_HOOKS_DIR}/",
                )
            )
            removed.extend(
                remove_tree(
                    context.source_dir / CLAUDE_MCP_DIR,
                    f"{context.source_dir_name}/{CLAUDE_MCP_DIR}/",
                )
            )

        remove_dir_if_empty(context.project_root / Path(CLAUDE_SKILLS_DIR).parts[0])
        return removed


__all__ = ["ClaudeCodeAgent", "generate_claude_rules"]
