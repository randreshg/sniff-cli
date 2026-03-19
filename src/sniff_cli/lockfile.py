"""Lockfile parsing -- read dependency graphs from lock files.

Supports:
  - Cargo.lock (Rust)
  - package-lock.json (npm)
  - yarn.lock (Yarn v1 classic format)
  - poetry.lock (Poetry)
  - uv.lock / pip-compile output (requirements.txt with hashes)
  - pnpm-lock.yaml (basic)
  - Gemfile.lock (Ruby)

Pure detection -- no side effects, no subprocesses. Reads files only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

from sniff_cli._compat import tomllib


class LockfileKind(Enum):
    CARGO = "Cargo.lock"
    NPM = "package-lock.json"
    YARN = "yarn.lock"
    PNPM = "pnpm-lock.yaml"
    POETRY = "poetry.lock"
    UV = "uv.lock"
    PIP_COMPILE = "requirements.txt"
    GEMFILE = "Gemfile.lock"


@dataclass(frozen=True)
class LockedDependency:
    """A single locked dependency."""

    name: str
    version: str
    source: str | None = None  # registry url, git url, path, etc.
    dependencies: tuple[str, ...] = ()  # names of direct dependencies
    checksum: str | None = None  # hash/checksum if available


@dataclass(frozen=True)
class LockfileInfo:
    """Parsed lockfile information."""

    kind: LockfileKind
    path: Path
    lockfile_version: str | None = None
    packages: tuple[LockedDependency, ...] = ()

    @property
    def package_count(self) -> int:
        return len(self.packages)

    @property
    def package_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.packages)

    def get_package(self, name: str) -> LockedDependency | None:
        """Find a package by name (first match)."""
        for p in self.packages:
            if p.name == name:
                return p
        return None

    def dependency_graph(self) -> dict[str, tuple[str, ...]]:
        """Build a name -> dependency names mapping."""
        known = set(self.package_names)
        return {
            p.name: tuple(d for d in p.dependencies if d in known)
            for p in self.packages
        }

    def find_outdated(self, latest: dict[str, str]) -> list[tuple[str, str, str]]:
        """Find packages where the locked version differs from latest.

        Args:
            latest: Mapping of package name -> latest version string.

        Returns:
            List of (name, locked_version, latest_version) for outdated packages.
        """
        outdated: list[tuple[str, str, str]] = []
        for pkg in self.packages:
            if pkg.name in latest and pkg.version != latest[pkg.name]:
                outdated.append((pkg.name, pkg.version, latest[pkg.name]))
        return outdated


class LockfileParser:
    """Parse dependency lockfiles.

    Pure filesystem reads only -- no network, no subprocesses.
    """

    def parse(self, path: Path) -> LockfileInfo | None:
        """Parse a lockfile at the given path.

        Auto-detects format from filename.

        Args:
            path: Path to the lockfile.

        Returns:
            LockfileInfo if parsed successfully, None otherwise.
        """
        if not path.is_file():
            return None

        dispatch = {
            "Cargo.lock": (LockfileKind.CARGO, self._parse_cargo_lock),
            "package-lock.json": (LockfileKind.NPM, self._parse_npm_lock),
            "yarn.lock": (LockfileKind.YARN, self._parse_yarn_lock),
            "pnpm-lock.yaml": (LockfileKind.PNPM, self._parse_pnpm_lock),
            "poetry.lock": (LockfileKind.POETRY, self._parse_poetry_lock),
            "uv.lock": (LockfileKind.UV, self._parse_uv_lock),
            "Gemfile.lock": (LockfileKind.GEMFILE, self._parse_gemfile_lock),
        }

        handler = dispatch.get(path.name)
        if handler is None:
            return None

        kind, parser_fn = handler
        try:
            return parser_fn(path, kind)
        except Exception:
            return None

    def detect_and_parse(self, root: Path) -> list[LockfileInfo]:
        """Find and parse all lockfiles in a directory.

        Args:
            root: Directory to scan (non-recursive).

        Returns:
            List of successfully parsed LockfileInfo. Never raises.
        """
        try:
            if not root.is_dir():
                return []
        except (OSError, PermissionError):
            return []

        lockfile_names = [
            "Cargo.lock",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "uv.lock",
            "Gemfile.lock",
        ]

        results: list[LockfileInfo] = []
        for name in lockfile_names:
            lf = root / name
            try:
                if lf.is_file():
                    info = self.parse(lf)
                    if info is not None:
                        results.append(info)
            except (OSError, PermissionError):
                continue
        return results

    # -- Cargo.lock --

    def _parse_cargo_lock(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        if tomllib is None:
            return self._parse_cargo_lock_text(path, kind)

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, ValueError):
            return self._parse_cargo_lock_text(path, kind)

        version = str(data.get("version", ""))
        packages: list[LockedDependency] = []

        for pkg in data.get("package", []):
            name = pkg.get("name", "")
            ver = pkg.get("version", "")
            source = pkg.get("source")
            checksum = pkg.get("checksum")

            deps: list[str] = []
            for dep in pkg.get("dependencies", []):
                if isinstance(dep, str):
                    # "name version source" format
                    dep_name = dep.split()[0]
                    deps.append(dep_name)

            packages.append(LockedDependency(
                name=name,
                version=ver,
                source=source,
                dependencies=tuple(deps),
                checksum=checksum,
            ))

        return LockfileInfo(
            kind=kind,
            path=path,
            lockfile_version=version,
            packages=tuple(packages),
        )

    def _parse_cargo_lock_text(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        """Fallback text-based parser for Cargo.lock when TOML lib unavailable."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

        packages: list[LockedDependency] = []
        # Match [[package]] blocks
        blocks = re.split(r"^\[\[package\]\]", text, flags=re.MULTILINE)

        for block in blocks[1:]:  # skip preamble
            name_m = re.search(r'^name\s*=\s*"([^"]+)"', block, re.MULTILINE)
            ver_m = re.search(r'^version\s*=\s*"([^"]+)"', block, re.MULTILINE)
            src_m = re.search(r'^source\s*=\s*"([^"]+)"', block, re.MULTILINE)
            chk_m = re.search(r'^checksum\s*=\s*"([^"]+)"', block, re.MULTILINE)

            if name_m and ver_m:
                deps: list[str] = []
                dep_section = re.search(
                    r"^dependencies\s*=\s*\[(.*?)\]", block,
                    re.MULTILINE | re.DOTALL,
                )
                if dep_section:
                    for dep_m in re.finditer(r'"([^"]+)"', dep_section.group(1)):
                        dep_name = dep_m.group(1).split()[0]
                        deps.append(dep_name)

                packages.append(LockedDependency(
                    name=name_m.group(1),
                    version=ver_m.group(1),
                    source=src_m.group(1) if src_m else None,
                    dependencies=tuple(deps),
                    checksum=chk_m.group(1) if chk_m else None,
                ))

        return LockfileInfo(
            kind=kind,
            path=path,
            packages=tuple(packages),
        )

    # -- package-lock.json (npm) --

    def _parse_npm_lock(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        lockfile_version = str(data.get("lockfileVersion", ""))
        packages: list[LockedDependency] = []

        # npm v2/v3 uses "packages" key with path-keyed entries
        pkgs_map = data.get("packages", {})
        if pkgs_map:
            for pkg_path, pkg_data in pkgs_map.items():
                if not pkg_path:  # root package
                    continue
                # pkg_path is like "node_modules/foo" or "node_modules/foo/node_modules/bar"
                name = pkg_data.get("name") or pkg_path.rsplit("node_modules/", 1)[-1]
                version = pkg_data.get("version", "")
                resolved = pkg_data.get("resolved")
                integrity = pkg_data.get("integrity")

                dep_names = list(pkg_data.get("dependencies", {}).keys())
                dep_names.extend(pkg_data.get("devDependencies", {}).keys())

                packages.append(LockedDependency(
                    name=name,
                    version=version,
                    source=resolved,
                    dependencies=tuple(dep_names),
                    checksum=integrity,
                ))
        else:
            # npm v1 uses "dependencies" key
            self._parse_npm_v1_deps(data.get("dependencies", {}), packages)

        return LockfileInfo(
            kind=kind,
            path=path,
            lockfile_version=lockfile_version,
            packages=tuple(packages),
        )

    def _parse_npm_v1_deps(
        self, deps: dict, packages: list[LockedDependency], _depth: int = 0
    ) -> None:
        """Recursively parse npm v1 lock format."""
        if _depth > 20:  # safety limit
            return
        for name, info in deps.items():
            version = info.get("version", "")
            resolved = info.get("resolved")
            integrity = info.get("integrity")
            sub_deps = list(info.get("requires", {}).keys())

            packages.append(LockedDependency(
                name=name,
                version=version,
                source=resolved,
                dependencies=tuple(sub_deps),
                checksum=integrity,
            ))

            # Nested dependencies
            nested = info.get("dependencies", {})
            if nested:
                self._parse_npm_v1_deps(nested, packages, _depth + 1)

    # -- yarn.lock (v1 classic) --

    def _parse_yarn_lock(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

        packages: list[LockedDependency] = []

        # Yarn v1 format: header lines followed by indented blocks
        # "package@^1.0.0":
        #   version "1.2.3"
        #   resolved "https://..."
        #   integrity sha512-...
        #   dependencies:
        #     dep1 "^1.0"

        current_name: str | None = None
        current_version: str | None = None
        current_resolved: str | None = None
        current_integrity: str | None = None
        current_deps: list[str] = []
        in_deps = False

        for line in text.splitlines():
            # New package header
            if line and not line[0].isspace() and not line.startswith("#"):
                # Flush previous
                if current_name and current_version:
                    packages.append(LockedDependency(
                        name=current_name,
                        version=current_version,
                        source=current_resolved,
                        dependencies=tuple(current_deps),
                        checksum=current_integrity,
                    ))

                # Parse: "name@version", "name@version":, "@scope/name@version":
                header = line.rstrip(":")
                # Take first entry if comma-separated
                first = header.split(",")[0].strip().strip('"')
                # Split on last @
                at_idx = first.rfind("@")
                if at_idx > 0:
                    current_name = first[:at_idx]
                else:
                    current_name = first
                current_version = None
                current_resolved = None
                current_integrity = None
                current_deps = []
                in_deps = False
                continue

            stripped = line.strip()

            if stripped.startswith("version "):
                current_version = stripped.split('"')[1] if '"' in stripped else stripped.split()[-1]
                in_deps = False
            elif stripped.startswith("resolved "):
                current_resolved = stripped.split('"')[1] if '"' in stripped else None
                in_deps = False
            elif stripped.startswith("integrity "):
                current_integrity = stripped.split()[-1]
                in_deps = False
            elif stripped == "dependencies:":
                in_deps = True
            elif stripped == "optionalDependencies:":
                in_deps = False
            elif in_deps and stripped:
                # "dep-name" "^1.0.0"
                dep_name = stripped.split()[0].strip('"')
                if dep_name:
                    current_deps.append(dep_name)

        # Flush last package
        if current_name and current_version:
            packages.append(LockedDependency(
                name=current_name,
                version=current_version,
                source=current_resolved,
                dependencies=tuple(current_deps),
                checksum=current_integrity,
            ))

        return LockfileInfo(
            kind=kind,
            path=path,
            packages=tuple(packages),
        )

    # -- pnpm-lock.yaml (basic) --

    def _parse_pnpm_lock(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        """Basic pnpm-lock.yaml parser without YAML dependency.

        Extracts package names and versions from the packages section.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

        packages: list[LockedDependency] = []
        lockfile_version: str | None = None

        # Extract lockfileVersion
        for line in text.splitlines():
            if line.startswith("lockfileVersion:"):
                lockfile_version = line.split(":", 1)[1].strip().strip("'\"")
                break

        # pnpm v6+: packages section has entries like:
        #   /package-name@1.2.3:
        # pnpm v9+: entries like:
        #   package-name@1.2.3:
        in_packages = False
        for line in text.splitlines():
            stripped = line.strip()

            # Skip blank lines
            if not stripped:
                continue

            # Detect top-level sections (no indentation)
            if not line.startswith(" ") and not line.startswith("\t"):
                if stripped in ("packages:", "snapshots:"):
                    in_packages = stripped == "packages:"
                else:
                    in_packages = False
                continue

            if not in_packages:
                continue

            if stripped.endswith(":") and not stripped.startswith("#") and "@" in stripped:
                entry = stripped.rstrip(":").strip("'\"")
                # Remove leading / if present
                if entry.startswith("/"):
                    entry = entry[1:]

                # Parse name@version
                # Handle scoped packages: @scope/name@version
                if entry.startswith("@"):
                    # @scope/name@version -- find second @
                    at_idx = entry.index("@", 1)
                else:
                    at_idx = entry.index("@") if "@" in entry else -1

                if at_idx > 0:
                    name = entry[:at_idx]
                    version = entry[at_idx + 1:]
                    # Version might have extra qualifiers like (react@18.2.0)
                    version = version.split("(")[0]
                    packages.append(LockedDependency(name=name, version=version))

        return LockfileInfo(
            kind=kind,
            path=path,
            lockfile_version=lockfile_version,
            packages=tuple(packages),
        )

    # -- poetry.lock --

    def _parse_poetry_lock(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        if tomllib is None:
            return self._parse_poetry_lock_text(path, kind)

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, ValueError):
            return self._parse_poetry_lock_text(path, kind)

        packages: list[LockedDependency] = []

        for pkg in data.get("package", []):
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            source = pkg.get("source", {})
            source_url = source.get("url") if isinstance(source, dict) else None

            dep_names = list(pkg.get("dependencies", {}).keys())

            packages.append(LockedDependency(
                name=name,
                version=version,
                source=source_url,
                dependencies=tuple(dep_names),
            ))

        return LockfileInfo(
            kind=kind,
            path=path,
            packages=tuple(packages),
        )

    def _parse_poetry_lock_text(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        """Fallback text parser for poetry.lock."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

        packages: list[LockedDependency] = []
        blocks = re.split(r"^\[\[package\]\]", text, flags=re.MULTILINE)

        for block in blocks[1:]:
            name_m = re.search(r'^name\s*=\s*"([^"]+)"', block, re.MULTILINE)
            ver_m = re.search(r'^version\s*=\s*"([^"]+)"', block, re.MULTILINE)

            if name_m and ver_m:
                packages.append(LockedDependency(
                    name=name_m.group(1),
                    version=ver_m.group(1),
                ))

        return LockfileInfo(
            kind=kind,
            path=path,
            packages=tuple(packages),
        )

    # -- uv.lock --

    def _parse_uv_lock(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        """Parse uv.lock (TOML format)."""
        if tomllib is None:
            return None

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, ValueError):
            return None

        lockfile_version = str(data.get("version", ""))
        packages: list[LockedDependency] = []

        for pkg in data.get("package", []):
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            source = pkg.get("source")
            if isinstance(source, dict):
                source = source.get("url") or source.get("registry")

            dep_names: list[str] = []
            for dep in pkg.get("dependencies", []):
                if isinstance(dep, dict):
                    dep_names.append(dep.get("name", ""))
                elif isinstance(dep, str):
                    dep_names.append(dep.split()[0])

            packages.append(LockedDependency(
                name=name,
                version=version,
                source=source if isinstance(source, str) else None,
                dependencies=tuple(dep_names),
            ))

        return LockfileInfo(
            kind=kind,
            path=path,
            lockfile_version=lockfile_version,
            packages=tuple(packages),
        )

    # -- Gemfile.lock --

    def _parse_gemfile_lock(self, path: Path, kind: LockfileKind) -> LockfileInfo | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

        packages: list[LockedDependency] = []
        in_specs = False

        for line in text.splitlines():
            # GEM section contains "specs:" with indented gems
            if line.strip() == "specs:":
                in_specs = True
                continue

            if in_specs:
                if not line.startswith(" "):
                    in_specs = False
                    continue

                # Top-level gem: 4 spaces + name (version)
                m = re.match(r"^    (\S+)\s+\((\S+)\)$", line)
                if m:
                    packages.append(LockedDependency(
                        name=m.group(1),
                        version=m.group(2),
                    ))

        return LockfileInfo(
            kind=kind,
            path=path,
            packages=tuple(packages),
        )
