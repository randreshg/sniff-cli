"""Per-target agent configuration generators.

Reads a source-of-truth directory (``.agents/`` or ``.carts/``) and produces
agent-specific config files for Claude Code, Codex, Cursor, Copilot, and
a machine-readable ``.agents.json`` manifest.

Extracted from ``carts/tools/scripts/agents.py`` into a generic library.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dekk.agents.constants import (
    AGENTS_JSON,
    AGENTS_MD,
    AGENTS_REFERENCE_MD,
    CLAUDE_MD,
    CLAUDE_RULES_DIR,
    CLAUDE_SKILLS_DIR,
    COPILOT_DIR,
    COPILOT_INSTRUCTIONS,
    COPILOT_PER_DIR,
    COPILOT_RULE_SUFFIX,
    CURSORRULES,
    DEFAULT_SOURCE_DIR,
    PROJECT_MD,
    SKILL_FILENAME,
    TARGET_ALL,
    TARGET_CLAUDE,
    TARGET_CODEX,
    TARGET_COPILOT,
    TARGET_CURSOR,
)
from dekk.agents.discovery import (
    RuleDefinition,
    SkillDefinition,
    discover_rules,
    discover_skills,
    iter_skill_files,
)


@dataclass
class GenerateResult:
    """Summary of what was generated."""

    generated: list[str] = field(default_factory=list)
    skill_count: int = 0
    rule_count: int = 0


def render_codex_skill(skill: SkillDefinition) -> str:
    """Render a skill in Codex format (simplified frontmatter: name + description only)."""
    return (
        "---\n"
        f"name: {skill.name}\n"
        f"description: {skill.description}\n"
        "---\n\n"
        f"{skill.body.lstrip()}"
    )


def _install_skills_to_dir(
    skills: list[SkillDefinition],
    target_dir: Path,
    renderer: Any = None,
    force: bool = True,
) -> list[str]:
    """Install skills into a directory, optionally transforming SKILL.md."""
    target_dir.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []

    for skill in skills:
        dest = target_dir / skill.source_dir.name
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


def _generate_claude_rules(project_root: Path, rules: list[RuleDefinition]) -> None:
    """Generate ``.claude/rules/`` from rules (Claude Code ``paths:`` frontmatter)."""
    rules_dir = project_root / CLAUDE_RULES_DIR
    rules_dir.mkdir(parents=True, exist_ok=True)
    for rule in rules:
        paths_yaml = "\n".join(f'  - "{p}"' for p in rule.paths)
        content = f"---\npaths:\n{paths_yaml}\n---\n{rule.body}"
        (rules_dir / f"{rule.name}.md").write_text(content, encoding="utf-8")


def _generate_copilot_per_directory(project_root: Path, rules: list[RuleDefinition]) -> None:
    """Generate ``.github/instructions/`` from rules (Copilot ``applyTo:`` frontmatter)."""
    instr_dir = project_root / COPILOT_DIR / COPILOT_PER_DIR
    instr_dir.mkdir(parents=True, exist_ok=True)
    for rule in rules:
        apply_to = ",".join(rule.paths)
        content = f"---\napplyTo: {apply_to}\n---\n{rule.body}"
        (instr_dir / f"{rule.name}{COPILOT_RULE_SUFFIX}").write_text(content, encoding="utf-8")


def _generate_agents_json(
    project_root: Path,
    skills: list[SkillDefinition],
    project_name: str,
    source_dir_name: str,
    cli_name: str | None = None,
) -> None:
    """Generate ``.agents.json`` machine-readable manifest."""
    manifest: dict[str, Any] = {
        "project": project_name,
        "source_of_truth": f"{source_dir_name}/",
        "agent_configs": {
            TARGET_CLAUDE: {
                "instructions": CLAUDE_MD,
                "skills": f"{CLAUDE_SKILLS_DIR}/",
            },
            TARGET_CODEX: {
                "instructions": AGENTS_MD,
                "skills": "~/.codex/skills/",
            },
            TARGET_COPILOT: {
                "instructions": f"{COPILOT_DIR}/{COPILOT_INSTRUCTIONS}",
                "per_directory": f"{COPILOT_DIR}/{COPILOT_PER_DIR}/",
            },
            TARGET_CURSOR: {
                "instructions": CURSORRULES,
            },
        },
        "skills": [{"name": s.name, "description": s.description} for s in skills],
    }
    if cli_name:
        manifest["cli"] = cli_name

    agents_json = project_root / AGENTS_JSON
    agents_json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


class AgentConfigManager:
    """Orchestrates agent config generation from a source-of-truth directory.

    Args:
        project_root: Root directory of the project.
        source_dir: Name of the source-of-truth directory (default: ".agents").
        project_name: Project name for manifests (auto-detected from source_dir or dir name).
        cli_name: Optional CLI command name (e.g., "carts") for manifest.
    """

    def __init__(
        self,
        project_root: Path,
        source_dir: str = DEFAULT_SOURCE_DIR,
        project_name: str | None = None,
        cli_name: str | None = None,
    ) -> None:
        self.project_root = project_root
        self.source_dir_name = source_dir
        self.source_dir = project_root / source_dir
        self.cli_name = cli_name
        self.project_name = project_name or project_root.name

    def _read_project_md(self) -> str | None:
        """Read project.md from the source directory."""
        project_md = self.source_dir / PROJECT_MD
        if not project_md.is_file():
            return None
        return project_md.read_text(encoding="utf-8")

    def generate(self, target: str = TARGET_ALL) -> GenerateResult:
        """Generate agent configs for the specified target(s).

        Args:
            target: One of "claude", "codex", "cursor", "copilot", "all".

        Returns:
            GenerateResult with list of generated files.
        """
        effective_target = target.lower()
        result = GenerateResult()

        skills = discover_skills(self.source_dir)
        result.skill_count = len(skills)

        project_content = self._read_project_md()
        if not project_content:
            msg = f"{self.source_dir_name}/{PROJECT_MD} not found"
            raise FileNotFoundError(msg)

        rules = discover_rules(self.source_dir)
        result.rule_count = len(rules)

        if effective_target in (TARGET_ALL, TARGET_CLAUDE):
            self._generate_claude(project_content, skills, rules)
            result.generated.append(CLAUDE_MD)
            result.generated.append(f"{CLAUDE_SKILLS_DIR}/ ({len(skills)} skills)")
            result.generated.append(f"{CLAUDE_RULES_DIR}/ ({len(rules)} rules)")

        if effective_target in (TARGET_ALL, TARGET_CODEX):
            self._generate_codex(project_content)
            result.generated.append(AGENTS_MD)

        if effective_target in (TARGET_ALL, TARGET_CURSOR):
            self._generate_cursor(project_content)
            result.generated.append(CURSORRULES)

        if effective_target in (TARGET_ALL, TARGET_COPILOT):
            self._generate_copilot(project_content, rules)
            result.generated.append(f"{COPILOT_DIR}/{COPILOT_INSTRUCTIONS}")
            result.generated.append(
                f"{COPILOT_DIR}/{COPILOT_PER_DIR}/ ({len(rules)} rules)"
            )

        if effective_target == TARGET_ALL:
            self._generate_manifest(skills)
            result.generated.append(AGENTS_JSON)

        return result

    def _generate_claude(
        self,
        project_content: str,
        skills: list[SkillDefinition],
        rules: list[RuleDefinition],
    ) -> None:
        """Generate CLAUDE.md + .claude/skills/ + .claude/rules/."""
        claude_md = self.project_root / CLAUDE_MD
        claude_md.write_text(project_content, encoding="utf-8")

        claude_skills = self.project_root / CLAUDE_SKILLS_DIR
        _install_skills_to_dir(skills, claude_skills)

        _generate_claude_rules(self.project_root, rules)

    def _generate_codex(self, project_content: str) -> None:
        """Generate AGENTS.md (Codex reads this from cwd).

        Uses agents-reference.md if available, otherwise project.md.
        """
        agents_ref = self.source_dir / AGENTS_REFERENCE_MD
        if agents_ref.is_file():
            content = agents_ref.read_text(encoding="utf-8")
        else:
            content = project_content

        agents_md = self.project_root / AGENTS_MD
        agents_md.write_text(content, encoding="utf-8")

    def _generate_cursor(self, project_content: str) -> None:
        """Generate .cursorrules (full project.md content)."""
        cursor_path = self.project_root / CURSORRULES
        cursor_path.write_text(project_content, encoding="utf-8")

    def _generate_copilot(
        self,
        project_content: str,
        rules: list[RuleDefinition],
    ) -> None:
        """Generate .github/copilot-instructions.md + .github/instructions/."""
        copilot_dir = self.project_root / COPILOT_DIR
        copilot_dir.mkdir(parents=True, exist_ok=True)
        copilot_path = copilot_dir / COPILOT_INSTRUCTIONS
        copilot_path.write_text(project_content, encoding="utf-8")

        _generate_copilot_per_directory(self.project_root, rules)

    def _generate_manifest(self, skills: list[SkillDefinition]) -> None:
        """Generate .agents.json machine-readable manifest."""
        _generate_agents_json(
            self.project_root,
            skills,
            self.project_name,
            self.source_dir_name,
            self.cli_name,
        )
