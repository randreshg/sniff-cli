"""Built-in agent provider implementations."""

from __future__ import annotations

from dekk.skills.providers.base import AgentContext, DekkAgent
from dekk.skills.providers.claude import ClaudeCodeAgent
from dekk.skills.providers.codex import CodexAgent, render_codex_skill
from dekk.skills.providers.copilot import CopilotAgent
from dekk.skills.providers.cursor import CursorAgent


def default_agents() -> tuple[DekkAgent, ...]:
    """Return the built-in target generators."""
    return (
        ClaudeCodeAgent(),
        CodexAgent(),
        CursorAgent(),
        CopilotAgent(),
    )


__all__ = [
    "AgentContext",
    "DekkAgent",
    "ClaudeCodeAgent",
    "CodexAgent",
    "CopilotAgent",
    "CursorAgent",
    "default_agents",
    "render_codex_skill",
]
