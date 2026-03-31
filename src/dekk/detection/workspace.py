"""Workspace and monorepo detection.

Detects workspace configurations across ecosystems:
- pnpm/npm/yarn workspaces (Node.js)
- Cargo workspaces (Rust)
- Poetry/PDM/Hatch workspaces (Python)
- Go multi-module workspaces
- Nx, Turborepo, Lerna (meta build tools)
- Bazel, Pants (polyglot build systems)

Pure detection -- no side effects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from dekk._compat import load_json, load_toml


class WorkspaceKind(enum.Enum):
    """Type of workspace/monorepo tool."""

    PNPM = "pnpm"
    NPM = "npm"
    YARN = "yarn"
    CARGO = "cargo"
    POETRY = "poetry"
    PDM = "pdm"
    HATCH = "hatch"
    UV = "uv"
    GO_WORK = "go_work"
    NX = "nx"
    TURBOREPO = "turborepo"
    LERNA = "lerna"
    BAZEL = "bazel"
    PANTS = "pants"


@dataclass(frozen=True)
class SubProject:
    """A project within a workspace."""

    name: str
    path: Path
    kind: str  # e.g., "rust_crate", "npm_package", "python_package"
    version: str | None = None
    dependencies: tuple[str, ...] = ()  # names of other SubProjects this depends on


@dataclass(frozen=True)
class WorkspaceInfo:
    """Detected workspace/monorepo configuration."""

    kind: WorkspaceKind
    root: Path  # workspace root directory
    config_file: Path  # file that defines the workspace
    member_globs: tuple[str, ...] = ()  # raw glob patterns from config
    projects: tuple[SubProject, ...] = ()  # resolved sub-projects
    shared_deps_file: Path | None = None  # workspace-level dependency file

    @property
    def project_count(self) -> int:
        """Number of detected sub-projects."""
        return len(self.projects)

    @property
    def project_names(self) -> tuple[str, ...]:
        """Names of all sub-projects."""
        return tuple(p.name for p in self.projects)

    def dependency_graph(self) -> dict[str, tuple[str, ...]]:
        """Build a name -> dependencies mapping for inter-project deps."""
        project_names = set(self.project_names)
        return {
            p.name: tuple(d for d in p.dependencies if d in project_names) for p in self.projects
        }

    def build_order(self) -> list[str]:
        """Topological sort of projects by internal dependencies.

        Returns project names in an order where dependencies come before
        dependents. Projects with no internal deps come first.

        Returns empty list if a cycle is detected.
        """
        graph = self.dependency_graph()
        all_names = list(self.project_names)

        visited: set[str] = set()
        in_stack: set[str] = set()
        order: list[str] = []

        def _visit(name: str) -> bool:
            if name in in_stack:
                return False  # cycle
            if name in visited:
                return True
            in_stack.add(name)
            for dep in graph.get(name, ()):
                if not _visit(dep):
                    return False
            in_stack.discard(name)
            visited.add(name)
            order.append(name)
            return True

        for name in all_names:
            if not _visit(name):
                return []
        return order


class WorkspaceDetector:
    """Detect workspace/monorepo configurations.

    Scans a directory for workspace configuration files and resolves
    member projects.

    Pure detection -- no side effects, no subprocess calls.
    """

    def detect(self, root: Path | None = None) -> list[WorkspaceInfo]:
        """Detect all workspace configurations at the given root.

        A single repo can have multiple workspace systems (e.g., Cargo workspace
        + npm workspace for a Rust + JS project).

        Args:
            root: Directory to scan. Defaults to cwd.

        Returns:
            List of WorkspaceInfo for each detected workspace. Never raises.
        """
        root = (root or Path.cwd()).resolve()
        try:
            if not root.is_dir():
                return []
        except (OSError, PermissionError):
            return []

        results: list[WorkspaceInfo] = []

        detectors = [
            self._detect_cargo,
            self._detect_pnpm,
            self._detect_npm,
            self._detect_yarn,
            self._detect_poetry,
            self._detect_pdm,
            self._detect_hatch,
            self._detect_uv,
            self._detect_go_work,
            self._detect_nx,
            self._detect_turborepo,
            self._detect_lerna,
            self._detect_bazel,
            self._detect_pants,
        ]

        for detector in detectors:
            try:
                info = detector(root)
                if info is not None:
                    results.append(info)
            except Exception:
                continue

        return results

    def detect_first(self, root: Path | None = None) -> WorkspaceInfo | None:
        """Detect the primary workspace configuration.

        Returns:
            First detected WorkspaceInfo, or None.
        """
        results = self.detect(root)
        return results[0] if results else None

    def find_workspace_root(self, start: Path | None = None) -> Path | None:
        """Walk up from start to find the nearest workspace root.

        Args:
            start: Starting directory. Defaults to cwd.

        Returns:
            Path to workspace root, or None.
        """
        current = (start or Path.cwd()).resolve()
        while current != current.parent:
            if self.detect(current):
                return current
            current = current.parent
        return None

    # --- Rust (Cargo) ---

    def _detect_cargo(self, root: Path) -> WorkspaceInfo | None:
        cargo_toml = root / "Cargo.toml"
        if not cargo_toml.exists():
            return None

        data = load_toml(cargo_toml)
        if not data:
            return None

        workspace = data.get("workspace")
        if not workspace:
            return None

        members = workspace.get("members", [])
        exclude = workspace.get("exclude", [])
        if not members:
            return None

        projects = self._resolve_cargo_members(root, members, exclude)

        return WorkspaceInfo(
            kind=WorkspaceKind.CARGO,
            root=root,
            config_file=cargo_toml,
            member_globs=tuple(members),
            projects=tuple(projects),
            shared_deps_file=cargo_toml if workspace.get("dependencies") else None,
        )

    def _resolve_cargo_members(
        self, root: Path, members: list[str], exclude: list[str]
    ) -> list[SubProject]:
        projects: list[SubProject] = []
        matched_dirs = self._expand_globs(root, members, exclude)

        for member_dir in matched_dirs:
            member_toml = member_dir / "Cargo.toml"
            if not member_toml.exists():
                continue

            data = load_toml(member_toml)
            if not data:
                continue

            pkg = data.get("package", {})
            name = pkg.get("name", member_dir.name)
            version = pkg.get("version")

            deps: list[str] = []
            for section in ("dependencies", "dev-dependencies", "build-dependencies"):
                dep_table = data.get(section, {})
                for dep_name, dep_val in dep_table.items():
                    if isinstance(dep_val, dict) and dep_val.get("path"):
                        deps.append(dep_name)

            projects.append(
                SubProject(
                    name=name,
                    path=member_dir,
                    kind="rust_crate",
                    version=version,
                    dependencies=tuple(deps),
                )
            )

        return projects

    # --- pnpm ---

    def _detect_pnpm(self, root: Path) -> WorkspaceInfo | None:
        ws_yaml = root / "pnpm-workspace.yaml"
        if not ws_yaml.exists():
            return None

        # Parse pnpm-workspace.yaml (simple YAML -- packages: list)
        globs = self._parse_pnpm_workspace_yaml(ws_yaml)
        if not globs:
            return None

        projects = self._resolve_node_members(root, globs)

        return WorkspaceInfo(
            kind=WorkspaceKind.PNPM,
            root=root,
            config_file=ws_yaml,
            member_globs=tuple(globs),
            projects=tuple(projects),
            shared_deps_file=root / "package.json" if (root / "package.json").exists() else None,
        )

    def _parse_pnpm_workspace_yaml(self, path: Path) -> list[str]:
        """Parse pnpm-workspace.yaml without a YAML dependency.

        Only handles the common format:
            packages:
              - 'packages/*'
              - 'apps/*'
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []

        globs: list[str] = []
        in_packages = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("packages:"):
                in_packages = True
                continue
            if in_packages:
                if stripped.startswith("- "):
                    value = stripped[2:].strip().strip("'\"")
                    if value:
                        globs.append(value)
                elif stripped and not stripped.startswith("#"):
                    break  # next top-level key
        return globs

    # --- npm ---

    def _detect_npm(self, root: Path) -> WorkspaceInfo | None:
        pkg_json = root / "package.json"
        if not pkg_json.exists():
            return None

        data = load_json(pkg_json)
        if not data:
            return None

        workspaces = data.get("workspaces")
        if not workspaces:
            return None

        # workspaces can be a list or {"packages": [...]}
        if isinstance(workspaces, dict):
            globs = workspaces.get("packages", [])
        elif isinstance(workspaces, list):
            globs = workspaces
        else:
            return None

        if not globs:
            return None

        # If pnpm-workspace.yaml exists, this is pnpm not npm
        if (root / "pnpm-workspace.yaml").exists():
            return None

        projects = self._resolve_node_members(root, globs)

        return WorkspaceInfo(
            kind=WorkspaceKind.NPM,
            root=root,
            config_file=pkg_json,
            member_globs=tuple(globs),
            projects=tuple(projects),
            shared_deps_file=pkg_json,
        )

    # --- yarn ---

    def _detect_yarn(self, root: Path) -> WorkspaceInfo | None:
        # Yarn uses the same package.json "workspaces" field but has .yarnrc.yml
        pkg_json = root / "package.json"
        yarnrc = root / ".yarnrc.yml"
        yarn_lock = root / "yarn.lock"

        if not pkg_json.exists():
            return None

        # Need yarn indicator
        if not yarnrc.exists() and not yarn_lock.exists():
            return None

        data = load_json(pkg_json)
        if not data:
            return None

        workspaces = data.get("workspaces")
        if not workspaces:
            return None

        if isinstance(workspaces, dict):
            globs = workspaces.get("packages", [])
        elif isinstance(workspaces, list):
            globs = workspaces
        else:
            return None

        if not globs:
            return None

        projects = self._resolve_node_members(root, globs)

        return WorkspaceInfo(
            kind=WorkspaceKind.YARN,
            root=root,
            config_file=pkg_json,
            member_globs=tuple(globs),
            projects=tuple(projects),
            shared_deps_file=pkg_json,
        )

    # --- Node shared member resolution ---

    def _resolve_node_members(self, root: Path, globs: list[str]) -> list[SubProject]:
        projects: list[SubProject] = []
        matched_dirs = self._expand_globs(root, globs, [])

        for member_dir in matched_dirs:
            pkg_json = member_dir / "package.json"
            if not pkg_json.exists():
                continue

            data = load_json(pkg_json)
            if not data:
                continue

            name = data.get("name", member_dir.name)
            version = data.get("version")

            # Collect deps that might be workspace siblings
            deps: list[str] = []
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                dep_dict = data.get(section, {})
                for dep_name, dep_ver in dep_dict.items():
                    if isinstance(dep_ver, str) and (
                        dep_ver.startswith("workspace:")
                        or dep_ver == "*"
                        or dep_ver.startswith("file:")
                    ):
                        deps.append(dep_name)

            projects.append(
                SubProject(
                    name=name,
                    path=member_dir,
                    kind="npm_package",
                    version=version,
                    dependencies=tuple(deps),
                )
            )

        return projects

    # --- Poetry ---

    def _detect_poetry(self, root: Path) -> WorkspaceInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        # Poetry doesn't have native workspaces, but poetry-monorepo-plugin
        # uses [tool.poetry.packages] with relative paths, and some setups
        # use a directory structure convention
        poetry = data.get("tool", {}).get("poetry", {})
        if not poetry:
            return None

        # Check for poetry-monorepo patterns:
        # 1. [tool.poetry.plugins] with "poetry-monorepo-plugin"
        # 2. Multiple [tool.poetry.packages] entries pointing to subdirs
        packages = poetry.get("packages", [])
        if len(packages) <= 1:
            return None

        # This looks like a poetry monorepo
        projects: list[SubProject] = []
        for pkg in packages:
            if isinstance(pkg, dict) and "include" in pkg:
                pkg_from = pkg.get("from", ".")
                pkg_path = root / pkg_from / pkg["include"]
                if pkg_path.is_dir():
                    projects.append(
                        SubProject(
                            name=pkg["include"],
                            path=pkg_path,
                            kind="python_package",
                        )
                    )

        if not projects:
            return None

        return WorkspaceInfo(
            kind=WorkspaceKind.POETRY,
            root=root,
            config_file=pyproject,
            projects=tuple(projects),
            shared_deps_file=pyproject,
        )

    # --- PDM ---

    def _detect_pdm(self, root: Path) -> WorkspaceInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        # PDM workspaces: [tool.pdm.workspace] or pdm.workspace in new format
        pdm = data.get("tool", {}).get("pdm", {})
        workspace = pdm.get("workspace", {})
        packages = workspace.get("packages", [])

        if not packages:
            return None

        projects = self._resolve_python_members(root, packages)

        return WorkspaceInfo(
            kind=WorkspaceKind.PDM,
            root=root,
            config_file=pyproject,
            member_globs=tuple(packages),
            projects=tuple(projects),
            shared_deps_file=pyproject,
        )

    # --- Hatch ---

    def _detect_hatch(self, root: Path) -> WorkspaceInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        # Hatch doesn't have formal workspaces but uses [tool.hatch.envs]
        # with matrix and multiple build targets. Check for multi-package
        # via [tool.hatch.build.targets.wheel.packages] with multiple entries
        hatch = data.get("tool", {}).get("hatch", {})
        build = hatch.get("build", {})
        targets = build.get("targets", {})
        wheel = targets.get("wheel", {})
        packages = wheel.get("packages", [])

        if len(packages) <= 1:
            return None

        projects: list[SubProject] = []
        for pkg_path in packages:
            resolved = root / pkg_path
            if resolved.is_dir():
                projects.append(
                    SubProject(
                        name=Path(pkg_path).name,
                        path=resolved,
                        kind="python_package",
                    )
                )

        if not projects:
            return None

        return WorkspaceInfo(
            kind=WorkspaceKind.HATCH,
            root=root,
            config_file=pyproject,
            projects=tuple(projects),
            shared_deps_file=pyproject,
        )

    # --- uv ---

    def _detect_uv(self, root: Path) -> WorkspaceInfo | None:
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            return None

        data = load_toml(pyproject)
        if not data:
            return None

        # uv workspaces: [tool.uv.workspace] with members list
        uv = data.get("tool", {}).get("uv", {})
        workspace = uv.get("workspace", {})
        members = workspace.get("members", [])

        if not members:
            return None

        exclude = workspace.get("exclude", [])
        projects = self._resolve_python_members(root, members, exclude)

        return WorkspaceInfo(
            kind=WorkspaceKind.UV,
            root=root,
            config_file=pyproject,
            member_globs=tuple(members),
            projects=tuple(projects),
            shared_deps_file=pyproject,
        )

    # --- Python shared member resolution ---

    def _resolve_python_members(
        self, root: Path, globs: list[str], exclude: list[str] | None = None
    ) -> list[SubProject]:
        projects: list[SubProject] = []
        matched_dirs = self._expand_globs(root, globs, exclude or [])

        for member_dir in matched_dirs:
            pyproject = member_dir / "pyproject.toml"
            if not pyproject.exists():
                continue

            data = load_toml(pyproject)
            if not data:
                continue

            project = data.get("project", {})
            name = project.get("name", member_dir.name)
            version = project.get("version")

            # Collect path dependencies
            deps: list[str] = []
            for _dep_str in project.get("dependencies", []):
                # PEP 508 doesn't have path deps in requirements strings,
                # but some tools use them; skip for now
                pass

            # Check tool-specific path deps
            tool = data.get("tool", {})
            for tool_name in ("poetry", "pdm", "uv"):
                tool_deps = tool.get(tool_name, {}).get("dependencies", {})
                if isinstance(tool_deps, dict):
                    for dep_name, dep_spec in tool_deps.items():
                        if isinstance(dep_spec, dict) and dep_spec.get("path"):
                            deps.append(dep_name)

            projects.append(
                SubProject(
                    name=name,
                    path=member_dir,
                    kind="python_package",
                    version=version,
                    dependencies=tuple(deps),
                )
            )

        return projects

    # --- Go ---

    def _detect_go_work(self, root: Path) -> WorkspaceInfo | None:
        go_work = root / "go.work"
        if not go_work.exists():
            return None

        try:
            text = go_work.read_text(encoding="utf-8")
        except OSError:
            return None

        # Parse go.work "use" directives
        globs: list[str] = []
        in_use = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("use ("):
                in_use = True
                continue
            if stripped == "use" and not in_use:
                in_use = True
                continue
            if in_use:
                if stripped == ")":
                    in_use = False
                    continue
                if stripped and not stripped.startswith("//"):
                    globs.append(stripped)
            elif stripped.startswith("use "):
                # Single-line use directive
                value = stripped[4:].strip()
                if value:
                    globs.append(value)

        if not globs:
            return None

        projects: list[SubProject] = []
        for g in globs:
            mod_dir = (root / g).resolve()
            if not mod_dir.is_dir():
                continue
            go_mod = mod_dir / "go.mod"
            if not go_mod.exists():
                continue

            # Parse module name from go.mod
            mod_name = mod_dir.name
            try:
                mod_text = go_mod.read_text(encoding="utf-8")
                for mod_line in mod_text.splitlines():
                    if mod_line.startswith("module "):
                        mod_name = mod_line[7:].strip()
                        break
            except OSError:
                pass

            projects.append(
                SubProject(
                    name=mod_name,
                    path=mod_dir,
                    kind="go_module",
                )
            )

        return WorkspaceInfo(
            kind=WorkspaceKind.GO_WORK,
            root=root,
            config_file=go_work,
            member_globs=tuple(globs),
            projects=tuple(projects),
        )

    # --- Nx ---

    def _detect_nx(self, root: Path) -> WorkspaceInfo | None:
        nx_json = root / "nx.json"
        if not nx_json.exists():
            return None

        data = load_json(nx_json)
        if not data:
            return None

        # Nx auto-detects projects. Check for workspaceLayout or project patterns
        layout = data.get("workspaceLayout", {})
        apps_dir = layout.get("appsDir", "apps")
        libs_dir = layout.get("libsDir", "libs")

        globs = [f"{apps_dir}/*", f"{libs_dir}/*"]

        projects: list[SubProject] = []
        for base_dir in (apps_dir, libs_dir):
            base_path = root / base_dir
            if not base_path.is_dir():
                continue
            for child in sorted(base_path.iterdir()):
                if not child.is_dir():
                    continue
                # Check for project.json (Nx) or package.json
                if (child / "project.json").exists() or (child / "package.json").exists():
                    name = child.name
                    pkg_json = child / "package.json"
                    if pkg_json.exists():
                        pkg_data = load_json(pkg_json)
                        if pkg_data:
                            name = pkg_data.get("name", name)
                    projects.append(
                        SubProject(
                            name=name,
                            path=child,
                            kind="nx_project",
                        )
                    )

        return WorkspaceInfo(
            kind=WorkspaceKind.NX,
            root=root,
            config_file=nx_json,
            member_globs=tuple(globs),
            projects=tuple(projects),
        )

    # --- Turborepo ---

    def _detect_turborepo(self, root: Path) -> WorkspaceInfo | None:
        turbo_json = root / "turbo.json"
        if not turbo_json.exists():
            return None

        # Turborepo relies on the underlying package manager's workspaces.
        # It just adds pipeline orchestration on top.
        pkg_json = root / "package.json"
        if not pkg_json.exists():
            return None

        data = load_json(pkg_json)
        if not data:
            return None

        workspaces = data.get("workspaces")
        if not workspaces:
            return None

        if isinstance(workspaces, dict):
            globs = workspaces.get("packages", [])
        elif isinstance(workspaces, list):
            globs = workspaces
        else:
            return None

        projects = self._resolve_node_members(root, globs)

        return WorkspaceInfo(
            kind=WorkspaceKind.TURBOREPO,
            root=root,
            config_file=turbo_json,
            member_globs=tuple(globs),
            projects=tuple(projects),
            shared_deps_file=pkg_json,
        )

    # --- Lerna ---

    def _detect_lerna(self, root: Path) -> WorkspaceInfo | None:
        lerna_json = root / "lerna.json"
        if not lerna_json.exists():
            return None

        data = load_json(lerna_json)
        if not data:
            return None

        packages = data.get("packages", ["packages/*"])

        projects = self._resolve_node_members(root, packages)

        return WorkspaceInfo(
            kind=WorkspaceKind.LERNA,
            root=root,
            config_file=lerna_json,
            member_globs=tuple(packages),
            projects=tuple(projects),
            shared_deps_file=root / "package.json" if (root / "package.json").exists() else None,
        )

    # --- Bazel ---

    def _detect_bazel(self, root: Path) -> WorkspaceInfo | None:
        # Bazel uses WORKSPACE or WORKSPACE.bazel or MODULE.bazel (bzlmod)
        for ws_file in ("MODULE.bazel", "WORKSPACE.bazel", "WORKSPACE"):
            ws_path = root / ws_file
            if ws_path.exists():
                # Find BUILD files to identify packages
                projects = self._find_bazel_packages(root)
                return WorkspaceInfo(
                    kind=WorkspaceKind.BAZEL,
                    root=root,
                    config_file=ws_path,
                    projects=tuple(projects),
                )
        return None

    def _find_bazel_packages(self, root: Path) -> list[SubProject]:
        """Find Bazel packages (directories with BUILD files)."""
        projects: list[SubProject] = []
        # Only look one level deep to avoid excessive I/O
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            for build_file in ("BUILD.bazel", "BUILD"):
                if (child / build_file).exists():
                    projects.append(
                        SubProject(
                            name=child.name,
                            path=child,
                            kind="bazel_package",
                        )
                    )
                    break
        return projects

    # --- Pants ---

    def _detect_pants(self, root: Path) -> WorkspaceInfo | None:
        pants_toml = root / "pants.toml"
        if not pants_toml.exists():
            return None

        data = load_toml(pants_toml)
        if not data:
            return None

        # Pants uses [source] root_patterns
        source = data.get("source", data.get("GLOBAL", {}))
        root_patterns = source.get("root_patterns", ["/"])

        # Find directories with BUILD files
        projects = self._find_bazel_packages(root)  # Same BUILD file pattern

        return WorkspaceInfo(
            kind=WorkspaceKind.PANTS,
            root=root,
            config_file=pants_toml,
            member_globs=tuple(root_patterns),
            projects=tuple(projects),
        )

    # --- Utility methods ---

    def _expand_globs(self, root: Path, patterns: list[str], exclude: list[str]) -> list[Path]:
        """Expand glob patterns relative to root, minus exclusions.

        Handles both simple globs (packages/*) and recursive globs (crates/**).
        Returns sorted list of directories.
        """
        matched: set[Path] = set()

        for pattern in patterns:
            # Normalize: strip negation prefix if present
            if pattern.startswith("!"):
                continue
            try:
                for match in root.glob(pattern):
                    if match.is_dir():
                        matched.add(match.resolve())
            except (OSError, ValueError):
                continue

        # Apply exclusions
        excluded: set[Path] = set()
        for pattern in exclude:
            clean = pattern.lstrip("!")
            try:
                for match in root.glob(clean):
                    if match.is_dir():
                        excluded.add(match.resolve())
            except (OSError, ValueError):
                continue

        # Also handle negation patterns from the main list
        for pattern in patterns:
            if pattern.startswith("!"):
                clean = pattern[1:]
                try:
                    for match in root.glob(clean):
                        if match.is_dir():
                            excluded.add(match.resolve())
                except (OSError, ValueError):
                    continue

        return sorted(matched - excluded)
