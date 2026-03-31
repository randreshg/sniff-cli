"""Codex skill installation and state checking.

Installs skills from the source-of-truth directory to ``~/.codex/skills/``
(or a custom directory) for Codex agent discovery.

Extracted from ``carts/tools/scripts/agents.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dekk.agents.constants import (
    CODEX_HOME_DEFAULT,
    CODEX_HOME_ENV,
    CODEX_SKILLS_DIR_NAME,
    SKILL_FILENAME,
)
from dekk.agents.discovery import SkillDefinition, discover_skills
from dekk.agents.providers.codex import render_codex_skill
from dekk.agents.providers.shared import install_skills_to_dir


def codex_home() -> Path:
    """Get the Codex home directory (``$CODEX_HOME`` or ``~/.codex``)."""
    override = os.environ.get(CODEX_HOME_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / CODEX_HOME_DEFAULT


def codex_skills_dir() -> Path:
    """Get the default Codex skills directory."""
    return codex_home() / CODEX_SKILLS_DIR_NAME


def check_skill_state(
    skill: SkillDefinition,
    target_dir: Path,
    renderer: object = None,
) -> str:
    """Check if a skill is installed and up to date in ``target_dir``.

    Returns "missing", "stale", or "ok".
    """
    dest = target_dir / skill.source_dir.name / SKILL_FILENAME
    if not dest.is_file():
        return "missing"
    try:
        expected = renderer(skill) if callable(renderer) else skill.source_file.read_text(
            encoding="utf-8"
        )
        if dest.read_text(encoding="utf-8") != expected:
            return "stale"
    except OSError:
        return "stale"
    return "ok"


def install_codex_skills(
    source_dir: Path,
    codex_dir: Path | None = None,
    force: bool = True,
) -> list[str]:
    """Install skills from ``source_dir`` to a Codex skills directory.

    Args:
        source_dir: Source-of-truth directory (e.g., ``.agents/``).
        codex_dir: Target directory (default: ``~/.codex/skills/``).
        force: Overwrite existing skills.

    Returns:
        List of installed skill names.
    """
    skills = discover_skills(source_dir)
    effective_dir = codex_dir.expanduser() if codex_dir else codex_skills_dir()
    return install_skills_to_dir(
        skills,
        effective_dir,
        renderer=render_codex_skill,
        force=force,
    )
