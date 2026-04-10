"""Shared helpers for built-in agent providers."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from dekk.skills.constants import SKILL_FILENAME
from dekk.skills.discovery import SkillDefinition, iter_skill_files


def install_skills_to_dir(
    skills: list[SkillDefinition],
    target_dir: Path,
    renderer: Any = None,
    force: bool = True,
) -> list[str]:
    """Install skills into a directory, optionally transforming `SKILL.md`."""
    target_dir.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []

    for skill in skills:
        dest = target_dir / skill.relative_install_path
        if dest.exists() and not force:
            continue
        dest.mkdir(parents=True, exist_ok=True)

        for source_path, relative in iter_skill_files(skill):
            target_path = dest / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if relative.as_posix() == SKILL_FILENAME and renderer:
                target_path.write_text(renderer(skill), encoding="utf-8")
            else:
                shutil.copy2(source_path, target_path)

        installed.append(skill.name)

    return installed


def remove_file(path: Path, label: str) -> list[str]:
    """Remove a generated file if it exists."""
    if not path.is_file():
        return []
    path.unlink()
    return [label]


def remove_tree(path: Path, label: str) -> list[str]:
    """Remove a generated directory tree if it exists."""
    if not path.exists():
        return []
    shutil.rmtree(path)
    return [label]


def remove_dir_if_empty(path: Path) -> None:
    """Remove a directory if it exists and has no remaining children."""
    if path.is_dir() and not any(path.iterdir()):
        path.rmdir()


__all__ = [
    "install_skills_to_dir",
    "remove_dir_if_empty",
    "remove_file",
    "remove_tree",
]
