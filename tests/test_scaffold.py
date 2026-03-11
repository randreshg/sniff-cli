"""Tests for project scaffolding -- type detection, templates, setup scripts."""

import json
from pathlib import Path

import pytest

from sniff.scaffold import (
    FileTemplate,
    ProjectFramework,
    ProjectLanguage,
    ProjectType,
    ProjectTypeDetector,
    SetupScript,
    SetupScriptBuilder,
    SetupStep,
    TemplateRegistry,
    TemplateSet,
)


@pytest.fixture
def detector():
    return ProjectTypeDetector()


# ---------------------------------------------------------------------------
# ProjectTypeDetector -- language detection
# ---------------------------------------------------------------------------


class TestLanguageDetection:
    def test_detect_python_pyproject(self, tmp_path, detector):
        """Detect Python project from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.PYTHON

    def test_detect_python_setup_py(self, tmp_path, detector):
        """Detect Python project from setup.py."""
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='myapp')\n",
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.PYTHON
        assert result.framework == ProjectFramework.SETUPTOOLS

    def test_detect_rust(self, tmp_path, detector):
        """Detect Rust project from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "myapp"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.RUST
        assert result.framework == ProjectFramework.CARGO

    def test_detect_javascript(self, tmp_path, detector):
        """Detect JavaScript project from package.json."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "myapp", "version": "1.0.0"}),
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.JAVASCRIPT

    def test_detect_typescript(self, tmp_path, detector):
        """Detect TypeScript via tsconfig.json alongside package.json."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "myapp"}),
            encoding="utf-8",
        )
        (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.TYPESCRIPT

    def test_detect_go(self, tmp_path, detector):
        """Detect Go project from go.mod."""
        (tmp_path / "go.mod").write_text(
            "module example.com/myapp\n\ngo 1.21\n",
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.GO
        assert result.framework == ProjectFramework.GO_MODULE

    def test_detect_java_maven(self, tmp_path, detector):
        """Detect Java/Maven project from pom.xml."""
        (tmp_path / "pom.xml").write_text("<project></project>", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.JAVA
        assert result.framework == ProjectFramework.MAVEN

    def test_detect_java_gradle(self, tmp_path, detector):
        """Detect Java/Gradle project from build.gradle."""
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.JAVA
        assert result.framework == ProjectFramework.GRADLE

    def test_detect_cpp_cmake(self, tmp_path, detector):
        """Detect C++/CMake project."""
        (tmp_path / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\n",
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.CPP
        assert result.framework == ProjectFramework.CMAKE

    def test_detect_ruby(self, tmp_path, detector):
        """Detect Ruby project from Gemfile."""
        (tmp_path / "Gemfile").write_text(
            'source "https://rubygems.org"\n',
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.RUBY
        assert result.framework == ProjectFramework.BUNDLER

    def test_detect_unknown_empty_dir(self, tmp_path, detector):
        """Empty directory returns UNKNOWN."""
        result = detector.detect(tmp_path)
        assert result.language == ProjectLanguage.UNKNOWN

    def test_detect_nonexistent_dir(self, tmp_path, detector):
        """Non-existent directory returns UNKNOWN."""
        result = detector.detect(tmp_path / "nope")
        assert result.language == ProjectLanguage.UNKNOWN


# ---------------------------------------------------------------------------
# ProjectTypeDetector -- framework refinement
# ---------------------------------------------------------------------------


class TestFrameworkDetection:
    def test_python_hatch_backend(self, tmp_path, detector):
        """Detect Hatch build backend."""
        (tmp_path / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n'
            '[project]\nname = "mylib"\n',
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.framework == ProjectFramework.HATCH

    def test_python_poetry_backend(self, tmp_path, detector):
        """Detect Poetry build backend."""
        (tmp_path / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["poetry-core"]\n'
            'build-backend = "poetry.core.masonry.api"\n'
            '[tool.poetry]\nname = "mylib"\n',
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.framework == ProjectFramework.POETRY

    def test_python_django_framework(self, tmp_path, detector):
        """Django dependency overrides build backend."""
        (tmp_path / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n'
            '[project]\nname = "myapp"\n'
            'dependencies = ["django>=4.0"]\n',
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.framework == ProjectFramework.DJANGO

    def test_python_fastapi_framework(self, tmp_path, detector):
        """Detect FastAPI framework."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "api"\n'
            'dependencies = ["fastapi", "uvicorn"]\n',
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.framework == ProjectFramework.FASTAPI

    def test_js_react_framework(self, tmp_path, detector):
        """Detect React framework from package.json deps."""
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "my-react-app",
                "dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"},
            }),
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.framework == ProjectFramework.REACT

    def test_js_next_framework(self, tmp_path, detector):
        """Detect Next.js framework when it is the only dep."""
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "my-next-app",
                "dependencies": {"next": "^14.0.0"},
            }),
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.framework == ProjectFramework.NEXT

    def test_js_vue_framework(self, tmp_path, detector):
        """Detect Vue.js framework."""
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "my-vue-app",
                "dependencies": {"vue": "^3.0.0"},
            }),
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.framework == ProjectFramework.VUE


# ---------------------------------------------------------------------------
# ProjectTypeDetector -- project characteristics
# ---------------------------------------------------------------------------


class TestProjectCharacteristics:
    def test_detect_has_tests(self, tmp_path, detector):
        """Detect test directory."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "tests").mkdir()
        result = detector.detect(tmp_path)
        assert result.has_tests is True

    def test_detect_no_tests(self, tmp_path, detector):
        """No test directory detected."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.has_tests is False

    def test_detect_has_ci_github(self, tmp_path, detector):
        """Detect GitHub Actions CI."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.has_ci is True

    def test_detect_has_ci_gitlab(self, tmp_path, detector):
        """Detect GitLab CI."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (tmp_path / ".gitlab-ci.yml").write_text("stages:\n  - test\n", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.has_ci is True

    def test_detect_has_docs(self, tmp_path, detector):
        """Detect docs directory."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "docs").mkdir()
        result = detector.detect(tmp_path)
        assert result.has_docs is True

    def test_detect_monorepo_cargo(self, tmp_path, detector):
        """Detect Cargo workspace as monorepo."""
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/*"]\n',
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.is_monorepo is True

    def test_detect_monorepo_pnpm(self, tmp_path, detector):
        """Detect pnpm workspace as monorepo."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "root"}),
            encoding="utf-8",
        )
        (tmp_path / "pnpm-workspace.yaml").write_text(
            "packages:\n  - 'packages/*'\n",
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.is_monorepo is True

    def test_detect_monorepo_npm_workspaces(self, tmp_path, detector):
        """Detect npm workspaces as monorepo."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "root", "workspaces": ["packages/*"]}),
            encoding="utf-8",
        )
        result = detector.detect(tmp_path)
        assert result.is_monorepo is True

    def test_detect_python_library(self, tmp_path, detector):
        """Python project with src/ layout is a library."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "src").mkdir()
        result = detector.detect(tmp_path)
        assert result.is_library is True

    def test_detect_rust_library(self, tmp_path, detector):
        """Rust project with src/lib.rs is a library."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "mylib"\n',
            encoding="utf-8",
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "lib.rs").write_text("", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.is_library is True

    def test_detect_rust_application(self, tmp_path, detector):
        """Rust project with src/main.rs is an application."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "myapp"\n',
            encoding="utf-8",
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.is_application is True

    def test_detect_python_application(self, tmp_path, detector):
        """Python project with manage.py is an application."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "manage.py").write_text("", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.is_application is True


# ---------------------------------------------------------------------------
# ProjectTypeDetector -- entry points
# ---------------------------------------------------------------------------


class TestEntryPoints:
    def test_python_entry_points(self, tmp_path, detector):
        """Detect Python entry point files."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "main.py").write_text("", encoding="utf-8")
        (tmp_path / "app.py").write_text("", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert "main.py" in result.entry_points
        assert "app.py" in result.entry_points

    def test_rust_entry_point(self, tmp_path, detector):
        """Detect Rust main.rs entry point."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert "src/main.rs" in result.entry_points

    def test_go_entry_points(self, tmp_path, detector):
        """Detect Go entry points including cmd/ convention."""
        (tmp_path / "go.mod").write_text("module example.com/x\ngo 1.21\n", encoding="utf-8")
        (tmp_path / "main.go").write_text("package main", encoding="utf-8")
        cmd_dir = tmp_path / "cmd" / "server"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "main.go").write_text("package main", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert "main.go" in result.entry_points
        assert "cmd/server/main.go" in result.entry_points

    def test_typescript_entry_point(self, tmp_path, detector):
        """Detect TypeScript entry point."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
        (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("", encoding="utf-8")
        result = detector.detect(tmp_path)
        assert "src/index.ts" in result.entry_points

    def test_no_entry_points(self, tmp_path, detector):
        """No entry points in empty project."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        result = detector.detect(tmp_path)
        assert result.entry_points == ()


# ---------------------------------------------------------------------------
# ProjectType dataclass
# ---------------------------------------------------------------------------


class TestProjectType:
    def test_frozen(self):
        """ProjectType is immutable."""
        pt = ProjectType(language=ProjectLanguage.PYTHON)
        with pytest.raises(AttributeError):
            pt.language = ProjectLanguage.RUST  # type: ignore[misc]

    def test_defaults(self):
        """ProjectType has sensible defaults."""
        pt = ProjectType(language=ProjectLanguage.PYTHON)
        assert pt.framework == ProjectFramework.NONE
        assert pt.is_library is False
        assert pt.is_application is False
        assert pt.is_monorepo is False
        assert pt.has_tests is False
        assert pt.has_ci is False
        assert pt.has_docs is False
        assert pt.entry_points == ()


# ---------------------------------------------------------------------------
# FileTemplate & TemplateSet
# ---------------------------------------------------------------------------


class TestTemplates:
    def test_file_template_frozen(self):
        """FileTemplate is immutable."""
        ft = FileTemplate(relative_path="setup.py", content="# setup")
        with pytest.raises(AttributeError):
            ft.content = "changed"  # type: ignore[misc]

    def test_template_set_properties(self):
        """TemplateSet exposes file_count and paths."""
        ts = TemplateSet(
            name="python-basic",
            description="Basic Python project",
            language=ProjectLanguage.PYTHON,
            files=(
                FileTemplate(relative_path="setup.py", content="# setup"),
                FileTemplate(relative_path="README.md", content="# My Project"),
                FileTemplate(relative_path="src/__init__.py", content=""),
            ),
        )
        assert ts.file_count == 3
        assert ts.paths == ("setup.py", "README.md", "src/__init__.py")

    def test_template_set_tags(self):
        """TemplateSet supports tags."""
        ts = TemplateSet(
            name="fastapi",
            description="FastAPI project",
            language=ProjectLanguage.PYTHON,
            framework=ProjectFramework.FASTAPI,
            tags=("api", "web", "async"),
        )
        assert "api" in ts.tags
        assert "web" in ts.tags


# ---------------------------------------------------------------------------
# TemplateRegistry
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    def test_register_and_find(self):
        """Register and find template sets."""
        registry = TemplateRegistry()
        ts = TemplateSet(
            name="python-lib",
            description="Python library",
            language=ProjectLanguage.PYTHON,
        )
        registry.register_template_set(ts)

        results = registry.find(ProjectLanguage.PYTHON)
        assert len(results) == 1
        assert results[0].name == "python-lib"

    def test_find_no_match(self):
        """Find returns empty for unmatched language."""
        registry = TemplateRegistry()
        ts = TemplateSet(
            name="python-lib",
            description="Python library",
            language=ProjectLanguage.PYTHON,
        )
        registry.register_template_set(ts)

        results = registry.find(ProjectLanguage.RUST)
        assert results == []

    def test_find_with_framework_filter(self):
        """Find filters by framework when specified."""
        registry = TemplateRegistry()
        generic = TemplateSet(
            name="python-generic",
            description="Generic Python",
            language=ProjectLanguage.PYTHON,
        )
        django = TemplateSet(
            name="python-django",
            description="Django project",
            language=ProjectLanguage.PYTHON,
            framework=ProjectFramework.DJANGO,
        )
        registry.register_template_set(generic)
        registry.register_template_set(django)

        # Searching for DJANGO should return both (generic has NONE framework)
        results = registry.find(ProjectLanguage.PYTHON, ProjectFramework.DJANGO)
        names = {r.name for r in results}
        assert "python-django" in names
        assert "python-generic" in names

    def test_find_by_tag(self):
        """Find template sets by tag."""
        registry = TemplateRegistry()
        ts1 = TemplateSet(
            name="api-template",
            description="API",
            language=ProjectLanguage.PYTHON,
            tags=("api", "rest"),
        )
        ts2 = TemplateSet(
            name="web-template",
            description="Web",
            language=ProjectLanguage.PYTHON,
            tags=("web", "frontend"),
        )
        registry.register_template_set(ts1)
        registry.register_template_set(ts2)

        results = registry.find_by_tag("api")
        assert len(results) == 1
        assert results[0].name == "api-template"

    def test_all_templates(self):
        """all_templates returns everything registered."""
        registry = TemplateRegistry()
        for name in ("a", "b", "c"):
            registry.register_template_set(TemplateSet(
                name=name,
                description=name,
                language=ProjectLanguage.PYTHON,
            ))
        assert len(registry.all_templates) == 3

    def test_register_provider(self):
        """Register and query a TemplateProvider."""

        class MyProvider:
            def get_templates(self, language, framework=ProjectFramework.NONE):
                if language == ProjectLanguage.RUST:
                    return [TemplateSet(
                        name="rust-wasm",
                        description="Rust WASM",
                        language=ProjectLanguage.RUST,
                    )]
                return []

        registry = TemplateRegistry()
        registry.register_provider(MyProvider())

        results = registry.find(ProjectLanguage.RUST)
        assert len(results) == 1
        assert results[0].name == "rust-wasm"

        # Provider should not return for Python
        results = registry.find(ProjectLanguage.PYTHON)
        assert results == []


# ---------------------------------------------------------------------------
# SetupStep & SetupScript
# ---------------------------------------------------------------------------


class TestSetupStep:
    def test_frozen(self):
        """SetupStep is immutable."""
        step = SetupStep(name="build", command="make")
        with pytest.raises(AttributeError):
            step.command = "cmake"  # type: ignore[misc]

    def test_optional_step(self):
        """Optional step defaults to False."""
        step = SetupStep(name="lint", command="ruff check .")
        assert step.optional is False

        optional = SetupStep(name="lint", command="ruff check .", optional=True)
        assert optional.optional is True


class TestSetupScript:
    def test_step_count(self):
        """step_count returns correct count."""
        script = SetupScript(
            name="test",
            description="Test script",
            steps=(
                SetupStep(name="a", command="echo a"),
                SetupStep(name="b", command="echo b"),
            ),
        )
        assert script.step_count == 2

    def test_required_and_optional_steps(self):
        """required_steps and optional_steps partition correctly."""
        script = SetupScript(
            name="test",
            description="Test script",
            steps=(
                SetupStep(name="a", command="echo a"),
                SetupStep(name="b", command="echo b", optional=True),
                SetupStep(name="c", command="echo c"),
            ),
        )
        assert len(script.required_steps) == 2
        assert len(script.optional_steps) == 1
        assert script.optional_steps[0].name == "b"

    def test_render_posix(self):
        """Render script as bash."""
        script = SetupScript(
            name="setup",
            description="Setup project",
            steps=(
                SetupStep(name="install", command="pip install -e ."),
                SetupStep(
                    name="lint",
                    command="ruff check .",
                    optional=True,
                ),
            ),
            env_vars=(("PYTHONDONTWRITEBYTECODE", "1"),),
        )
        rendered = script.render("bash")
        assert "#!/usr/bin/env bash" in rendered
        assert "set -euo pipefail" in rendered
        assert 'export PYTHONDONTWRITEBYTECODE="1"' in rendered
        assert "pip install -e ." in rendered
        assert "ruff check . || true" in rendered

    def test_render_fish(self):
        """Render script as fish."""
        script = SetupScript(
            name="setup",
            description="Setup project",
            steps=(
                SetupStep(name="install", command="pip install -e ."),
            ),
            env_vars=(("FOO", "bar"),),
        )
        rendered = script.render("fish")
        assert "#!/usr/bin/env fish" in rendered
        assert "set -gx FOO bar" in rendered
        assert "pip install -e ." in rendered

    def test_render_powershell(self):
        """Render script as PowerShell."""
        script = SetupScript(
            name="setup",
            description="Setup project",
            steps=(
                SetupStep(name="build", command="dotnet build"),
                SetupStep(name="lint", command="dotnet format", optional=True),
            ),
            env_vars=(("DOTNET_CLI_TELEMETRY_OPTOUT", "1"),),
        )
        rendered = script.render("powershell")
        assert "$ErrorActionPreference = 'Stop'" in rendered
        assert '$env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"' in rendered
        assert "dotnet build" in rendered
        assert "try { dotnet format } catch { }" in rendered

    def test_render_with_condition(self):
        """Render step with condition."""
        script = SetupScript(
            name="setup",
            description="Conditional setup",
            steps=(
                SetupStep(
                    name="migrate",
                    command="python manage.py migrate",
                    condition="[ -f manage.py ]",
                ),
            ),
        )
        rendered = script.render("bash")
        assert "if [ -f manage.py ]; then" in rendered
        assert "    python manage.py migrate" in rendered
        assert "fi" in rendered

    def test_render_with_working_dir(self):
        """Render step with working directory."""
        script = SetupScript(
            name="setup",
            description="Subdir setup",
            steps=(
                SetupStep(
                    name="build-frontend",
                    command="npm run build",
                    working_dir="frontend",
                ),
            ),
        )
        rendered = script.render("bash")
        assert "(cd frontend && npm run build)" in rendered


# ---------------------------------------------------------------------------
# SetupScriptBuilder
# ---------------------------------------------------------------------------


class TestSetupScriptBuilder:
    def test_build_python_script(self):
        """Build setup script for Python project."""
        builder = SetupScriptBuilder()
        pt = ProjectType(language=ProjectLanguage.PYTHON)
        script = builder.build(pt)

        assert script.name == "python-setup"
        step_names = [s.name for s in script.steps]
        assert "create-venv" in step_names
        assert "install-deps" in step_names

    def test_build_rust_script(self):
        """Build setup script for Rust project."""
        builder = SetupScriptBuilder()
        pt = ProjectType(language=ProjectLanguage.RUST)
        script = builder.build(pt)

        assert script.name == "rust-setup"
        step_names = [s.name for s in script.steps]
        assert "build" in step_names
        assert "test" in step_names

    def test_build_go_script(self):
        """Build setup script for Go project."""
        builder = SetupScriptBuilder()
        pt = ProjectType(language=ProjectLanguage.GO)
        script = builder.build(pt)

        step_names = [s.name for s in script.steps]
        assert "download-deps" in step_names
        assert "build" in step_names

    def test_build_node_script(self):
        """Build setup script for JavaScript project."""
        builder = SetupScriptBuilder()
        pt = ProjectType(language=ProjectLanguage.JAVASCRIPT)
        script = builder.build(pt)

        step_names = [s.name for s in script.steps]
        assert "install-deps" in step_names

    def test_build_unknown_language(self):
        """Unknown language produces empty steps."""
        builder = SetupScriptBuilder()
        pt = ProjectType(language=ProjectLanguage.UNKNOWN)
        script = builder.build(pt)
        assert script.step_count == 0

    def test_build_with_poetry_framework(self):
        """Poetry framework adds poetry-install step."""
        builder = SetupScriptBuilder()
        pt = ProjectType(
            language=ProjectLanguage.PYTHON,
            framework=ProjectFramework.POETRY,
        )
        script = builder.build(pt)
        step_names = [s.name for s in script.steps]
        assert "poetry-install" in step_names

    def test_build_with_cmake_framework(self):
        """CMake framework adds configure and build steps."""
        builder = SetupScriptBuilder()
        pt = ProjectType(
            language=ProjectLanguage.CPP,
            framework=ProjectFramework.CMAKE,
        )
        script = builder.build(pt)
        step_names = [s.name for s in script.steps]
        assert "cmake-configure" in step_names
        assert "cmake-build" in step_names

    def test_build_with_django_framework(self):
        """Django framework adds migrate step."""
        builder = SetupScriptBuilder()
        pt = ProjectType(
            language=ProjectLanguage.PYTHON,
            framework=ProjectFramework.DJANGO,
        )
        script = builder.build(pt)
        step_names = [s.name for s in script.steps]
        assert "migrate" in step_names

    def test_build_with_platform_apt(self):
        """Platform-aware build includes system deps for apt."""
        builder = SetupScriptBuilder()
        pt = ProjectType(language=ProjectLanguage.PYTHON)
        script = builder.build_with_platform(pt, os_name="Linux", pkg_manager="apt")

        step_names = [s.name for s in script.steps]
        assert "install-system-deps" in step_names
        # The system deps step should use apt
        sys_step = next(s for s in script.steps if s.name == "install-system-deps")
        assert "apt-get install" in sys_step.command

    def test_build_with_platform_brew(self):
        """Platform-aware build for macOS/brew with C++ project."""
        builder = SetupScriptBuilder()
        pt = ProjectType(
            language=ProjectLanguage.CPP,
            framework=ProjectFramework.CMAKE,
        )
        script = builder.build_with_platform(pt, os_name="Darwin", pkg_manager="brew")

        step_names = [s.name for s in script.steps]
        assert "install-system-deps" in step_names
        sys_step = next(s for s in script.steps if s.name == "install-system-deps")
        assert "brew install" in sys_step.command

    def test_build_with_platform_no_pkg_manager(self):
        """Platform-aware build without pkg manager skips system deps."""
        builder = SetupScriptBuilder()
        pt = ProjectType(language=ProjectLanguage.PYTHON)
        script = builder.build_with_platform(pt, os_name="Linux", pkg_manager=None)

        step_names = [s.name for s in script.steps]
        assert "install-system-deps" not in step_names


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


class TestEnums:
    def test_project_language_values(self):
        """ProjectLanguage has expected members."""
        assert ProjectLanguage.PYTHON.value == "python"
        assert ProjectLanguage.RUST.value == "rust"
        assert ProjectLanguage.GO.value == "go"
        assert ProjectLanguage.UNKNOWN.value == "unknown"

    def test_project_framework_values(self):
        """ProjectFramework has expected members."""
        assert ProjectFramework.DJANGO.value == "django"
        assert ProjectFramework.REACT.value == "react"
        assert ProjectFramework.CARGO.value == "cargo"
        assert ProjectFramework.CMAKE.value == "cmake"
        assert ProjectFramework.NONE.value == "none"
