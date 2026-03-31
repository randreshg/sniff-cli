"""Focused tests for project scaffolding support."""

from __future__ import annotations

import json

import pytest

from dekk.detection.scaffold import (
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
def detector() -> ProjectTypeDetector:
    return ProjectTypeDetector()


@pytest.mark.parametrize(
    ("files", "expected_language", "expected_framework"),
    [
        (
            {"pyproject.toml": '[project]\nname = "app"\n'},
            ProjectLanguage.PYTHON,
            ProjectFramework.NONE,
        ),
        (
            {"setup.py": "from setuptools import setup\n"},
            ProjectLanguage.PYTHON,
            ProjectFramework.SETUPTOOLS,
        ),
        ({"Cargo.toml": '[package]\nname = "app"\n'}, ProjectLanguage.RUST, ProjectFramework.CARGO),
        (
            {"package.json": json.dumps({"name": "app"})},
            ProjectLanguage.JAVASCRIPT,
            ProjectFramework.NONE,
        ),
        (
            {"package.json": json.dumps({"name": "app"}), "tsconfig.json": "{}"},
            ProjectLanguage.TYPESCRIPT,
            ProjectFramework.NONE,
        ),
        ({"go.mod": "module example.com/app\n"}, ProjectLanguage.GO, ProjectFramework.GO_MODULE),
        ({"pom.xml": "<project></project>"}, ProjectLanguage.JAVA, ProjectFramework.MAVEN),
        ({"build.gradle": "plugins { id 'java' }"}, ProjectLanguage.JAVA, ProjectFramework.GRADLE),
        (
            {"CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)"},
            ProjectLanguage.CPP,
            ProjectFramework.CMAKE,
        ),
        (
            {"Gemfile": 'source "https://rubygems.org"\n'},
            ProjectLanguage.RUBY,
            ProjectFramework.BUNDLER,
        ),
    ],
)
def test_detector_identifies_primary_language_markers(
    tmp_path, detector, files, expected_language, expected_framework
):
    for relative_path, content in files.items():
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    result = detector.detect(tmp_path)

    assert result.language is expected_language
    assert result.framework is expected_framework


def test_detector_returns_unknown_for_missing_or_empty_directories(tmp_path, detector):
    assert detector.detect(tmp_path).language is ProjectLanguage.UNKNOWN
    assert detector.detect(tmp_path / "missing").language is ProjectLanguage.UNKNOWN


def test_detector_refines_python_and_js_frameworks(tmp_path, detector):
    python_root = tmp_path / "python"
    python_root.mkdir()
    (python_root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        '[project]\nname = "api"\ndependencies = ["fastapi", "uvicorn"]\n',
        encoding="utf-8",
    )
    js_root = tmp_path / "js"
    js_root.mkdir()
    (js_root / "package.json").write_text(
        json.dumps({"name": "web", "dependencies": {"react": "^18.0.0"}}),
        encoding="utf-8",
    )

    python_result = detector.detect(python_root)
    js_result = detector.detect(js_root)

    assert python_result.framework is ProjectFramework.FASTAPI
    assert js_result.framework is ProjectFramework.REACT


def test_detector_captures_project_characteristics(tmp_path, detector):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "app"\n', encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "manage.py").write_text("", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")

    result = detector.detect(tmp_path)

    assert result.has_tests is True
    assert result.has_ci is True
    assert result.has_docs is True
    assert result.is_library is True
    assert result.is_application is True


@pytest.mark.parametrize(
    ("files", "expected_monorepo"),
    [
        ({"Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n'}, True),
        ({"package.json": json.dumps({"name": "root", "workspaces": ["packages/*"]})}, True),
        (
            {
                "package.json": json.dumps({"name": "root"}),
                "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
            },
            True,
        ),
        ({"pyproject.toml": '[project]\nname = "app"\n'}, False),
    ],
)
def test_detector_recognizes_monorepo_markers(tmp_path, detector, files, expected_monorepo):
    for relative_path, content in files.items():
        target = tmp_path / relative_path
        target.write_text(content, encoding="utf-8")

    assert detector.detect(tmp_path).is_monorepo is expected_monorepo


def test_detector_finds_entry_points_across_languages(tmp_path, detector):
    python_root = tmp_path / "python"
    python_root.mkdir()
    (python_root / "pyproject.toml").write_text('[project]\nname = "py"\n', encoding="utf-8")
    (python_root / "main.py").write_text("", encoding="utf-8")
    (python_root / "app.py").write_text("", encoding="utf-8")
    (python_root / "src").mkdir()
    (python_root / "src" / "pkg").mkdir()
    (python_root / "src" / "pkg" / "__main__.py").write_text("", encoding="utf-8")

    go_root = tmp_path / "go"
    go_root.mkdir()
    (go_root / "go.mod").write_text("module example.com/go\n", encoding="utf-8")
    (go_root / "main.go").write_text("package main\n", encoding="utf-8")
    (go_root / "cmd" / "server").mkdir(parents=True)
    (go_root / "cmd" / "server" / "main.go").write_text("package main\n", encoding="utf-8")

    ts_root = tmp_path / "ts"
    ts_root.mkdir()
    (ts_root / "package.json").write_text(json.dumps({"name": "ts"}), encoding="utf-8")
    (ts_root / "tsconfig.json").write_text("{}", encoding="utf-8")
    (ts_root / "src").mkdir()
    (ts_root / "src" / "index.ts").write_text("", encoding="utf-8")

    python_result = detector.detect(python_root)
    go_result = detector.detect(go_root)
    ts_result = detector.detect(ts_root)

    assert python_result.entry_points == ("main.py", "app.py", "src/pkg/__main__.py")
    assert go_result.entry_points == ("main.go", "cmd/server/main.go")
    assert ts_result.entry_points == ("src/index.ts",)


def test_project_type_and_templates_expose_derived_properties():
    project_type = ProjectType(language=ProjectLanguage.PYTHON)
    template = TemplateSet(
        name="python-basic",
        description="Basic Python project",
        language=ProjectLanguage.PYTHON,
        files=(
            FileTemplate(relative_path="setup.py", content="# setup"),
            FileTemplate(relative_path="README.md", content="# README"),
        ),
        tags=("cli", "python"),
    )

    assert project_type.framework is ProjectFramework.NONE
    assert template.file_count == 2
    assert template.paths == ("setup.py", "README.md")
    assert "cli" in template.tags


def test_template_registry_merges_builtin_and_provider_results():
    class RustProvider:
        def get_templates(self, language, framework=ProjectFramework.NONE):
            if language is ProjectLanguage.RUST:
                return [
                    TemplateSet(
                        name="rust-wasm", description="Rust WASM", language=ProjectLanguage.RUST
                    )
                ]
            return []

    registry = TemplateRegistry()
    registry.register_template_set(
        TemplateSet(
            name="python-generic",
            description="Generic Python",
            language=ProjectLanguage.PYTHON,
        )
    )
    registry.register_template_set(
        TemplateSet(
            name="python-django",
            description="Django",
            language=ProjectLanguage.PYTHON,
            framework=ProjectFramework.DJANGO,
            tags=("web",),
        )
    )
    registry.register_provider(RustProvider())

    python_results = registry.find(ProjectLanguage.PYTHON, ProjectFramework.DJANGO)
    rust_results = registry.find(ProjectLanguage.RUST)
    tag_results = registry.find_by_tag("web")

    assert {template.name for template in python_results} == {"python-generic", "python-django"}
    assert [template.name for template in rust_results] == ["rust-wasm"]
    assert [template.name for template in tag_results] == ["python-django"]
    assert len(registry.all_templates) == 2


def test_setup_script_derived_views_and_shell_rendering():
    script = SetupScript(
        name="setup",
        description="Setup project",
        steps=(
            SetupStep(name="install", command="pip install -e ."),
            SetupStep(name="lint", command="ruff check .", optional=True),
            SetupStep(
                name="migrate", command="python manage.py migrate", condition="[ -f manage.py ]"
            ),
            SetupStep(name="frontend", command="npm run build", working_dir="frontend"),
        ),
        env_vars=(("PYTHONDONTWRITEBYTECODE", "1"),),
    )

    bash = script.render("bash")
    fish = script.render("fish")
    powershell = script.render("powershell")

    assert script.step_count == 4
    assert [step.name for step in script.required_steps] == ["install", "migrate", "frontend"]
    assert [step.name for step in script.optional_steps] == ["lint"]
    assert 'export PYTHONDONTWRITEBYTECODE="1"' in bash
    assert "ruff check . || true" in bash
    assert "(cd frontend && npm run build)" in bash
    assert "set -gx PYTHONDONTWRITEBYTECODE 1" in fish
    assert "$ErrorActionPreference = 'Stop'" in powershell
    assert "try { ruff check . } catch { }" in powershell


def test_setup_script_builder_covers_language_framework_and_platform_steps():
    builder = SetupScriptBuilder()

    python_steps = [
        step.name for step in builder.build(ProjectType(language=ProjectLanguage.PYTHON)).steps
    ]
    rust_steps = [
        step.name for step in builder.build(ProjectType(language=ProjectLanguage.RUST)).steps
    ]
    go_steps = [step.name for step in builder.build(ProjectType(language=ProjectLanguage.GO)).steps]
    poetry_steps = [
        step.name
        for step in builder.build(
            ProjectType(language=ProjectLanguage.PYTHON, framework=ProjectFramework.POETRY)
        ).steps
    ]
    django_steps = [
        step.name
        for step in builder.build(
            ProjectType(language=ProjectLanguage.PYTHON, framework=ProjectFramework.DJANGO)
        ).steps
    ]
    cmake_steps = [
        step.name
        for step in builder.build(
            ProjectType(language=ProjectLanguage.CPP, framework=ProjectFramework.CMAKE)
        ).steps
    ]
    platform_script = builder.build_with_platform(
        ProjectType(language=ProjectLanguage.CPP, framework=ProjectFramework.CMAKE),
        os_name="Darwin",
        pkg_manager="brew",
    )

    assert {"create-venv", "install-deps"} <= set(python_steps)
    assert {"build", "test"} <= set(rust_steps)
    assert {"download-deps", "build", "test"} <= set(go_steps)
    assert "poetry-install" in poetry_steps
    assert "migrate" in django_steps
    assert {"cmake-configure", "cmake-build"} <= set(cmake_steps)
    assert platform_script.steps[0].name == "install-system-deps"
    assert "brew install" in platform_script.steps[0].command
