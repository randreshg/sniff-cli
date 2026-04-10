"""Skill state checking for dekk agents.

Checks whether skills are installed and up to date in target directories.
"""

from __future__ import annotations

from pathlib import Path

from dekk.skills.constants import SKILL_FILENAME
from dekk.skills.discovery import SkillDefinition


def check_skill_state(
    skill: SkillDefinition,
    target_dir: Path,
    renderer: object = None,
) -> str:
    """Check if a skill is installed and up to date in ``target_dir``.

    Returns "missing", "stale", or "ok".
    """
    dest = target_dir / skill.relative_install_path / SKILL_FILENAME
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
