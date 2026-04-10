"""Per-target agent configuration generators.

Reads a source-of-truth directory (``.agents/`` or ``.carts/``) and produces
agent-specific config files for Claude Code, Codex, Cursor, Copilot, and
a machine-readable ``.agents.json`` manifest.

Extracted from ``carts/tools/scripts/agents.py`` into a generic library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dekk.environment.spec import EnvironmentSpec, SkillsSpec
from dekk.skills.constants import (
    AGENTS_JSON,
    AGENTS_MD,
    ALL_TARGETS,
    CLAUDE_MD,
    CLAUDE_SKILLS_DIR,
    COPILOT_DIR,
    COPILOT_INSTRUCTIONS,
    COPILOT_PER_DIR,
    CURSORRULES,
    DEFAULT_SOURCE_DIR,
    PROJECT_MD,
    TARGET_ALL,
    TARGET_CLAUDE,
    TARGET_CODEX,
    TARGET_COPILOT,
    TARGET_CURSOR,
)
from dekk.skills.discovery import SkillDefinition, discover_rules, discover_skills
from dekk.skills.providers import (
    AgentContext,
    ClaudeCodeAgent,
    CodexAgent,
    CopilotAgent,
    CursorAgent,
    DekkAgent,
    default_agents,
    render_codex_skill,
)
from dekk.skills.providers.shared import remove_file

_BUILTIN_TARGETS: frozenset[str] = frozenset({TARGET_ALL, *ALL_TARGETS})


def render_skills_index(skills: list[SkillDefinition]) -> str:
    """Render ``skills_index.md`` content from discovered skills.

    The index gives agents a lightweight lookup so they can pick the right
    skill before loading full SKILL.md instructions.
    """
    lines = ["## Available Skills", ""]
    for skill in skills:
        lines.append(f"### {skill.name}")
        lines.append(f"Use when: {skill.description.rstrip('.')}.")
        lines.append("")
    return "\n".join(lines)

_TARGET_CONFIGS: dict[str, dict[str, str]] = {
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
}


def _validate_target(target: str, known_targets: set[str] | None = None) -> None:
    """Raise ``ValidationError`` if *target* is not a recognised value."""
    valid = _BUILTIN_TARGETS | known_targets if known_targets else _BUILTIN_TARGETS
    if target not in valid:
        from dekk.cli.errors import ValidationError

        raise ValidationError(
            f"Unknown target {target!r}",
            hint=f"Valid targets: {', '.join(sorted(valid))}",
        )


@dataclass
class GenerateResult:
    """Summary of what was generated."""

    generated: list[str] = field(default_factory=list)
    skill_count: int = 0
    rule_count: int = 0


@dataclass
class CleanResult:
    """Summary of what was removed."""

    removed: list[str] = field(default_factory=list)


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
        "agent_configs": {k: dict(v) for k, v in _TARGET_CONFIGS.items()},
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
        agents: tuple[DekkAgent, ...] | None = None,
        agents_spec: SkillsSpec | None = None,
        env_spec: EnvironmentSpec | None = None,
    ) -> None:
        self.project_root = project_root
        self.source_dir_name = source_dir
        self.source_dir = project_root / source_dir
        self.cli_name = cli_name
        self.project_name = project_name or project_root.name
        self._agents_spec = agents_spec
        self._env_spec = env_spec
        self._abstractions = {
            agent.target: agent
            for agent in (agents or default_agents())
        }

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

        Raises:
            ValidationError: If *target* is not a recognised value.
        """
        effective_target = target.lower()
        _validate_target(effective_target, set(self._abstractions))
        result = GenerateResult()

        skills = discover_skills(self.source_dir)
        result.skill_count = len(skills)

        project_content = self._read_project_md()
        if not project_content:
            msg = f"{self.source_dir_name}/{PROJECT_MD} not found"
            raise FileNotFoundError(msg)

        rules = discover_rules(self.source_dir)
        result.rule_count = len(rules)

        enrichment = None
        if self._agents_spec and self._agents_spec.enrich and self._env_spec:
            from dekk.skills.providers.enrichment import compute_enrichment

            enrichment = compute_enrichment(self._env_spec, self.cli_name)

        context = AgentContext(
            project_root=self.project_root,
            source_dir=self.source_dir,
            source_dir_name=self.source_dir_name,
            project_name=self.project_name,
            cli_name=self.cli_name,
            project_content=project_content,
            skills=skills,
            rules=rules,
            project_description=self._env_spec.project_description if self._env_spec else "",
            enrichment=enrichment,
            skills_spec=self._agents_spec,
        )

        if effective_target == TARGET_ALL:
            # Honour [agents].targets from .dekk.toml when present.
            if self._agents_spec and self._agents_spec.targets:
                allowed = set(self._agents_spec.targets)
            else:
                allowed = set(ALL_TARGETS)
            for target_name in (TARGET_CLAUDE, TARGET_CODEX, TARGET_CURSOR, TARGET_COPILOT):
                if target_name in allowed:
                    result.generated.extend(
                        self._abstractions[target_name].generate(context)
                    )
        else:
            result.generated.extend(self._abstractions[effective_target].generate(context))

        # Always update the manifest (merge single-target entries).
        self._generate_manifest(skills, effective_target)
        result.generated.append(AGENTS_JSON)

        return result

    def clean(self, target: str = TARGET_ALL) -> CleanResult:
        """Remove generated files for the specified target(s).

        Raises:
            ValidationError: If *target* is not a recognised value.
        """
        effective_target = target.lower()
        _validate_target(effective_target, set(self._abstractions))
        context = AgentContext(
            project_root=self.project_root,
            source_dir=self.source_dir,
            source_dir_name=self.source_dir_name,
            project_name=self.project_name,
            cli_name=self.cli_name,
            project_content="",
            skills=[],
            rules=[],
        )
        result = CleanResult()

        if effective_target == TARGET_ALL:
            for target_name in (TARGET_CLAUDE, TARGET_CODEX, TARGET_CURSOR, TARGET_COPILOT):
                result.removed.extend(self._abstractions[target_name].clean(context))
            result.removed.extend(remove_file(self.project_root / AGENTS_JSON, AGENTS_JSON))
        else:
            result.removed.extend(self._abstractions[effective_target].clean(context))

        return result

    def _generate_manifest(
        self,
        skills: list[SkillDefinition],
        effective_target: str = TARGET_ALL,
    ) -> None:
        """Generate or update ``.agents.json`` machine-readable manifest.

        When *effective_target* is ``"all"`` the full manifest is written.
        For a single target, the existing manifest is read (if present) and
        only the entry for that target is updated, preserving other entries.
        """
        if effective_target == TARGET_ALL:
            _generate_agents_json(
                self.project_root,
                skills,
                self.project_name,
                self.source_dir_name,
                self.cli_name,
            )
        else:
            agents_json_path = self.project_root / AGENTS_JSON

            # Read existing manifest if present, otherwise start fresh.
            if agents_json_path.is_file():
                try:
                    existing = json.loads(
                        agents_json_path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError):
                    existing = {}
            else:
                existing = {}

            # Merge / initialise fields.
            existing.setdefault("project", self.project_name)
            existing.setdefault("source_of_truth", f"{self.source_dir_name}/")
            agent_configs = existing.setdefault("agent_configs", {})
            if effective_target in _TARGET_CONFIGS:
                agent_configs[effective_target] = dict(_TARGET_CONFIGS[effective_target])
            existing["skills"] = [
                {"name": s.name, "description": s.description} for s in skills
            ]
            if self.cli_name:
                existing["cli"] = self.cli_name

            agents_json_path.write_text(
                json.dumps(existing, indent=2) + "\n", encoding="utf-8"
            )


__all__ = [
    "AgentConfigManager",
    "AgentContext",
    "CleanResult",
    "ClaudeCodeAgent",
    "CodexAgent",
    "CopilotAgent",
    "CursorAgent",
    "DekkAgent",
    "GenerateResult",
    "default_agents",
    "render_codex_skill",
]
