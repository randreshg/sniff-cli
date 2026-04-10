"""Cursor provider implementation."""

from __future__ import annotations

import json

from dekk.skills.constants import (
    CLAUDE_MCP_DIR,
    CURSOR_DIR,
    CURSOR_MCP_JSON,
    CURSORRULES,
    MCP_COMMAND,
    MCP_KEY_ARGS,
    MCP_KEY_COMMAND,
    MCP_KEY_SERVERS,
    MCP_SERVER_SUFFIX,
    TARGET_CURSOR,
)
from dekk.skills.providers.base import AgentContext, DekkAgent
from dekk.skills.providers.shared import remove_dir_if_empty, remove_file


class CursorAgent(DekkAgent):
    """Cursor target generation."""

    target = TARGET_CURSOR

    def generate(self, context: AgentContext) -> list[str]:
        cursor_path = context.project_root / CURSORRULES
        cursor_path.write_text(context.project_content, encoding="utf-8")
        results = [CURSORRULES]

        if context.enrichment and context.enrichment.mcp_tools:
            results.extend(self._generate_mcp_config(context))

        return results

    def _generate_mcp_config(self, context: AgentContext) -> list[str]:
        """Generate ``.cursor/mcp.json`` referencing the shared MCP server."""
        enrichment = context.enrichment
        assert enrichment is not None

        cursor_dir = context.project_root / CURSOR_DIR
        cursor_dir.mkdir(parents=True, exist_ok=True)

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

        mcp_path = cursor_dir / CURSOR_MCP_JSON
        # Merge with existing config if present.
        if mcp_path.is_file():
            try:
                existing = json.loads(mcp_path.read_text(encoding="utf-8"))
                existing.setdefault(MCP_KEY_SERVERS, {}).update(
                    mcp_config[MCP_KEY_SERVERS]
                )
                mcp_config = existing
            except (json.JSONDecodeError, OSError):
                pass

        mcp_path.write_text(
            json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8"
        )
        return [f"{CURSOR_DIR}/{CURSOR_MCP_JSON}"]

    def clean(self, context: AgentContext) -> list[str]:
        removed = remove_file(context.project_root / CURSORRULES, CURSORRULES)

        # Remove only our project's MCP entry, preserving other servers.
        mcp_path = context.project_root / CURSOR_DIR / CURSOR_MCP_JSON
        if mcp_path.is_file():
            try:
                config = json.loads(mcp_path.read_text(encoding="utf-8"))
                servers = config.get(MCP_KEY_SERVERS, {})
                if context.project_name in servers:
                    del servers[context.project_name]
                    if servers:
                        # Other entries remain — rewrite the file.
                        mcp_path.write_text(
                            json.dumps(config, indent=2) + "\n", encoding="utf-8"
                        )
                    else:
                        # No entries left — remove the file.
                        removed.extend(
                            remove_file(mcp_path, f"{CURSOR_DIR}/{CURSOR_MCP_JSON}")
                        )
            except (json.JSONDecodeError, OSError):
                removed.extend(
                    remove_file(mcp_path, f"{CURSOR_DIR}/{CURSOR_MCP_JSON}")
                )

        remove_dir_if_empty(context.project_root / CURSOR_DIR)
        return removed


__all__ = ["CursorAgent"]
