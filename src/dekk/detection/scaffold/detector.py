"""Project type detection -- language, framework, and project characteristics."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Final

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

    def _detect_language_framework(self, root: Path) -> tuple[ProjectLanguage, ProjectFramework]:
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

    def _refine_python_framework(self, root: Path, current: ProjectFramework) -> ProjectFramework:
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

    def _refine_js_framework(self, root: Path, current: ProjectFramework) -> ProjectFramework:
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

    def _detect_entry_points(self, root: Path, language: ProjectLanguage) -> tuple[str, ...]:
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
                                str((pkg / "__main__.py").relative_to(root)).replace("\\", "/")
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
