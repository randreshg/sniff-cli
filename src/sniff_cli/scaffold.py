"""Project scaffolding -- detect project type, provide templates, generate setup scripts.

Composes existing detectors (WorkspaceDetector, PlatformDetector, CIDetector, etc.)
to determine the project type and provide appropriate scaffolding support.

Pure detection for ProjectTypeDetector. Deterministic output for template and
setup script generation -- no subprocess calls, no side effects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, Sequence


DEFAULT_RENDER_SHELL: Final = "bash"
FISH_RENDER_SHELL: Final = "fish"
POWERSHELL_RENDER_SHELL: Final = "powershell"
TEST_DIR_NAMES: Final = ("tests", "test", "spec", "__tests__")
SYSTEM_DEPS_STEP_NAME: Final = "install-system-deps"


# ---------------------------------------------------------------------------
# Project type detection
# ---------------------------------------------------------------------------


class ProjectLanguage(enum.Enum):
    """Primary programming language of a project."""

    PYTHON = "python"
    RUST = "rust"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    JAVA = "java"
    CSHARP = "csharp"
    CPP = "cpp"
    C = "c"
    RUBY = "ruby"
    PHP = "php"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    SCALA = "scala"
    UNKNOWN = "unknown"


class ProjectFramework(enum.Enum):
    """Detected framework or build system."""

    # Python
    DJANGO = "django"
    FLASK = "flask"
    FASTAPI = "fastapi"
    SETUPTOOLS = "setuptools"
    HATCH = "hatch"
    POETRY = "poetry"
    PDM = "pdm"
    FLIT = "flit"
    MATURIN = "maturin"

    # JavaScript/TypeScript
    REACT = "react"
    NEXT = "next"
    VUE = "vue"
    NUXT = "nuxt"
    ANGULAR = "angular"
    SVELTE = "svelte"
    EXPRESS = "express"
    VITE = "vite"

    # Rust
    CARGO = "cargo"
    WASM_PACK = "wasm_pack"

    # Go
    GO_MODULE = "go_module"

    # Java/JVM
    MAVEN = "maven"
    GRADLE = "gradle"
    SBT = "sbt"

    # C/C++
    CMAKE = "cmake"
    MESON = "meson"
    MAKE = "make"
    AUTOTOOLS = "autotools"

    # Ruby
    RAILS = "rails"
    BUNDLER = "bundler"

    # Generic
    NONE = "none"


@dataclass(frozen=True)
class ProjectType:
    """Detected project type combining language, framework, and metadata."""

    language: ProjectLanguage
    framework: ProjectFramework = ProjectFramework.NONE
    is_library: bool = False
    is_application: bool = False
    is_monorepo: bool = False
    has_tests: bool = False
    has_ci: bool = False
    has_docs: bool = False
    entry_points: tuple[str, ...] = ()


class ProjectTypeDetector:
    """Detect the type of project in a directory.

    Scans filesystem markers (config files, directory structure) to determine
    the project's language, framework, and characteristics.

    Pure detection -- no side effects, no subprocess calls.
    """

    # Map config files to (language, framework) pairs
    _CONFIG_MARKERS: list[tuple[str, ProjectLanguage, ProjectFramework]] = [
        # Python
        ("pyproject.toml", ProjectLanguage.PYTHON, ProjectFramework.NONE),
        ("setup.py", ProjectLanguage.PYTHON, ProjectFramework.SETUPTOOLS),
        ("setup.cfg", ProjectLanguage.PYTHON, ProjectFramework.SETUPTOOLS),
        # Rust
        ("Cargo.toml", ProjectLanguage.RUST, ProjectFramework.CARGO),
        # JavaScript/TypeScript
        ("package.json", ProjectLanguage.JAVASCRIPT, ProjectFramework.NONE),
        ("tsconfig.json", ProjectLanguage.TYPESCRIPT, ProjectFramework.NONE),
        # Go
        ("go.mod", ProjectLanguage.GO, ProjectFramework.GO_MODULE),
        # Java
        ("pom.xml", ProjectLanguage.JAVA, ProjectFramework.MAVEN),
        ("build.gradle", ProjectLanguage.JAVA, ProjectFramework.GRADLE),
        ("build.gradle.kts", ProjectLanguage.JAVA, ProjectFramework.GRADLE),
        # C/C++
        ("CMakeLists.txt", ProjectLanguage.CPP, ProjectFramework.CMAKE),
        ("meson.build", ProjectLanguage.CPP, ProjectFramework.MESON),
        ("Makefile", ProjectLanguage.C, ProjectFramework.MAKE),
        ("configure.ac", ProjectLanguage.C, ProjectFramework.AUTOTOOLS),
        # Ruby
        ("Gemfile", ProjectLanguage.RUBY, ProjectFramework.BUNDLER),
        # C#
        ("*.csproj", ProjectLanguage.CSHARP, ProjectFramework.NONE),
        ("*.sln", ProjectLanguage.CSHARP, ProjectFramework.NONE),
        # Scala
        ("build.sbt", ProjectLanguage.SCALA, ProjectFramework.SBT),
    ]

    # Framework-specific markers within package.json dependencies
    _JS_FRAMEWORK_MARKERS: dict[str, ProjectFramework] = {
        "react": ProjectFramework.REACT,
        "next": ProjectFramework.NEXT,
        "vue": ProjectFramework.VUE,
        "nuxt": ProjectFramework.NUXT,
        "@angular/core": ProjectFramework.ANGULAR,
        "svelte": ProjectFramework.SVELTE,
        "express": ProjectFramework.EXPRESS,
        "vite": ProjectFramework.VITE,
    }

    # Python framework markers in dependencies
    _PY_FRAMEWORK_MARKERS: dict[str, ProjectFramework] = {
        "django": ProjectFramework.DJANGO,
        "flask": ProjectFramework.FLASK,
        "fastapi": ProjectFramework.FASTAPI,
    }

    # Python build backend markers
    _PY_BUILD_BACKENDS: dict[str, ProjectFramework] = {
        "hatchling": ProjectFramework.HATCH,
        "poetry": ProjectFramework.POETRY,
        "pdm": ProjectFramework.PDM,
        "flit": ProjectFramework.FLIT,
        "maturin": ProjectFramework.MATURIN,
        "setuptools": ProjectFramework.SETUPTOOLS,
    }

    def detect(self, root: Path | None = None) -> ProjectType:
        """Detect project type at the given root.

        Args:
            root: Directory to scan. Defaults to cwd.

        Returns:
            ProjectType with detected characteristics. Never raises.
        """
        root = (root or Path.cwd()).resolve()
        try:
            if not root.is_dir():
                return ProjectType(language=ProjectLanguage.UNKNOWN)
        except (OSError, PermissionError):
            return ProjectType(language=ProjectLanguage.UNKNOWN)

        language, framework = self._detect_language_framework(root)
        is_library = self._detect_is_library(root, language)
        is_application = self._detect_is_application(root, language)
        is_monorepo = self._detect_is_monorepo(root)
        has_tests = self._detect_has_tests(root)
        has_ci = self._detect_has_ci(root)
        has_docs = self._detect_has_docs(root)
        entry_points = self._detect_entry_points(root, language)

        return ProjectType(
            language=language,
            framework=framework,
            is_library=is_library,
            is_application=is_application,
            is_monorepo=is_monorepo,
            has_tests=has_tests,
            has_ci=has_ci,
            has_docs=has_docs,
            entry_points=entry_points,
        )

    def _detect_language_framework(
        self, root: Path
    ) -> tuple[ProjectLanguage, ProjectFramework]:
        """Detect primary language and framework from config files."""
        language = ProjectLanguage.UNKNOWN
        framework = ProjectFramework.NONE

        for marker_file, lang, fw in self._CONFIG_MARKERS:
            if "*" in marker_file:
                # Glob pattern
                try:
                    if any(root.glob(marker_file)):
                        language = lang
                        framework = fw
                        break
                except (OSError, ValueError):
                    continue
            elif (root / marker_file).exists():
                language = lang
                framework = fw
                break

        # Refine framework detection for Python
        if language == ProjectLanguage.PYTHON:
            framework = self._refine_python_framework(root, framework)

        # Refine framework detection for JS/TS
        if language in (ProjectLanguage.JAVASCRIPT, ProjectLanguage.TYPESCRIPT):
            framework = self._refine_js_framework(root, framework)

        # If tsconfig.json exists alongside package.json, upgrade to TypeScript
        if language == ProjectLanguage.JAVASCRIPT and (root / "tsconfig.json").exists():
            language = ProjectLanguage.TYPESCRIPT

        return language, framework

    def _refine_python_framework(
        self, root: Path, current: ProjectFramework
    ) -> ProjectFramework:
        """Refine Python framework from pyproject.toml contents."""
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return current

        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return current

        # Check build backend
        for backend_key, fw in self._PY_BUILD_BACKENDS.items():
            if backend_key in text:
                current = fw
                break

        # Check for web framework dependencies (higher priority)
        for dep_name, fw in self._PY_FRAMEWORK_MARKERS.items():
            if dep_name in text:
                return fw

        return current

    def _refine_js_framework(
        self, root: Path, current: ProjectFramework
    ) -> ProjectFramework:
        """Refine JS/TS framework from package.json dependencies."""
        import json

        pkg_json = root / "package.json"
        if not pkg_json.exists():
            return current

        try:
            with open(pkg_json, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, json.JSONDecodeError):
            return current

        all_deps: set[str] = set()
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            all_deps.update(data.get(section, {}).keys())

        for dep_name, fw in self._JS_FRAMEWORK_MARKERS.items():
            if dep_name in all_deps:
                return fw

        return current

    def _detect_is_library(self, root: Path, language: ProjectLanguage) -> bool:
        """Heuristic: is this project a library?"""
        if language == ProjectLanguage.PYTHON:
            # Has src/ layout or a top-level package but no obvious app entry point
            return (root / "src").is_dir() or (root / "setup.py").exists()
        if language == ProjectLanguage.RUST:
            return (root / "src" / "lib.rs").exists()
        if language in (ProjectLanguage.JAVASCRIPT, ProjectLanguage.TYPESCRIPT):
            pkg_json = root / "package.json"
            if pkg_json.exists():
                try:
                    import json
                    with open(pkg_json, encoding="utf-8") as f:
                        data = json.load(f)
                    return "main" in data or "exports" in data
                except (OSError, ValueError):
                    pass
        return False

    def _detect_is_application(self, root: Path, language: ProjectLanguage) -> bool:
        """Heuristic: is this project an application?"""
        if language == ProjectLanguage.PYTHON:
            return (root / "manage.py").exists() or (root / "app.py").exists()
        if language == ProjectLanguage.RUST:
            return (root / "src" / "main.rs").exists()
        if language in (ProjectLanguage.JAVASCRIPT, ProjectLanguage.TYPESCRIPT):
            pkg_json = root / "package.json"
            if pkg_json.exists():
                try:
                    import json
                    with open(pkg_json, encoding="utf-8") as f:
                        data = json.load(f)
                    scripts = data.get("scripts", {})
                    return "start" in scripts or "dev" in scripts
                except (OSError, ValueError):
                    pass
        return False

    def _detect_is_monorepo(self, root: Path) -> bool:
        """Check for monorepo indicators."""
        monorepo_markers = [
            "pnpm-workspace.yaml",
            "lerna.json",
            "nx.json",
            "turbo.json",
            "go.work",
        ]
        for marker in monorepo_markers:
            if (root / marker).exists():
                return True

        # Check Cargo workspace
        cargo_toml = root / "Cargo.toml"
        if cargo_toml.exists():
            try:
                text = cargo_toml.read_text(encoding="utf-8")
                if "[workspace]" in text:
                    return True
            except OSError:
                pass

        # Check package.json workspaces
        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                import json
                with open(pkg_json, encoding="utf-8") as f:
                    data = json.load(f)
                if "workspaces" in data:
                    return True
            except (OSError, ValueError):
                pass

        return False

    def _detect_has_tests(self, root: Path) -> bool:
        """Check for test directories or files."""
        for d in TEST_DIR_NAMES:
            if (root / d).is_dir():
                return True
        # Rust convention
        if (root / "src" / "lib.rs").exists():
            try:
                text = (root / "src" / "lib.rs").read_text(encoding="utf-8")
                if "#[cfg(test)]" in text:
                    return True
            except OSError:
                pass
        return False

    def _detect_has_ci(self, root: Path) -> bool:
        """Check for CI configuration files."""
        ci_markers = [
            ".github/workflows",
            ".gitlab-ci.yml",
            "Jenkinsfile",
            ".circleci",
            ".travis.yml",
            "azure-pipelines.yml",
            "bitbucket-pipelines.yml",
        ]
        for marker in ci_markers:
            p = root / marker
            if p.exists():
                return True
        return False

    def _detect_has_docs(self, root: Path) -> bool:
        """Check for documentation directories."""
        doc_dirs = ["docs", "doc", "documentation"]
        for d in doc_dirs:
            if (root / d).is_dir():
                return True
        return False

    def _detect_entry_points(
        self, root: Path, language: ProjectLanguage
    ) -> tuple[str, ...]:
        """Detect common entry point files."""
        candidates: list[str] = []

        if language == ProjectLanguage.PYTHON:
            for name in ("main.py", "app.py", "manage.py", "cli.py", "__main__.py"):
                if (root / name).exists():
                    candidates.append(name)
                # Also check src/<pkg>/__main__.py
            src = root / "src"
            if src.is_dir():
                try:
                    for pkg in src.iterdir():
                        if pkg.is_dir() and (pkg / "__main__.py").exists():
                            candidates.append(
                                str((pkg / "__main__.py").relative_to(root))
                            )
                except OSError:
                    pass

        elif language == ProjectLanguage.RUST:
            if (root / "src" / "main.rs").exists():
                candidates.append("src/main.rs")

        elif language == ProjectLanguage.GO:
            if (root / "main.go").exists():
                candidates.append("main.go")
            cmd_dir = root / "cmd"
            if cmd_dir.is_dir():
                try:
                    for child in sorted(cmd_dir.iterdir()):
                        if child.is_dir() and (child / "main.go").exists():
                            candidates.append(f"cmd/{child.name}/main.go")
                except OSError:
                    pass

        elif language in (ProjectLanguage.JAVASCRIPT, ProjectLanguage.TYPESCRIPT):
            ext = "ts" if language == ProjectLanguage.TYPESCRIPT else "js"
            for name in (f"index.{ext}", f"src/index.{ext}", f"src/main.{ext}", f"app.{ext}"):
                if (root / name).exists():
                    candidates.append(name)

        return tuple(candidates)


# ---------------------------------------------------------------------------
# File templates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileTemplate:
    """A template for a single file to scaffold."""

    relative_path: str
    content: str
    executable: bool = False
    description: str = ""


@dataclass(frozen=True)
class TemplateSet:
    """A named collection of file templates."""

    name: str
    description: str
    language: ProjectLanguage
    framework: ProjectFramework = ProjectFramework.NONE
    files: tuple[FileTemplate, ...] = ()
    tags: tuple[str, ...] = ()

    @property
    def file_count(self) -> int:
        """Number of files in this template set."""
        return len(self.files)

    @property
    def paths(self) -> tuple[str, ...]:
        """Relative paths of all files."""
        return tuple(f.relative_path for f in self.files)


class TemplateProvider(Protocol):
    """Protocol for objects that provide template sets."""

    def get_templates(
        self,
        language: ProjectLanguage,
        framework: ProjectFramework = ProjectFramework.NONE,
    ) -> list[TemplateSet]:
        """Return template sets matching the given language/framework."""
        ...


class TemplateRegistry:
    """Registry of template providers.

    Collects TemplateProvider implementations and queries them for
    templates matching a project type.
    """

    def __init__(self) -> None:
        self._providers: list[TemplateProvider] = []
        self._builtin_templates: list[TemplateSet] = []

    def register_provider(self, provider: TemplateProvider) -> None:
        """Register a template provider."""
        self._providers.append(provider)

    def register_template_set(self, template_set: TemplateSet) -> None:
        """Register a standalone template set."""
        self._builtin_templates.append(template_set)

    def find(
        self,
        language: ProjectLanguage,
        framework: ProjectFramework = ProjectFramework.NONE,
    ) -> list[TemplateSet]:
        """Find all template sets matching the given criteria.

        Args:
            language: Target language.
            framework: Target framework (optional).

        Returns:
            List of matching TemplateSet objects.
        """
        results: list[TemplateSet] = []

        # Query providers
        for provider in self._providers:
            try:
                results.extend(provider.get_templates(language, framework))
            except Exception:
                continue

        # Check builtin templates
        for ts in self._builtin_templates:
            if ts.language == language:
                if framework == ProjectFramework.NONE or ts.framework in (
                    framework,
                    ProjectFramework.NONE,
                ):
                    results.append(ts)

        return results

    def find_by_tag(self, tag: str) -> list[TemplateSet]:
        """Find template sets by tag.

        Args:
            tag: Tag to search for.

        Returns:
            List of matching TemplateSet objects.
        """
        results: list[TemplateSet] = []

        for ts in self._builtin_templates:
            if tag in ts.tags:
                results.append(ts)

        return results

    @property
    def all_templates(self) -> list[TemplateSet]:
        """Return all registered template sets."""
        return list(self._builtin_templates)


# ---------------------------------------------------------------------------
# Setup script generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SetupStep:
    """A single step in a setup script."""

    name: str
    command: str
    description: str = ""
    condition: str | None = None  # Shell condition to check before running
    optional: bool = False
    working_dir: str | None = None  # Relative working directory


@dataclass(frozen=True)
class SetupScript:
    """A complete setup script composed of ordered steps."""

    name: str
    description: str
    steps: tuple[SetupStep, ...] = ()
    env_vars: tuple[tuple[str, str], ...] = ()  # (name, value) pairs

    @property
    def step_count(self) -> int:
        """Number of steps in this script."""
        return len(self.steps)

    @property
    def required_steps(self) -> tuple[SetupStep, ...]:
        """Steps that are not optional."""
        return tuple(s for s in self.steps if not s.optional)

    @property
    def optional_steps(self) -> tuple[SetupStep, ...]:
        """Steps that are optional."""
        return tuple(s for s in self.steps if s.optional)

    def render(self, shell: str = DEFAULT_RENDER_SHELL) -> str:
        """Render the setup script as shell commands.

        Args:
            shell: Target shell (``bash``, ``fish``, ``powershell``).

        Returns:
            Script text.
        """
        if shell == POWERSHELL_RENDER_SHELL:
            return self._render_powershell()
        if shell == FISH_RENDER_SHELL:
            return self._render_fish()
        return self._render_posix()

    def _render_posix(self) -> str:
        lines = [
            "#!/usr/bin/env bash",
            f"# {self.name}: {self.description}",
            "set -euo pipefail",
            "",
        ]

        for name, value in self.env_vars:
            lines.append(f'export {name}="{value}"')
        if self.env_vars:
            lines.append("")

        for step in self.steps:
            lines.append(f"# Step: {step.name}")
            if step.description:
                lines.append(f"# {step.description}")

            cmd = step.command
            if step.working_dir:
                cmd = f"(cd {step.working_dir} && {cmd})"

            if step.condition:
                lines.append(f"if {step.condition}; then")
                lines.append(f"    {cmd}")
                lines.append("fi")
            elif step.optional:
                lines.append(f"{cmd} || true")
            else:
                lines.append(cmd)
            lines.append("")

        return "\n".join(lines)

    def _render_fish(self) -> str:
        lines = [
            "#!/usr/bin/env fish",
            f"# {self.name}: {self.description}",
            "",
        ]

        for name, value in self.env_vars:
            lines.append(f"set -gx {name} {value}")
        if self.env_vars:
            lines.append("")

        for step in self.steps:
            lines.append(f"# Step: {step.name}")
            cmd = step.command
            if step.working_dir:
                cmd = f"pushd {step.working_dir}; and {cmd}; and popd"

            if step.condition:
                lines.append(f"if {step.condition}")
                lines.append(f"    {cmd}")
                lines.append("end")
            elif step.optional:
                lines.append(f"{cmd}; or true")
            else:
                lines.append(cmd)
            lines.append("")

        return "\n".join(lines)

    def _render_powershell(self) -> str:
        lines = [
            f"# {self.name}: {self.description}",
            "$ErrorActionPreference = 'Stop'",
            "",
        ]

        for name, value in self.env_vars:
            lines.append(f'$env:{name} = "{value}"')
        if self.env_vars:
            lines.append("")

        for step in self.steps:
            lines.append(f"# Step: {step.name}")
            cmd = step.command
            if step.working_dir:
                cmd = f"Push-Location {step.working_dir}; {cmd}; Pop-Location"

            if step.condition:
                lines.append(f"if ({step.condition}) {{ {cmd} }}")
            elif step.optional:
                lines.append(f"try {{ {cmd} }} catch {{ }}")
            else:
                lines.append(cmd)
            lines.append("")

        return "\n".join(lines)


class SetupScriptBuilder:
    """Build setup scripts for detected project types.

    Composes detection results from ProjectTypeDetector, PlatformDetector,
    and WorkspaceDetector to generate appropriate setup commands.
    """

    # Language-specific setup steps
    _PYTHON_STEPS: list[tuple[str, str, str]] = [
        ("create-venv", "python -m venv .venv", "Create virtual environment"),
        ("activate-venv", "source .venv/bin/activate", "Activate virtual environment"),
        ("install-deps", "pip install -e '.[dev]'", "Install dependencies in dev mode"),
    ]

    _RUST_STEPS: list[tuple[str, str, str]] = [
        ("check-toolchain", "rustup show", "Verify Rust toolchain"),
        ("build", "cargo build", "Build the project"),
        ("test", "cargo test", "Run tests"),
    ]

    _NODE_STEPS: list[tuple[str, str, str]] = [
        ("install-deps", "npm install", "Install dependencies"),
    ]

    _GO_STEPS: list[tuple[str, str, str]] = [
        ("download-deps", "go mod download", "Download Go module dependencies"),
        ("build", "go build ./...", "Build the project"),
        ("test", "go test ./...", "Run tests"),
    ]

    def build(self, project_type: ProjectType) -> SetupScript:
        """Build a setup script for the given project type.

        Args:
            project_type: Detected project type.

        Returns:
            SetupScript with appropriate steps.
        """
        steps = self._steps_for_language(project_type)
        steps.extend(self._steps_for_framework(project_type))

        return SetupScript(
            name=f"{project_type.language.value}-setup",
            description=f"Setup script for {project_type.language.value} project",
            steps=tuple(steps),
        )

    def build_with_platform(
        self,
        project_type: ProjectType,
        os_name: str = "Linux",
        pkg_manager: str | None = None,
    ) -> SetupScript:
        """Build a platform-aware setup script.

        Args:
            project_type: Detected project type.
            os_name: Operating system name.
            pkg_manager: System package manager (e.g., "apt", "brew").

        Returns:
            SetupScript with platform-specific steps.
        """
        steps: list[SetupStep] = []

        # Add system dependency installation if package manager is known
        sys_deps = self._system_deps_for(project_type, pkg_manager)
        if sys_deps and pkg_manager:
            install_cmd = self._pkg_install_command(pkg_manager, sys_deps)
            if install_cmd:
                steps.append(SetupStep(
                    name=SYSTEM_DEPS_STEP_NAME,
                    command=install_cmd,
                    description="Install system-level dependencies",
                    optional=True,
                ))

        # Add language-specific steps
        steps.extend(self._steps_for_language(project_type))
        steps.extend(self._steps_for_framework(project_type))

        return SetupScript(
            name=f"{project_type.language.value}-setup",
            description=(
                f"Setup script for {project_type.language.value} project "
                f"on {os_name}"
            ),
            steps=tuple(steps),
        )

    def _steps_for_language(self, project_type: ProjectType) -> list[SetupStep]:
        """Generate setup steps based on primary language."""
        step_map: dict[ProjectLanguage, list[tuple[str, str, str]]] = {
            ProjectLanguage.PYTHON: self._PYTHON_STEPS,
            ProjectLanguage.RUST: self._RUST_STEPS,
            ProjectLanguage.JAVASCRIPT: self._NODE_STEPS,
            ProjectLanguage.TYPESCRIPT: self._NODE_STEPS,
            ProjectLanguage.GO: self._GO_STEPS,
        }

        raw_steps = step_map.get(project_type.language, [])
        return [
            SetupStep(name=name, command=cmd, description=desc)
            for name, cmd, desc in raw_steps
        ]

    def _steps_for_framework(self, project_type: ProjectType) -> list[SetupStep]:
        """Add framework-specific setup steps."""
        steps: list[SetupStep] = []

        if project_type.framework == ProjectFramework.POETRY:
            # Replace pip install with poetry install
            steps.append(SetupStep(
                name="poetry-install",
                command="poetry install",
                description="Install dependencies via Poetry",
            ))

        elif project_type.framework == ProjectFramework.PDM:
            steps.append(SetupStep(
                name="pdm-install",
                command="pdm install",
                description="Install dependencies via PDM",
            ))

        elif project_type.framework == ProjectFramework.HATCH:
            steps.append(SetupStep(
                name="hatch-env",
                command="hatch env create",
                description="Create Hatch environment",
            ))

        elif project_type.framework == ProjectFramework.NEXT:
            steps.append(SetupStep(
                name="next-build",
                command="npm run build",
                description="Build Next.js application",
                optional=True,
            ))

        elif project_type.framework == ProjectFramework.DJANGO:
            steps.append(SetupStep(
                name="migrate",
                command="python manage.py migrate",
                description="Run Django database migrations",
                optional=True,
            ))

        elif project_type.framework == ProjectFramework.CMAKE:
            steps.append(SetupStep(
                name="cmake-configure",
                command="cmake -B build -S .",
                description="Configure CMake build",
            ))
            steps.append(SetupStep(
                name="cmake-build",
                command="cmake --build build",
                description="Build with CMake",
            ))

        return steps

    def _system_deps_for(
        self, project_type: ProjectType, pkg_manager: str | None
    ) -> list[str]:
        """Determine system dependencies needed for the project."""
        deps: list[str] = []

        if project_type.language == ProjectLanguage.PYTHON:
            if pkg_manager == "apt":
                deps.extend(["python3-dev", "python3-venv"])
            elif pkg_manager == "dnf":
                deps.extend(["python3-devel"])

        elif project_type.language == ProjectLanguage.CPP:
            if pkg_manager == "apt":
                deps.extend(["build-essential", "cmake"])
            elif pkg_manager == "dnf":
                deps.extend(["gcc-c++", "cmake"])
            elif pkg_manager == "brew":
                deps.append("cmake")

        return deps

    def _pkg_install_command(
        self, pkg_manager: str, packages: list[str]
    ) -> str | None:
        """Generate a package install command."""
        if not packages:
            return None

        pkg_list = " ".join(packages)

        commands = {
            "apt": f"sudo apt-get install -y {pkg_list}",
            "dnf": f"sudo dnf install -y {pkg_list}",
            "pacman": f"sudo pacman -S --noconfirm {pkg_list}",
            "brew": f"brew install {pkg_list}",
            "apk": f"apk add {pkg_list}",
        }

        return commands.get(pkg_manager)
