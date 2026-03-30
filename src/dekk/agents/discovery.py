"""Skill and rule discovery with YAML frontmatter parsing.

Scans a source directory for SKILL.md files (skills) and *.md files (rules),
extracting YAML frontmatter metadata from each.

Extracted from ``carts/tools/scripts/agents.py`` into a reusable library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dekk.agents.constants import (
    REQUIRED_SKILL_FIELDS,
    RULES_DIR_NAME,
    RULES_GLOB,
    SKILL_FILENAME,
    SKILLS_DIR_NAME,
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_PATHS_KEY = "paths:"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from a markdown file.

    Returns (metadata_dict, body_after_frontmatter).
    Handles simple ``key: value`` pairs and ``paths:`` lists.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip()

    return metadata, text[match.end():]


def _parse_paths_list(frontmatter_text: str) -> list[str]:
    """Extract a ``paths:`` YAML list from frontmatter text."""
    paths: list[str] = []
    in_paths = False
    for line in frontmatter_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_PATHS_KEY):
            in_paths = True
            continue
        if in_paths and stripped.startswith("- "):
            path_val = stripped[2:].strip().strip('"').strip("'")
            paths.append(path_val)
        elif in_paths and not stripped.startswith("-"):
            in_paths = False
    return paths


@dataclass(frozen=True)
class SkillDefinition:
    """A skill discovered from a ``skills/<name>/SKILL.md`` file."""

    source_dir: Path
    source_file: Path
    metadata: dict[str, str]
    body: str

    @property
    def name(self) -> str:
        return self.metadata[REQUIRED_SKILL_FIELDS[0]]

    @property
    def description(self) -> str:
        return self.metadata[REQUIRED_SKILL_FIELDS[1]]


@dataclass(frozen=True)
class RuleDefinition:
    """A path-scoped rule discovered from ``rules/<name>.md``."""

    source_file: Path
    name: str
    paths: list[str]
    body: str


def _parse_skill(skill_file: Path) -> SkillDefinition:
    """Parse a single SKILL.md file into a SkillDefinition."""
    text = skill_file.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)

    if not metadata:
        msg = f"Skill file missing YAML frontmatter: {skill_file}"
        raise ValueError(msg)

    for key in REQUIRED_SKILL_FIELDS:
        if key not in metadata or not metadata[key]:
            msg = f"Skill file missing required '{key}': {skill_file}"
            raise ValueError(msg)

    return SkillDefinition(
        source_dir=skill_file.parent,
        source_file=skill_file,
        metadata=metadata,
        body=body,
    )


def discover_skills(source_dir: Path) -> list[SkillDefinition]:
    """Discover all skills from ``source_dir/skills/*/SKILL.md``."""
    skills_dir = source_dir / SKILLS_DIR_NAME
    if not skills_dir.is_dir():
        return []

    skills: list[SkillDefinition] = []
    for skill_file in sorted(skills_dir.glob(f"*/{SKILL_FILENAME}")):
        skills.append(_parse_skill(skill_file))
    return skills


def discover_rules(source_dir: Path) -> list[RuleDefinition]:
    """Discover all rules from ``source_dir/rules/*.md``."""
    rules_dir = source_dir / RULES_DIR_NAME
    if not rules_dir.is_dir():
        return []

    rules: list[RuleDefinition] = []
    for rule_file in sorted(rules_dir.glob(RULES_GLOB)):
        text = rule_file.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(text)
        if not match:
            continue

        paths = _parse_paths_list(match.group(1))
        if not paths:
            continue

        rules.append(RuleDefinition(
            source_file=rule_file,
            name=rule_file.stem,
            paths=paths,
            body=text[match.end():],
        ))
    return rules


def iter_skill_files(skill: SkillDefinition) -> list[tuple[Path, Path]]:
    """Yield (absolute_path, relative_path) for all files in a skill directory."""
    result: list[tuple[Path, Path]] = []
    for path in sorted(skill.source_dir.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(skill.source_dir)
        result.append((path, relative))
    return result
