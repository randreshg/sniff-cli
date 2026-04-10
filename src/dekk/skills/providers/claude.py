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
    HOOKS_KEY_COMMAND_PATTERN,
    HOOKS_KEY_FILE_PATTERN,
    HOOKS_KEY_HOOKS,
    HOOKS_KEY_MATCHER,
    HOOKS_KEY_TOOL_NAME,
    HOOKS_KEY_TYPE,
    HOOKS_KEY_TYPE_COMMAND,
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

        # 3. hooks/hooks.json (new Claude Code format: record keyed by event)
        if enrichment.hooks:
            hooks_dir = source / CLAUDE_HOOKS_DIR
            hooks_dir.mkdir(parents=True, exist_ok=True)
            hooks_record = self._build_hooks_record(enrichment.hooks)
            (hooks_dir / CLAUDE_HOOKS_JSON).write_text(
                json.dumps(hooks_record, indent=2) + "\n",
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

        # Register plugin (check both string and dict forms to avoid duplicates)
        settings.setdefault(SETTINGS_KEY_PLUGINS, [])
        plugin_ref = f"{context.source_dir_name}/"
        already_registered = any(
            (isinstance(p, str) and p.rstrip("/") == context.source_dir_name)
            or (isinstance(p, dict) and p.get("path", "").rstrip("/") == context.source_dir_name)
            for p in settings[SETTINGS_KEY_PLUGINS]
        )
        if not already_registered:
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

        # Register hooks (inline as record, not a file path)
        if enrichment.hooks:
            settings[SETTINGS_KEY_HOOKS] = self._build_hooks_record(
                enrichment.hooks
            )

        settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
        results.append(f"{CLAUDE_SETTINGS_DIR}/{CLAUDE_SETTINGS_JSON}")

        return results

    @staticmethod
    def _build_hooks_record(
        hooks: list[Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """Build the new Claude Code hooks record format.

        Groups hooks by event name, each with matcher + hooks array::

            {"PostToolUse": [{"matcher": {...}, "hooks": [{"type": "command", "command": "..."}]}]}
        """
        from collections import defaultdict

        from dekk.skills.providers.enrichment import HookDef

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for hook in hooks:
            assert isinstance(hook, HookDef)
            hook_entry: dict[str, Any] = {
                HOOKS_KEY_HOOKS: [
                    {
                        HOOKS_KEY_TYPE: HOOKS_KEY_TYPE_COMMAND,
                        HOOKS_KEY_COMMAND: hook.command,
                    }
                ],
            }
            if hook.matcher:
                matcher: dict[str, str] = {}
                if HOOKS_KEY_TOOL_NAME in hook.matcher:
                    matcher[HOOKS_KEY_TOOL_NAME] = hook.matcher[HOOKS_KEY_TOOL_NAME]
                if HOOKS_KEY_FILE_PATTERN in hook.matcher:
                    matcher[HOOKS_KEY_FILE_PATTERN] = hook.matcher[HOOKS_KEY_FILE_PATTERN]
                if HOOKS_KEY_COMMAND_PATTERN in hook.matcher:
                    matcher[HOOKS_KEY_COMMAND_PATTERN] = hook.matcher[HOOKS_KEY_COMMAND_PATTERN]
                if matcher:
                    hook_entry[HOOKS_KEY_MATCHER] = matcher
            grouped[hook.event].append(hook_entry)
        return dict(grouped)

    def clean(self, context: AgentContext) -> list[str]:
        removed: list[str] = []
        removed.extend(remove_file(context.project_root / CLAUDE_MD, CLAUDE_MD))
        removed.extend(
            remove_tree(context.project_root / CLAUDE_SKILLS_DIR, f"{CLAUDE_SKILLS_DIR}/")
        )
        removed.extend(remove_tree(context.project_root / CLAUDE_RULES_DIR, f"{CLAUDE_RULES_DIR}/"))

        # Enriched artifacts (inside source dir) — remove only generated files,
        # not entire dirs that may contain hand-crafted content.
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
            # hooks.json and MCP server stub — remove specific generated files only
            removed.extend(
                remove_file(
                    context.source_dir / CLAUDE_HOOKS_DIR / CLAUDE_HOOKS_JSON,
                    f"{context.source_dir_name}/{CLAUDE_HOOKS_DIR}/{CLAUDE_HOOKS_JSON}",
                )
            )
            remove_dir_if_empty(context.source_dir / CLAUDE_HOOKS_DIR)

            # Remove generated MCP server + requirements, preserve other files
            project_name = context.project_name
            server_file = f"{project_name}{MCP_SERVER_SUFFIX}"
            removed.extend(
                remove_file(
                    context.source_dir / CLAUDE_MCP_DIR / server_file,
                    f"{context.source_dir_name}/{CLAUDE_MCP_DIR}/{server_file}",
                )
            )
            removed.extend(
                remove_file(
                    context.source_dir / CLAUDE_MCP_DIR / MCP_REQUIREMENTS,
                    f"{context.source_dir_name}/{CLAUDE_MCP_DIR}/{MCP_REQUIREMENTS}",
                )
            )
            remove_dir_if_empty(context.source_dir / CLAUDE_MCP_DIR)

        # Clean up settings.json entries added by enrichment
        settings_path = context.project_root / CLAUDE_SETTINGS_DIR / CLAUDE_SETTINGS_JSON
        if settings_path.is_file():
            self._clean_settings(settings_path, context)

        remove_dir_if_empty(context.project_root / Path(CLAUDE_SKILLS_DIR).parts[0])
        return removed

    def _clean_settings(self, settings_path: Path, context: AgentContext) -> None:
        """Remove enrichment entries from .claude/settings.json."""
        try:
            settings: dict[str, Any] = json.loads(
                settings_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return

        changed = False

        # Remove plugin reference
        plugins = settings.get(SETTINGS_KEY_PLUGINS, [])
        new_plugins = [
            p for p in plugins
            if not (
                (isinstance(p, str) and p.rstrip("/") == context.source_dir_name)
                or (
                    isinstance(p, dict)
                    and p.get("path", "").rstrip("/") == context.source_dir_name
                )
            )
        ]
        if len(new_plugins) != len(plugins):
            settings[SETTINGS_KEY_PLUGINS] = new_plugins
            changed = True

        # Remove MCP server entry
        mcp_servers = settings.get(SETTINGS_KEY_MCP_SERVERS, {})
        if context.project_name in mcp_servers:
            del mcp_servers[context.project_name]
            changed = True

        # Remove hooks
        if SETTINGS_KEY_HOOKS in settings:
            del settings[SETTINGS_KEY_HOOKS]
            changed = True

        if changed:
            settings_path.write_text(
                json.dumps(settings, indent=2) + "\n", encoding="utf-8"
            )


__all__ = ["ClaudeCodeAgent", "generate_claude_rules"]
