"""Cursor provider implementation."""

from __future__ import annotations

from dekk.agents.constants import CURSORRULES, TARGET_CURSOR
from dekk.agents.providers.base import AgentContext, DekkAgent
from dekk.agents.providers.shared import remove_file


class CursorAgent(DekkAgent):
    """Cursor target generation."""

    target = TARGET_CURSOR

    def generate(self, context: AgentContext) -> list[str]:
        cursor_path = context.project_root / CURSORRULES
        cursor_path.write_text(context.project_content, encoding="utf-8")
        return [CURSORRULES]

    def clean(self, context: AgentContext) -> list[str]:
        return remove_file(context.project_root / CURSORRULES, CURSORRULES)


__all__ = ["CursorAgent"]
