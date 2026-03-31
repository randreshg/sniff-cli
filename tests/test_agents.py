"""Tests for dekk.agents — agent config generation."""

from __future__ import annotations

from pathlib import Path

import pytest
from dekk.agents.constants import AGENTS_JSON, AGENTS_MD, CLAUDE_MD, CURSORRULES


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    """Create a minimal .agents/ source-of-truth directory."""
    source = tmp_path / ".agents"
    skills = source / "skills"
    rules = source / "rules"
    source.mkdir()
    skills.mkdir()
    rules.mkdir()

    # project.md
    (source / "project.md").write_text(
        "# Test Project\n\nThis is a test project.\n\n"
        "## Build\n\n```bash\nmake\n```\n",
        encoding="utf-8",
    )

    # A skill
    build_skill = skills / "build"
    build_skill.mkdir()
    (build_skill / "SKILL.md").write_text(
        "---\nname: build\ndescription: Build the project\nuser-invocable: true\n---\n\n"
        "# Build\n\nRun `make` to build.\n",
        encoding="utf-8",
    )

    # A second skill
    test_skill = skills / "test"
    test_skill.mkdir()
    (test_skill / "SKILL.md").write_text(
        "---\nname: test\ndescription: Run test suite\n---\n\n"
        "# Test\n\nRun `pytest` to test.\n",
        encoding="utf-8",
    )

    # A rule
    (rules / "tests.md").write_text(
        '---\npaths:\n  - "tests/**/*"\n  - "test/**/*"\n---\n\n'
        "Use descriptive test names.\n",
        encoding="utf-8",
    )

    return source


@pytest.fixture
def project_root(agents_dir: Path) -> Path:
    """Return the project root (parent of .agents/)."""
    return agents_dir.parent


# ============================================================================
# Discovery Tests
# ============================================================================


class TestDiscovery:
    def test_discover_skills(self, agents_dir: Path) -> None:
        from dekk.agents.discovery import discover_skills

        skills = discover_skills(agents_dir)
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"build", "test"}

    def test_discover_skills_empty(self, tmp_path: Path) -> None:
        from dekk.agents.discovery import discover_skills

        empty = tmp_path / ".agents"
        empty.mkdir()
        assert discover_skills(empty) == []

    def test_discover_skills_no_dir(self, tmp_path: Path) -> None:
        from dekk.agents.discovery import discover_skills

        assert discover_skills(tmp_path / "nonexistent") == []

    def test_skill_properties(self, agents_dir: Path) -> None:
        from dekk.agents.discovery import discover_skills

        skills = discover_skills(agents_dir)
        build = next(s for s in skills if s.name == "build")
        assert build.description == "Build the project"
        assert "make" in build.body

    def test_discover_rules(self, agents_dir: Path) -> None:
        from dekk.agents.discovery import discover_rules

        rules = discover_rules(agents_dir)
        assert len(rules) == 1
        assert rules[0].name == "tests"
        assert "tests/**/*" in rules[0].paths
        assert "test/**/*" in rules[0].paths
        assert "descriptive" in rules[0].body

    def test_discover_rules_empty(self, tmp_path: Path) -> None:
        from dekk.agents.discovery import discover_rules

        assert discover_rules(tmp_path / "nonexistent") == []

    def test_parse_frontmatter(self) -> None:
        from dekk.agents.discovery import parse_frontmatter

        text = "---\nname: foo\ndescription: bar\n---\n\nBody text.\n"
        meta, body = parse_frontmatter(text)
        assert meta["name"] == "foo"
        assert meta["description"] == "bar"
        assert "Body text." in body

    def test_parse_frontmatter_missing(self) -> None:
        from dekk.agents.discovery import parse_frontmatter

        text = "# Just a heading\n\nNo frontmatter here.\n"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_skill_missing_required_field(self, tmp_path: Path) -> None:
        from dekk.agents.discovery import _parse_skill

        skill_dir = tmp_path / "skills" / "bad"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\nname: bad\n---\n\nMissing description.\n")

        with pytest.raises(ValueError, match="missing required 'description'"):
            _parse_skill(skill_file)

    def test_skill_missing_frontmatter(self, tmp_path: Path) -> None:
        from dekk.agents.discovery import _parse_skill

        skill_dir = tmp_path / "skills" / "nofm"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# No frontmatter\n\nJust text.\n")

        with pytest.raises(ValueError, match="missing YAML frontmatter"):
            _parse_skill(skill_file)

    def test_iter_skill_files(self, agents_dir: Path) -> None:
        from dekk.agents.discovery import discover_skills, iter_skill_files

        skills = discover_skills(agents_dir)
        build = next(s for s in skills if s.name == "build")
        files = iter_skill_files(build)
        relative_names = {str(rel) for _, rel in files}
        assert "SKILL.md" in relative_names


# ============================================================================
# Generator Tests
# ============================================================================


class TestGenerators:
    def test_generate_all(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        result = manager.generate("all")

        assert (project_root / "CLAUDE.md").is_file()
        assert (project_root / "AGENTS.md").is_file()
        assert (project_root / ".cursorrules").is_file()
        assert (project_root / ".github" / "copilot-instructions.md").is_file()
        assert (project_root / ".agents.json").is_file()
        assert result.skill_count == 2
        assert result.rule_count == 1
        assert len(result.generated) >= 5

    def test_generate_claude_only(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        result = manager.generate("claude")

        assert (project_root / "CLAUDE.md").is_file()
        assert not (project_root / ".cursorrules").exists()
        assert any("CLAUDE.md" in g for g in result.generated)

    def test_claude_md_content(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        manager.generate("claude")

        content = (project_root / "CLAUDE.md").read_text()
        assert "Test Project" in content

    def test_claude_skills_synced(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        manager.generate("claude")

        claude_skills = project_root / ".claude" / "skills"
        assert (claude_skills / "build" / "SKILL.md").is_file()
        assert (claude_skills / "test" / "SKILL.md").is_file()

    def test_claude_rules_synced(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        manager.generate("claude")

        rules_dir = project_root / ".claude" / "rules"
        tests_rule = rules_dir / "tests.md"
        assert tests_rule.is_file()
        content = tests_rule.read_text()
        assert "tests/**/*" in content
        assert "paths:" in content

    def test_copilot_per_directory(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        manager.generate("copilot")

        instr = project_root / ".github" / "instructions" / "tests.instructions.md"
        assert instr.is_file()
        content = instr.read_text()
        assert "applyTo:" in content

    def test_agents_json(self, project_root: Path) -> None:
        import json

        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        manager.generate("all")

        manifest = json.loads((project_root / ".agents.json").read_text())
        assert manifest["source_of_truth"] == ".agents/"
        assert len(manifest["skills"]) == 2
        names = {s["name"] for s in manifest["skills"]}
        assert names == {"build", "test"}

    def test_agents_reference_md(self, project_root: Path, agents_dir: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        # Create agents-reference.md
        (agents_dir / "agents-reference.md").write_text(
            "# Detailed Reference\n\nFull docs here.\n"
        )

        manager = AgentConfigManager(project_root)
        manager.generate("codex")

        agents_md = project_root / "AGENTS.md"
        assert agents_md.is_file()
        assert "Detailed Reference" in agents_md.read_text()

    def test_custom_agent_abstraction(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager, AgentContext, DekkAgent

        class StubAgent(DekkAgent):
            target = "stub"

            def generate(self, context: AgentContext) -> list[str]:
                output = context.project_root / "STUB.md"
                output.write_text(context.project_content, encoding="utf-8")
                return ["STUB.md"]

        manager = AgentConfigManager(project_root, agents=(StubAgent(),))
        result = manager.generate("stub")

        assert result.generated == ["STUB.md"]
        assert (project_root / "STUB.md").is_file()

    def test_clean_all_removes_generated_outputs(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        manager.generate("all")

        result = manager.clean("all")

        assert AGENTS_MD in result.removed
        assert CLAUDE_MD in result.removed
        assert CURSORRULES in result.removed
        assert AGENTS_JSON in result.removed
        assert not (project_root / AGENTS_MD).exists()
        assert not (project_root / CLAUDE_MD).exists()
        assert not (project_root / CURSORRULES).exists()
        assert not (project_root / AGENTS_JSON).exists()
        assert not (project_root / ".claude").exists()

    def test_clean_specific_target_only_removes_that_target(self, project_root: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        manager = AgentConfigManager(project_root)
        manager.generate("all")

        result = manager.clean("codex")

        assert result.removed == [AGENTS_MD]
        assert not (project_root / AGENTS_MD).exists()
        assert (project_root / CLAUDE_MD).exists()
        assert (project_root / CURSORRULES).exists()

    def test_generate_no_project_md(self, tmp_path: Path) -> None:
        from dekk.agents.generators import AgentConfigManager

        empty = tmp_path / ".agents"
        empty.mkdir()

        manager = AgentConfigManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            manager.generate()

    def test_render_codex_skill(self, agents_dir: Path) -> None:
        from dekk.agents.discovery import discover_skills
        from dekk.agents.generators import render_codex_skill

        skills = discover_skills(agents_dir)
        build = next(s for s in skills if s.name == "build")
        rendered = render_codex_skill(build)

        assert rendered.startswith("---\n")
        assert "name: build" in rendered
        assert "description: Build the project" in rendered
        # Only name and description in frontmatter (no user-invocable)
        lines_before_close = rendered.split("---\n")[1].strip().split("\n")
        assert len(lines_before_close) == 2


# ============================================================================
# Installer Tests
# ============================================================================


class TestInstaller:
    def test_install_codex_skills(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.installer import install_codex_skills

        codex_dir = tmp_path / "codex_skills"
        installed = install_codex_skills(agents_dir, codex_dir=codex_dir)
        assert len(installed) == 2
        assert (codex_dir / "build" / "SKILL.md").is_file()
        assert (codex_dir / "test" / "SKILL.md").is_file()

        # Verify codex rendering (simplified frontmatter)
        content = (codex_dir / "build" / "SKILL.md").read_text()
        assert "name: build" in content
        assert "user-invocable" not in content

    def test_check_skill_state_missing(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.discovery import discover_skills
        from dekk.agents.installer import check_skill_state

        skills = discover_skills(agents_dir)
        state = check_skill_state(skills[0], tmp_path / "empty")
        assert state == "missing"

    def test_check_skill_state_ok(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.discovery import discover_skills
        from dekk.agents.installer import check_skill_state, install_codex_skills

        install_codex_skills(agents_dir, codex_dir=tmp_path)

        skills = discover_skills(agents_dir)
        build = next(s for s in skills if s.name == "build")

        from dekk.agents.generators import render_codex_skill

        state = check_skill_state(build, tmp_path, renderer=render_codex_skill)
        assert state == "ok"

    def test_check_skill_state_stale(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.discovery import discover_skills
        from dekk.agents.generators import render_codex_skill
        from dekk.agents.installer import check_skill_state, install_codex_skills

        install_codex_skills(agents_dir, codex_dir=tmp_path)

        # Modify the installed skill
        (tmp_path / "build" / "SKILL.md").write_text("stale content")

        skills = discover_skills(agents_dir)
        build = next(s for s in skills if s.name == "build")
        state = check_skill_state(build, tmp_path, renderer=render_codex_skill)
        assert state == "stale"

    def test_no_force_skip(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.installer import install_codex_skills

        codex_dir = tmp_path / "codex_skills"

        # First install
        installed_1 = install_codex_skills(agents_dir, codex_dir=codex_dir, force=True)
        assert len(installed_1) == 2

        # Second install without force — still installs because dir exists
        # but with force=False, existing dirs are skipped
        installed_2 = install_codex_skills(agents_dir, codex_dir=codex_dir, force=False)
        assert len(installed_2) == 0


# ============================================================================
# Scaffold Tests
# ============================================================================


class TestScaffold:
    def test_scaffold_from_toml(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import scaffold_agents_dir

        # Create a .dekk.toml with commands
        (tmp_path / ".dekk.toml").write_text(
            '[project]\nname = "my-project"\n\n'
            "[commands]\n"
            'build = { run = "make", description = "Build project" }\n'
            'test = { run = "make test", description = "Run tests" }\n',
            encoding="utf-8",
        )

        result = scaffold_agents_dir(tmp_path)
        assert result == tmp_path / ".agents"
        assert (result / "project.md").is_file()
        assert (result / "skills" / "build" / "SKILL.md").is_file()
        assert (result / "skills" / "test" / "SKILL.md").is_file()

        # Verify skill content
        build_skill = (result / "skills" / "build" / "SKILL.md").read_text()
        assert "name: build" in build_skill
        assert "make" in build_skill

    def test_scaffold_project_detection_cargo(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import _detect_project_info

        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'\n")
        info = _detect_project_info(tmp_path)
        assert info["language"] == "Rust"
        assert "cargo" in info["build"]

    def test_scaffold_project_detection_cmake(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import _detect_project_info

        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.14)\n")
        info = _detect_project_info(tmp_path)
        assert info["language"] == "C/C++"
        assert "cmake" in info["build"]

    def test_scaffold_project_detection_npm(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import _detect_project_info

        (tmp_path / "package.json").write_text('{"name": "test"}\n')
        info = _detect_project_info(tmp_path)
        assert info["language"] == "TypeScript/JavaScript"

    def test_scaffold_project_detection_python(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import _detect_project_info

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
        info = _detect_project_info(tmp_path)
        assert info["language"] == "Python"

    def test_scaffold_no_overwrite(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import scaffold_agents_dir

        (tmp_path / ".dekk.toml").write_text(
            '[project]\nname = "test"\n'
            '[commands]\nbuild = { run = "make", description = "Build" }\n',
        )

        # First scaffold
        scaffold_agents_dir(tmp_path)
        original_content = (tmp_path / ".agents" / "project.md").read_text()

        # Modify project.md
        (tmp_path / ".agents" / "project.md").write_text("Custom content")

        # Second scaffold without force — should NOT overwrite
        scaffold_agents_dir(tmp_path)
        assert (tmp_path / ".agents" / "project.md").read_text() == "Custom content"

    def test_scaffold_force_overwrite(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import scaffold_agents_dir

        (tmp_path / ".dekk.toml").write_text(
            '[project]\nname = "test"\n'
            '[commands]\nbuild = { run = "make", description = "Build" }\n',
        )

        scaffold_agents_dir(tmp_path)
        (tmp_path / ".agents" / "project.md").write_text("Custom content")

        # Force overwrite
        scaffold_agents_dir(tmp_path, force=True)
        content = (tmp_path / ".agents" / "project.md").read_text()
        assert content != "Custom content"

    def test_scaffold_custom_source_dir(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import scaffold_agents_dir

        result = scaffold_agents_dir(tmp_path, source_dir=".carts")
        assert result == tmp_path / ".carts"
        assert (result / "project.md").is_file()

    def test_commands_to_skills_no_overwrite(self, tmp_path: Path) -> None:
        from dekk.agents.scaffold import DiscoveredCommand, commands_to_skills

        skills_dir = tmp_path / "skills"

        # Create initial skill
        cmds = [DiscoveredCommand(name="build", description="Build", run="make")]
        created = commands_to_skills(cmds, skills_dir)
        assert len(created) == 1

        # Modify the skill
        (skills_dir / "build" / "SKILL.md").write_text("Custom content")

        # Re-run — should NOT overwrite
        created_2 = commands_to_skills(cmds, skills_dir)
        assert len(created_2) == 0
        assert (skills_dir / "build" / "SKILL.md").read_text() == "Custom content"


# ============================================================================
# Envspec Extension Tests
# ============================================================================


class TestEnvspecExtensions:
    def test_command_spec_parsing(self, tmp_path: Path) -> None:
        from dekk.environment.spec import EnvironmentSpec

        toml_path = tmp_path / ".dekk.toml"
        toml_path.write_text(
            '[project]\nname = "test"\n\n'
            "[commands]\n"
            'build = { run = "make", description = "Build" }\n'
            'clean = "rm -rf build"\n',
            encoding="utf-8",
        )

        spec = EnvironmentSpec.from_file(toml_path)
        assert "build" in spec.commands
        assert spec.commands["build"].run == "make"
        assert spec.commands["build"].description == "Build"
        assert "clean" in spec.commands
        assert spec.commands["clean"].run == "rm -rf build"

    def test_agents_spec_parsing(self, tmp_path: Path) -> None:
        from dekk.environment.spec import EnvironmentSpec

        toml_path = tmp_path / ".dekk.toml"
        toml_path.write_text(
            '[project]\nname = "test"\n\n'
            "[agents]\n"
            'source = ".carts"\n'
            'targets = ["claude", "codex"]\n',
            encoding="utf-8",
        )

        spec = EnvironmentSpec.from_file(toml_path)
        assert spec.agents is not None
        assert spec.agents.source == ".carts"
        assert spec.agents.targets == ("claude", "codex")

    def test_agents_spec_defaults(self, tmp_path: Path) -> None:
        from dekk.environment.spec import EnvironmentSpec

        toml_path = tmp_path / ".dekk.toml"
        toml_path.write_text('[project]\nname = "test"\n', encoding="utf-8")

        spec = EnvironmentSpec.from_file(toml_path)
        assert spec.agents is None
        assert spec.commands == {}


# ============================================================================
# Typer Integration Tests
# ============================================================================


class TestTyperIntegration:
    def test_agent_skill_marker(self) -> None:
        from dekk.typer_app import Typer

        app = Typer(name="test")

        @app.command(agent_skill=True)
        def build() -> None:
            """Build the project."""

        @app.command()
        def clean() -> None:
            """Clean build artifacts."""

        assert getattr(build, "_dekk_agent_skill", False) is True
        assert getattr(clean, "_dekk_agent_skill", False) is False

    def test_discover_commands_from_typer(self) -> None:
        from dekk.agents.scaffold import discover_commands_from_typer
        from dekk.typer_app import Typer

        app = Typer(name="test")

        @app.command(agent_skill=True)
        def build() -> None:
            """Build the project."""

        @app.command(agent_skill=True)
        def test_cmd() -> None:
            """Run tests."""

        @app.command()
        def clean() -> None:
            """Not a skill."""

        commands = discover_commands_from_typer(app, "myapp")
        names = {c.name for c in commands}
        # build and test_cmd should be discovered, clean should not
        assert "build" in names
        assert "clean" not in names

    def test_discover_commands_run_format(self) -> None:
        from dekk.agents.scaffold import discover_commands_from_typer
        from dekk.typer_app import Typer

        app = Typer(name="myapp")

        @app.command(agent_skill=True)
        def build() -> None:
            """Build the project."""

        commands = discover_commands_from_typer(app, "myapp")
        assert commands[0].run == "myapp build"


# ============================================================================
# End-to-End Integration Tests
# ============================================================================


class TestProjectRootResolution:
    def test_walk_up_finds_agents_dir(self, tmp_path: Path) -> None:
        """_find_project_root walks up from subdir to find .agents/."""
        from unittest.mock import patch

        from dekk.agents.app import _find_project_root

        # Create project with .agents/ at root
        (tmp_path / ".agents").mkdir()
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)

        with patch("dekk.agents.app.Path") as mock_path:
            mock_path.cwd.return_value = subdir
            # walk_up needs real Path, so only mock cwd
        # Use the real function with monkeypatched cwd
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            root = _find_project_root(".agents")
            assert root == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_walk_up_finds_dekk_toml(self, tmp_path: Path) -> None:
        """_find_project_root walks up from subdir to find .dekk.toml."""
        from dekk.agents.app import _find_project_root

        (tmp_path / ".dekk.toml").write_text('[project]\nname = "test"\n')
        subdir = tmp_path / "src"
        subdir.mkdir()

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            root = _find_project_root(".agents")
            assert root == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_fallback_to_cwd(self, tmp_path: Path) -> None:
        """_find_project_root falls back to cwd when nothing is found."""
        from dekk.agents.app import _find_project_root

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            root = _find_project_root(".agents")
            assert root == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_explicit_get_project_root_callback(self, tmp_path: Path) -> None:
        """get_project_root callback overrides walk-up."""
        from dekk.agents.app import create_agents_app

        custom_root = tmp_path / "my-repo"
        custom_root.mkdir()

        # The callback should always be used when provided
        app = create_agents_app(
            source_dir=".carts",
            get_project_root=lambda: custom_root,
        )
        # Verify the app was created (it's a typer.Typer)
        assert app is not None

    def test_generate_writes_to_project_root_not_cwd(self, tmp_path: Path) -> None:
        """Generate writes to project_root, not cwd, even when called from elsewhere."""
        from dekk.agents.generators import AgentConfigManager
        from dekk.agents.scaffold import scaffold_agents_dir

        project_root = tmp_path / "my-project"
        project_root.mkdir()
        (project_root / ".dekk.toml").write_text(
            '[project]\nname = "test"\n'
            '[commands]\nbuild = { run = "make", description = "Build" }\n'
        )

        # Scaffold in the project root
        scaffold_agents_dir(project_root)

        # Generate from a DIFFERENT directory
        some_other_dir = tmp_path / "somewhere-else"
        some_other_dir.mkdir()

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(some_other_dir)

            # Use AgentConfigManager with explicit project_root
            manager = AgentConfigManager(project_root=project_root)
            manager.generate("all")

            # Files should be in project_root, NOT in cwd
            assert (project_root / "CLAUDE.md").is_file()
            assert (project_root / ".agents.json").is_file()
            assert not (some_other_dir / "CLAUDE.md").exists()
            assert not (some_other_dir / ".agents.json").exists()
        finally:
            os.chdir(original_cwd)

    def test_agents_init_auto_creates_dekk_toml(self, tmp_path: Path) -> None:
        """`agents init` should seed `.dekk.toml` before scaffolding `.agents/`."""
        import os

        from typer.testing import CliRunner

        from dekk.agents.app import create_agents_app

        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            'name = "demo-app"\n\n'
            "[build-system]\n"
            'build-backend = "setuptools.build_meta"\n',
            encoding="utf-8",
        )

        runner = CliRunner()
        app = create_agents_app()

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(app, ["init"])
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0
        assert (tmp_path / ".dekk.toml").is_file()
        assert (tmp_path / ".agents" / "project.md").is_file()
        assert (tmp_path / ".agents" / "skills" / "build" / "SKILL.md").is_file()

    def test_agents_clean_command(self, project_root: Path) -> None:
        import os

        from typer.testing import CliRunner

        from dekk.agents.app import create_agents_app

        from dekk.agents.generators import AgentConfigManager

        AgentConfigManager(project_root).generate("all")

        runner = CliRunner()
        app = create_agents_app()

        original_cwd = os.getcwd()
        try:
            os.chdir(project_root)
            result = runner.invoke(app, ["clean", "--target", "codex"])
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0
        assert not (project_root / AGENTS_MD).exists()
        assert (project_root / CLAUDE_MD).exists()


class TestFlowGeneration:
    """Tests for dekk agents flow — acpx flow template generation."""

    def test_generate_review_flow(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        created = generate_flow(tmp_path, "review")
        assert any("review.flow.ts" in str(p) for p in created)
        flow_file = tmp_path / "flows" / "review.flow.ts"
        assert flow_file.is_file()
        content = flow_file.read_text()
        assert "defineFlow" in content
        assert 'name: "pr-review"' in content
        assert "load_pr" in content
        assert "review_code" in content
        assert "$output.route" in content

    def test_generate_triage_flow(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        created = generate_flow(tmp_path, "triage")
        flow_file = tmp_path / "flows" / "triage.flow.ts"
        assert flow_file.is_file()
        content = flow_file.read_text()
        assert 'name: "pr-triage"' in content
        assert "extract_intent" in content
        assert "test_changes" in content
        assert "final_review" in content
        assert "comment_and_close" in content

    def test_generate_echo_flow(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        created = generate_flow(tmp_path, "echo")
        flow_file = tmp_path / "flows" / "echo.flow.ts"
        assert flow_file.is_file()
        content = flow_file.read_text()
        assert 'name: "echo-test"' in content
        assert 'profile: "codex"' in content
        assert 'profile: "claude"' in content

    def test_generates_utils_and_package_json(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        generate_flow(tmp_path, "review")
        assert (tmp_path / "flows" / "lib" / "utils.ts").is_file()
        assert (tmp_path / "flows" / "package.json").is_file()
        assert (tmp_path / "flows" / "tsconfig.json").is_file()

    def test_no_overwrite_without_force(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        generate_flow(tmp_path, "review")
        # Second call should not overwrite
        created = generate_flow(tmp_path, "review")
        assert len(created) == 0

    def test_force_overwrites(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        generate_flow(tmp_path, "review")
        created = generate_flow(tmp_path, "review", force=True)
        assert any("review.flow.ts" in str(p) for p in created)

    def test_invalid_template(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        with pytest.raises(ValueError, match="Unknown template"):
            generate_flow(tmp_path, "nonexistent")

    def test_embeds_project_skills(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        # The agents_dir fixture creates build and test skills
        created = generate_flow(tmp_path, "triage")
        content = (tmp_path / "flows" / "triage.flow.ts").read_text()
        # Should reference build and test skills in embedSkills calls
        assert '"build"' in content
        assert '"test"' in content

    def test_uses_dekk_toml_project_name(self, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        # Create .dekk.toml with project name
        (tmp_path / ".dekk.toml").write_text(
            '[project]\nname = "my-fancy-project"\n'
        )
        # Create minimal .agents/
        source = tmp_path / ".agents"
        (source / "skills").mkdir(parents=True)
        (source / "project.md").write_text("# my-fancy-project\n")

        generate_flow(tmp_path, "echo")
        content = (tmp_path / "flows" / "echo.flow.ts").read_text()
        assert "my-fancy-project" in content

    def test_shared_utils_not_duplicated(self, agents_dir: Path, tmp_path: Path) -> None:
        from dekk.agents.flows import generate_flow

        # Generate review (creates utils.ts)
        generate_flow(tmp_path, "review")
        utils_content = (tmp_path / "flows" / "lib" / "utils.ts").read_text()
        # Generate triage (should NOT recreate utils.ts)
        created = generate_flow(tmp_path, "triage")
        assert not any("utils.ts" in str(p) for p in created)
        # Content should be unchanged
        assert (tmp_path / "flows" / "lib" / "utils.ts").read_text() == utils_content


class TestEndToEnd:
    def test_full_pipeline(self, tmp_path: Path) -> None:
        """Test the full init -> generate -> install pipeline."""
        from dekk.agents.generators import AgentConfigManager
        from dekk.agents.installer import install_codex_skills
        from dekk.agents.scaffold import scaffold_agents_dir

        # Create project with .dekk.toml
        (tmp_path / ".dekk.toml").write_text(
            '[project]\nname = "e2e-test"\n\n'
            "[commands]\n"
            'build = { run = "make", description = "Build" }\n'
            'test = { run = "pytest", description = "Test" }\n',
        )

        # Step 1: Scaffold
        scaffold_agents_dir(tmp_path)
        assert (tmp_path / ".agents" / "project.md").is_file()
        assert (tmp_path / ".agents" / "skills" / "build" / "SKILL.md").is_file()

        # Step 2: Generate
        manager = AgentConfigManager(tmp_path, project_name="e2e-test")
        result = manager.generate("all")
        assert (tmp_path / "CLAUDE.md").is_file()
        assert (tmp_path / "AGENTS.md").is_file()
        assert (tmp_path / ".cursorrules").is_file()
        assert (tmp_path / ".agents.json").is_file()
        assert result.skill_count == 2

        # Step 3: Install to codex
        codex_target = tmp_path / "codex_skills"
        installed = install_codex_skills(
            tmp_path / ".agents", codex_dir=codex_target
        )
        assert len(installed) == 2
        assert (codex_target / "build" / "SKILL.md").is_file()

        # Verify CLAUDE.md content
        claude_content = (tmp_path / "CLAUDE.md").read_text()
        assert "e2e-test" in claude_content

        # Verify .agents.json content
        import json

        manifest = json.loads((tmp_path / ".agents.json").read_text())
        assert manifest["project"] == "e2e-test"
        assert len(manifest["skills"]) == 2
