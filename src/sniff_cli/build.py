"""Build system detection -- identify project build tools and targets.

Detects build systems across ecosystems:
- Cargo (Rust)
- CMake, Make, Meson, Ninja (C/C++)
- Bazel, Buck2 (polyglot)
- npm, pnpm, yarn, bun (Node.js)
- Poetry, PDM, Hatch, Flit, Setuptools, Maturin, uv (Python)
- Go (go.mod)
- Maven, Gradle (Java/JVM)
- Mix (Elixir)
- Stack, Cabal (Haskell)
- Zig (Zig)
- Dune (OCaml)

Pure detection -- no side effects, no subprocesses. Reads files only.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from pathlib import Path

from sniff_cli._compat import load_toml, load_json


class BuildSystem(enum.Enum):
    """Known build systems."""

    CARGO = "cargo"
    CMAKE = "cmake"
    MAKE = "make"
    MESON = "meson"
    NINJA = "ninja"
    BAZEL = "bazel"
    BUCK2 = "buck2"
    NPM = "npm"
    PNPM = "pnpm"
    YARN = "yarn"
    BUN = "bun"
    POETRY = "poetry"
    PDM = "pdm"
    HATCH = "hatch"
    FLIT = "flit"
    SETUPTOOLS = "setuptools"
    MATURIN = "maturin"
    UV = "uv"
    GO = "go"
    MAVEN = "maven"
    GRADLE = "gradle"
    MIX = "mix"
    STACK = "stack"
    CABAL = "cabal"
    ZIG = "zig"
    DUNE = "dune"


@dataclass(frozen=True)
class BuildTarget:
    """A build target or entry point within a project."""

    name: str
    kind: str  # "binary", "library", "test", "bench", "example", "script"
    path: Path | None = None  # source file or directory for this target


@dataclass(frozen=True)
class BuildSystemInfo:
    """Detected build system configuration."""

    system: BuildSystem
    root: Path
    config_file: Path
    version: str | None = None  # build tool version constraint if specified
    targets: tuple[BuildTarget, ...] = ()
    is_workspace: bool = False  # whether this is a workspace/monorepo root

    @property
    def target_count(self) -> int:
        return len(self.targets)

    @property
    def target_names(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.targets)

    def targets_of_kind(self, kind: str) -> tuple[BuildTarget, ...]:
        return tuple(t for t in self.targets if t.kind == kind)


class BuildSystemDetector:
    """Detect build systems in a project directory.

    Scans a directory for build system configuration files and extracts
    target/entry-point information where available.

    Pure detection -- no side effects, no subprocess calls.
    """

    def detect(self, root: Path | None = None) -> list[BuildSystemInfo]:
        """Detect all build systems at the given root.

        A single project can use multiple build systems (e.g., Cargo + CMake
        for a Rust project with C bindings).

        Args:
            root: Directory to scan. Defaults to cwd.

        Returns:
            List of BuildSystemInfo for each detected build system. Never raises.
        """
        root = (root or Path.cwd()).resolve()
        try:
            if not root.is_dir():
                return []
        except (OSError, PermissionError):
            return []

        results: list[BuildSystemInfo] = []

        detectors = [
            self._detect_cargo,
            self._detect_cmake,
            self._detect_make,
            self._detect_meson,
            self._detect_ninja,
            self._detect_bazel,
            self._detect_buck2,
            self._detect_npm,
            self._detect_pnpm,
            self._detect_yarn,
            self._detect_bun,
            self._detect_poetry,
            self._detect_pdm,
            self._detect_hatch,
            self._detect_flit,
            self._detect_setuptools,
            self._detect_maturin,
            self._detect_uv,
            self._detect_go,
            self._detect_maven,
            self._detect_gradle,
            self._detect_mix,
            self._detect_stack,
            self._detect_cabal,
            self._detect_zig,
            self._detect_dune,
        ]

        for detector in detectors:
            try:
                info = detector(root)
                if info is not None:
                    results.append(info)
            except Exception:
                continue

        return results

    def detect_first(self, root: Path | None = None) -> BuildSystemInfo | None:
        """Detect the primary build system.

        Returns:
            First detected BuildSystemInfo, or None.
        """
        results = self.detect(root)
        return results[0] if results else None

    # --- Rust (Cargo) ---

    def _detect_cargo(self, root: Path) -> BuildSystemInfo | None:
        cargo_toml = root / "Cargo.toml"
        if not cargo_toml.exists():
            return None

        data = load_toml(cargo_toml)
        if not data:
            return None

        is_workspace = "workspace" in data
        pkg = data.get("package", {})
        version = pkg.get("edition")

        targets: list[BuildTarget] = []

        # Extract [[bin]] targets
        for bin_entry in data.get("bin", []):
            name = bin_entry.get("name", pkg.get("name", ""))
            path = bin_entry.get("path")
            targets.append(BuildTarget(
                name=name,
                kind="binary",
                path=root / path if path else None,
            ))

        # Extract [[lib]] target
        lib = data.get("lib")
        if isinstance(lib, dict):
            name = lib.get("name", pkg.get("name", ""))
            path = lib.get("path")
            targets.append(BuildTarget(
                name=name,
                kind="library",
                path=root / path if path else None,
            ))

        # Extract [[bench]] targets
        for bench in data.get("bench", []):
            name = bench.get("name", "")
            path = bench.get("path")
            targets.append(BuildTarget(
                name=name,
                kind="bench",
                path=root / path if path else None,
            ))

        # Extract [[example]] targets
        for example in data.get("example", []):
            name = example.get("name", "")
            path = example.get("path")
            targets.append(BuildTarget(
                name=name,
                kind="example",
                path=root / path if path else None,
            ))

        # Default targets from conventional paths
        if not targets:
            if (root / "src" / "main.rs").exists():
                targets.append(BuildTarget(
                    name=pkg.get("name", root.name),
                    kind="binary",
                    path=root / "src" / "main.rs",
                ))
            if (root / "src" / "lib.rs").exists():
                targets.append(BuildTarget(
                    name=pkg.get("name", root.name),
                    kind="library",
                    path=root / "src" / "lib.rs",
                ))

        return BuildSystemInfo(
            system=BuildSystem.CARGO,
            root=root,
            config_file=cargo_toml,
            version=version,
            targets=tuple(targets),
            is_workspace=is_workspace,
        )

    # --- CMake ---

    def _detect_cmake(self, root: Path) -> BuildSystemInfo | None:
        cmake_lists = root / "CMakeLists.txt"
        if not cmake_lists.exists():
            return None

        targets: list[BuildTarget] = []
        version: str | None = None

        try:
            text = cmake_lists.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

        # Extract cmake_minimum_required
        ver_match = re.search(r"cmake_minimum_required\s*\(\s*VERSION\s+([\d.]+)", text, re.I)
        if ver_match:
            version = ver_match.group(1)

        # Extract add_executable targets
        for m in re.finditer(r"add_executable\s*\(\s*(\S+)", text, re.I):
            targets.append(BuildTarget(name=m.group(1), kind="binary"))

        # Extract add_library targets
        for m in re.finditer(r"add_library\s*\(\s*(\S+)", text, re.I):
            targets.append(BuildTarget(name=m.group(1), kind="library"))

        return BuildSystemInfo(
            system=BuildSystem.CMAKE,
            root=root,
            config_file=cmake_lists,
            version=version,
            targets=tuple(targets),
        )

    # --- Make ---

    def _detect_make(self, root: Path) -> BuildSystemInfo | None:
        for name in ("GNUmakefile", "Makefile", "makefile"):
            makefile = root / name
            if makefile.exists():
                targets = self._parse_makefile_targets(makefile)
                return BuildSystemInfo(
                    system=BuildSystem.MAKE,
                    root=root,
                    config_file=makefile,
                    targets=tuple(targets),
                )
        return None

    def _parse_makefile_targets(self, path: Path) -> list[BuildTarget]:
        targets: list[BuildTarget] = []
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return targets

        for m in re.finditer(r"^([a-zA-Z_][\w.-]*):", text, re.MULTILINE):
            name = m.group(1)
            # Skip internal/pattern targets
            if name.startswith(".") or "%" in name:
                continue
            targets.append(BuildTarget(name=name, kind="script"))

        return targets

    # --- Meson ---

    def _detect_meson(self, root: Path) -> BuildSystemInfo | None:
        meson_build = root / "meson.build"
        if not meson_build.exists():
            return None

        targets: list[BuildTarget] = []
        version: str | None = None

        try:
            text = meson_build.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

        # Extract project version
        proj_match = re.search(r"project\s*\([^)]*version\s*:\s*'([^']+)'", text, re.I)
        if proj_match:
            version = proj_match.group(1)

        # Extract executable targets
        for m in re.finditer(r"executable\s*\(\s*'([^']+)'", text):
            targets.append(BuildTarget(name=m.group(1), kind="binary"))

        # Extract library targets (shared_library and static_library first to avoid
        # the plain "library" regex matching them as a substring)
        seen_libs: set[str] = set()
        for func in ("shared_library", "static_library", "library"):
            for m in re.finditer(rf"(?<!\w){func}\s*\(\s*'([^']+)'", text):
                if m.group(1) not in seen_libs:
                    seen_libs.add(m.group(1))
                    targets.append(BuildTarget(name=m.group(1), kind="library"))

        return BuildSystemInfo(
            system=BuildSystem.MESON,
            root=root,
            config_file=meson_build,
            version=version,
            targets=tuple(targets),
        )

    # --- Ninja ---

    def _detect_ninja(self, root: Path) -> BuildSystemInfo | None:
        build_ninja = root / "build.ninja"
        if not build_ninja.exists():
            return None

        return BuildSystemInfo(
            system=BuildSystem.NINJA,
            root=root,
            config_file=build_ninja,
        )

    # --- Bazel ---

    def _detect_bazel(self, root: Path) -> BuildSystemInfo | None:
        for ws_file in ("MODULE.bazel", "WORKSPACE.bazel", "WORKSPACE"):
            ws_path = root / ws_file
            if ws_path.exists():
                return BuildSystemInfo(
                    system=BuildSystem.BAZEL,
                    root=root,
                    config_file=ws_path,
                    is_workspace=True,
                )
        return None

    # --- Buck2 ---

    def _detect_buck2(self, root: Path) -> BuildSystemInfo | None:
        buckconfig = root / ".buckconfig"
        if not buckconfig.exists():
            return None

        return BuildSystemInfo(
            system=BuildSystem.BUCK2,
            root=root,
            config_file=buckconfig,
        )

    # --- npm ---

    def _detect_npm(self, root: Path) -> BuildSystemInfo | None:
        pkg_json = root / "package.json"
        if not pkg_json.exists():
            return None

        # Skip if another JS package manager is primary
        if any((root / f).exists() for f in ("pnpm-workspace.yaml", "pnpm-lock.yaml",
                                               "bun.lockb", "bun.lock")):
            return None
        if (root / ".yarnrc.yml").exists() or (root / "yarn.lock").exists():
            return None

        data = load_json(pkg_json)
        if not data:
            return None

        targets = self._parse_npm_scripts(data)
        is_workspace = "workspaces" in data

        return BuildSystemInfo(
            system=BuildSystem.NPM,
            root=root,
            config_file=pkg_json,
            version=data.get("version"),
            targets=tuple(targets),
            is_workspace=is_workspace,
        )

    # --- pnpm ---

    def _detect_pnpm(self, root: Path) -> BuildSystemInfo | None:
        ws_yaml = root / "pnpm-workspace.yaml"
        pnpm_lock = root / "pnpm-lock.yaml"

        if not ws_yaml.exists() and not pnpm_lock.exists():
            return None

        config_file = ws_yaml if ws_yaml.exists() else pnpm_lock

        targets: list[BuildTarget] = []
        pkg_json = root / "package.json"
        if pkg_json.exists():
            data = load_json(pkg_json)
            if data:
                targets = self._parse_npm_scripts(data)

        return BuildSystemInfo(
            system=BuildSystem.PNPM,
            root=root,
            config_file=config_file,
            targets=tuple(targets),
            is_workspace=ws_yaml.exists(),
        )

    # --- yarn ---

    def _detect_yarn(self, root: Path) -> BuildSystemInfo | None:
        yarnrc = root / ".yarnrc.yml"
        yarn_lock = root / "yarn.lock"

        if not yarnrc.exists() and not yarn_lock.exists():
            return None

        config_file = yarnrc if yarnrc.exists() else yarn_lock
        pkg_json = root / "package.json"

        targets: list[BuildTarget] = []
        is_workspace = False
        if pkg_json.exists():
            data = load_json(pkg_json)
            if data:
                targets = self._parse_npm_scripts(data)
                is_workspace = "workspaces" in data

        return BuildSystemInfo(
            system=BuildSystem.YARN,
            root=root,
            config_file=config_file,
            targets=tuple(targets),
            is_workspace=is_workspace,
        )

    # --- bun ---

    def _detect_bun(self, root: Path) -> BuildSystemInfo | None:
        for lockfile in ("bun.lockb", "bun.lock"):
            if (root / lockfile).exists():
                config_file = root / lockfile
                pkg_json = root / "package.json"

                targets: list[BuildTarget] = []
                is_workspace = False
                if pkg_json.exists():
                    data = load_json(pkg_json)
                    if data:
                        targets = self._parse_npm_scripts(data)
                        is_workspace = "workspaces" in data

                return BuildSystemInfo(
                    system=BuildSystem.BUN,
                    root=root,
                    config_file=config_file,
                    targets=tuple(targets),
                    is_workspace=is_workspace,
                )
        return None

    # --- Node.js shared ---

    def _parse_npm_scripts(self, data: dict) -> list[BuildTarget]:
        targets: list[BuildTarget] = []
        scripts = data.get("scripts", {})
        for name in scripts:
            targets.append(BuildTarget(name=name, kind="script"))
        return targets

    # --- Poetry ---

    def _detect_poetry(self, root: Path) -> BuildSystemInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        poetry = data.get("tool", {}).get("poetry", {})
        if not poetry:
            # Check build-system backend
            backend = data.get("build-system", {}).get("build-backend", "")
            if "poetry" not in backend:
                return None

        targets = self._parse_python_targets(data)

        return BuildSystemInfo(
            system=BuildSystem.POETRY,
            root=root,
            config_file=pyproject,
            version=poetry.get("version") or data.get("project", {}).get("version"),
            targets=tuple(targets),
        )

    # --- PDM ---

    def _detect_pdm(self, root: Path) -> BuildSystemInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        pdm = data.get("tool", {}).get("pdm", {})
        if not pdm:
            backend = data.get("build-system", {}).get("build-backend", "")
            if "pdm" not in backend:
                return None

        targets = self._parse_python_targets(data)

        return BuildSystemInfo(
            system=BuildSystem.PDM,
            root=root,
            config_file=pyproject,
            version=data.get("project", {}).get("version"),
            targets=tuple(targets),
        )

    # --- Hatch ---

    def _detect_hatch(self, root: Path) -> BuildSystemInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        hatch = data.get("tool", {}).get("hatch", {})
        if not hatch:
            backend = data.get("build-system", {}).get("build-backend", "")
            if "hatchling" not in backend:
                return None

        targets = self._parse_python_targets(data)

        return BuildSystemInfo(
            system=BuildSystem.HATCH,
            root=root,
            config_file=pyproject,
            version=data.get("project", {}).get("version"),
            targets=tuple(targets),
        )

    # --- Flit ---

    def _detect_flit(self, root: Path) -> BuildSystemInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        backend = data.get("build-system", {}).get("build-backend", "")
        if "flit" not in backend:
            return None

        targets = self._parse_python_targets(data)

        return BuildSystemInfo(
            system=BuildSystem.FLIT,
            root=root,
            config_file=pyproject,
            version=data.get("project", {}).get("version"),
            targets=tuple(targets),
        )

    # --- Setuptools ---

    def _detect_setuptools(self, root: Path) -> BuildSystemInfo | None:
        setup_py = root / "setup.py"
        setup_cfg = root / "setup.cfg"

        if setup_py.exists():
            return BuildSystemInfo(
                system=BuildSystem.SETUPTOOLS,
                root=root,
                config_file=setup_py,
            )

        if setup_cfg.exists():
            return BuildSystemInfo(
                system=BuildSystem.SETUPTOOLS,
                root=root,
                config_file=setup_cfg,
            )

        # Check pyproject.toml with setuptools backend
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            data = load_toml(pyproject)
            if data:
                backend = data.get("build-system", {}).get("build-backend", "")
                if "setuptools" in backend:
                    targets = self._parse_python_targets(data)
                    return BuildSystemInfo(
                        system=BuildSystem.SETUPTOOLS,
                        root=root,
                        config_file=pyproject,
                        version=data.get("project", {}).get("version"),
                        targets=tuple(targets),
                    )

        return None

    # --- Maturin ---

    def _detect_maturin(self, root: Path) -> BuildSystemInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        # Check for maturin in build-system or tool.maturin
        backend = data.get("build-system", {}).get("build-backend", "")
        has_maturin_tool = "maturin" in data.get("tool", {})

        if "maturin" not in backend and not has_maturin_tool:
            return None

        targets = self._parse_python_targets(data)

        return BuildSystemInfo(
            system=BuildSystem.MATURIN,
            root=root,
            config_file=pyproject,
            version=data.get("project", {}).get("version"),
            targets=tuple(targets),
        )

    # --- uv ---

    def _detect_uv(self, root: Path) -> BuildSystemInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        uv = data.get("tool", {}).get("uv", {})
        if not uv:
            return None

        is_workspace = bool(uv.get("workspace", {}).get("members"))
        targets = self._parse_python_targets(data)

        return BuildSystemInfo(
            system=BuildSystem.UV,
            root=root,
            config_file=pyproject,
            version=data.get("project", {}).get("version"),
            targets=tuple(targets),
            is_workspace=is_workspace,
        )

    # --- Python shared ---

    def _parse_python_targets(self, data: dict) -> list[BuildTarget]:
        targets: list[BuildTarget] = []

        # PEP 621 scripts (console_scripts equivalent)
        scripts = data.get("project", {}).get("scripts", {})
        for name in scripts:
            targets.append(BuildTarget(name=name, kind="script"))

        # PEP 621 gui-scripts
        gui_scripts = data.get("project", {}).get("gui-scripts", {})
        for name in gui_scripts:
            targets.append(BuildTarget(name=name, kind="script"))

        return targets

    # --- Go ---

    def _detect_go(self, root: Path) -> BuildSystemInfo | None:
        go_mod = root / "go.mod"
        if not go_mod.exists():
            return None

        version: str | None = None
        try:
            text = go_mod.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("go "):
                    version = line[3:].strip()
                    break
        except OSError:
            pass

        targets: list[BuildTarget] = []
        # Check for main packages in conventional locations
        cmd_dir = root / "cmd"
        if cmd_dir.is_dir():
            try:
                for child in sorted(cmd_dir.iterdir()):
                    if child.is_dir():
                        targets.append(BuildTarget(
                            name=child.name,
                            kind="binary",
                            path=child,
                        ))
            except OSError:
                pass

        # Check root main.go
        if (root / "main.go").exists():
            targets.append(BuildTarget(
                name=root.name,
                kind="binary",
                path=root / "main.go",
            ))

        is_workspace = (root / "go.work").exists()

        return BuildSystemInfo(
            system=BuildSystem.GO,
            root=root,
            config_file=go_mod,
            version=version,
            targets=tuple(targets),
            is_workspace=is_workspace,
        )

    # --- Maven ---

    def _detect_maven(self, root: Path) -> BuildSystemInfo | None:
        pom_xml = root / "pom.xml"
        if not pom_xml.exists():
            return None

        return BuildSystemInfo(
            system=BuildSystem.MAVEN,
            root=root,
            config_file=pom_xml,
        )

    # --- Gradle ---

    def _detect_gradle(self, root: Path) -> BuildSystemInfo | None:
        for name in ("build.gradle.kts", "build.gradle"):
            gradle_file = root / name
            if gradle_file.exists():
                settings = root / "settings.gradle.kts"
                if not settings.exists():
                    settings = root / "settings.gradle"
                is_workspace = settings.exists()

                return BuildSystemInfo(
                    system=BuildSystem.GRADLE,
                    root=root,
                    config_file=gradle_file,
                    is_workspace=is_workspace,
                )
        return None

    # --- Mix (Elixir) ---

    def _detect_mix(self, root: Path) -> BuildSystemInfo | None:
        mix_exs = root / "mix.exs"
        if not mix_exs.exists():
            return None

        return BuildSystemInfo(
            system=BuildSystem.MIX,
            root=root,
            config_file=mix_exs,
        )

    # --- Stack (Haskell) ---

    def _detect_stack(self, root: Path) -> BuildSystemInfo | None:
        stack_yaml = root / "stack.yaml"
        if not stack_yaml.exists():
            return None

        return BuildSystemInfo(
            system=BuildSystem.STACK,
            root=root,
            config_file=stack_yaml,
        )

    # --- Cabal (Haskell) ---

    def _detect_cabal(self, root: Path) -> BuildSystemInfo | None:
        # Look for *.cabal file
        try:
            cabal_files = sorted(root.glob("*.cabal"))
        except OSError:
            return None

        if not cabal_files:
            return None

        return BuildSystemInfo(
            system=BuildSystem.CABAL,
            root=root,
            config_file=cabal_files[0],
        )

    # --- Zig ---

    def _detect_zig(self, root: Path) -> BuildSystemInfo | None:
        build_zig = root / "build.zig"
        if not build_zig.exists():
            return None

        return BuildSystemInfo(
            system=BuildSystem.ZIG,
            root=root,
            config_file=build_zig,
        )

    # --- Dune (OCaml) ---

    def _detect_dune(self, root: Path) -> BuildSystemInfo | None:
        dune_project = root / "dune-project"
        if not dune_project.exists():
            return None

        return BuildSystemInfo(
            system=BuildSystem.DUNE,
            root=root,
            config_file=dune_project,
        )

    # --- Utility methods kept for subclass compat; delegate to _compat ---
