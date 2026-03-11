"""Environment manifest generation for SBOM-style compliance export.

Generates Software Bill of Materials (SBOM) from the current environment
in SPDX and CycloneDX formats. Detects Python, Conda, and system packages.

Pure detection -- consistent with sniff's philosophy.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PackageInfo:
    """Detailed package information."""

    name: str
    version: str
    source: str  # "pypi" | "conda" | "system"
    license: str | None = None
    homepage: str | None = None
    dependencies: tuple[str, ...] = ()
    checksum: str | None = None


def _detect_python_packages() -> list[PackageInfo]:
    """Detect installed Python packages via importlib.metadata."""
    try:
        from importlib.metadata import distributions
    except ImportError:
        return []

    packages: list[PackageInfo] = []
    seen: set[str] = set()

    try:
        for dist in distributions():
            name = dist.metadata.get("Name")
            version = dist.metadata.get("Version")
            if not name or not version:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            pkg_license = dist.metadata.get("License")
            homepage = dist.metadata.get("Home-page")
            if not homepage:
                # Try Project-URL
                project_urls = dist.metadata.get_all("Project-URL") or []
                for url_line in project_urls:
                    if "," in url_line:
                        label, url = url_line.split(",", 1)
                        label = label.strip().lower()
                        url = url.strip()
                        if label in ("homepage", "home"):
                            homepage = url
                            break

            # Get dependencies
            deps: list[str] = []
            requires = dist.metadata.get_all("Requires-Dist") or []
            for req in requires:
                # Strip extras and version specifiers for simple dep name
                dep_name = req.split(";")[0].split("[")[0].split("(")[0].split("<")[0]
                dep_name = dep_name.split(">")[0].split("=")[0].split("!")[0].strip()
                if dep_name:
                    deps.append(dep_name)

            # Compute checksum from dist location if available
            checksum: str | None = None
            try:
                if hasattr(dist, '_path') and dist._path is not None:
                    dist_path = Path(str(dist._path))
                    if dist_path.exists() and dist_path.is_file():
                        h = hashlib.sha256(dist_path.read_bytes()).hexdigest()
                        checksum = f"sha256:{h}"
            except (OSError, TypeError):
                pass

            packages.append(PackageInfo(
                name=name,
                version=version,
                source="pypi",
                license=pkg_license,
                homepage=homepage,
                dependencies=tuple(deps),
                checksum=checksum,
            ))
    except Exception:
        pass

    return sorted(packages, key=lambda p: p.name.lower())


def _detect_conda_packages() -> list[PackageInfo]:
    """Detect conda packages in the active environment."""
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if not conda_prefix:
        return []

    # Try conda list --json
    for cmd in ("conda", "mamba"):
        try:
            result = subprocess.run(
                [cmd, "list", "--prefix", conda_prefix, "--json"],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if result.returncode != 0:
                continue

            data = json.loads(result.stdout)
            packages: list[PackageInfo] = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name", "")
                version = entry.get("version", "")
                if not name or not version:
                    continue
                channel = entry.get("channel", "")
                packages.append(PackageInfo(
                    name=name,
                    version=version,
                    source="conda",
                    license=None,
                    homepage=None,
                    dependencies=[],
                    checksum=None,
                ))
            return sorted(packages, key=lambda p: p.name.lower())
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            continue

    return []


def _detect_system_packages() -> list[PackageInfo]:
    """Detect system packages (platform-specific)."""
    packages: list[PackageInfo] = []
    system = platform.system().lower()

    if system == "linux":
        packages = _detect_linux_system_packages()
    elif system == "darwin":
        packages = _detect_macos_system_packages()

    return sorted(packages, key=lambda p: p.name.lower())


def _detect_linux_system_packages() -> list[PackageInfo]:
    """Detect Linux system packages via dpkg or rpm."""
    packages: list[PackageInfo] = []

    # Try dpkg (Debian/Ubuntu)
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f", "${Package}\t${Version}\n"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    packages.append(PackageInfo(
                        name=parts[0],
                        version=parts[1],
                        source="system",
                    ))
            return packages
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Try rpm (RHEL/Fedora)
    try:
        result = subprocess.run(
            ["rpm", "-qa", "--queryformat", "%{NAME}\t%{VERSION}\n"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    packages.append(PackageInfo(
                        name=parts[0],
                        version=parts[1],
                        source="system",
                    ))
            return packages
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return packages


def _detect_macos_system_packages() -> list[PackageInfo]:
    """Detect macOS packages via brew."""
    packages: list[PackageInfo] = []

    try:
        result = subprocess.run(
            ["brew", "list", "--versions"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    packages.append(PackageInfo(
                        name=parts[0],
                        version=parts[1],
                        source="system",
                    ))
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return packages


def _compute_file_checksums(paths: list[Path]) -> dict[Path, str]:
    """Compute SHA-256 checksums for a list of file paths."""
    checksums: dict[Path, str] = {}
    for p in paths:
        try:
            if p.is_file():
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                checksums[p] = f"sha256:{h}"
        except (OSError, PermissionError):
            pass
    return checksums


@dataclass(frozen=True)
class EnvironmentManifest:
    """Complete environment manifest (SBOM-style).

    This is for compliance, security, and auditing.
    """

    manifest_version: str
    generated_at: datetime
    generated_by: str

    # Environment snapshot
    context: Any  # ExecutionContext

    # Dependencies (detailed)
    python_packages: list[PackageInfo]
    system_packages: list[PackageInfo]
    conda_packages: list[PackageInfo]

    # Checksums
    file_checksums: dict[Path, str]

    @classmethod
    def generate(
        cls,
        *,
        tool_name: str = "sniff",
        include_system: bool = True,
        include_conda: bool = True,
        checksum_paths: list[Path] | None = None,
    ) -> EnvironmentManifest:
        """Create a manifest from the current environment.

        Args:
            tool_name: Name of the tool generating the manifest.
            include_system: Include system-level packages.
            include_conda: Include conda packages.
            checksum_paths: Files to compute checksums for.

        Returns:
            Complete EnvironmentManifest.
        """
        from sniff.context import ExecutionContext

        context = ExecutionContext.capture(
            include_env_vars=False,
            include_packages=True,
            include_hardware=False,
        )

        python_packages = _detect_python_packages()

        conda_packages: list[PackageInfo] = []
        if include_conda:
            conda_packages = _detect_conda_packages()

        system_packages: list[PackageInfo] = []
        if include_system:
            system_packages = _detect_system_packages()

        file_checksums: dict[Path, str] = {}
        if checksum_paths:
            file_checksums = _compute_file_checksums(checksum_paths)

        return cls(
            manifest_version="1.0",
            generated_at=datetime.now(timezone.utc),
            generated_by=tool_name,
            context=context,
            python_packages=python_packages,
            system_packages=system_packages,
            conda_packages=conda_packages,
            file_checksums=file_checksums,
        )

    def to_spdx(self) -> str:
        """Export manifest as SPDX 2.3 tag-value format."""
        lines: list[str] = []

        doc_ns = f"https://spdx.org/spdxdocs/sniff-manifest-{uuid.uuid4()}"
        lines.append("SPDXVersion: SPDX-2.3")
        lines.append("DataLicense: CC0-1.0")
        lines.append(f"SPDXID: SPDXRef-DOCUMENT")
        lines.append(f"DocumentName: sniff-environment-manifest")
        lines.append(f"DocumentNamespace: {doc_ns}")
        lines.append(f"Creator: Tool: {self.generated_by}")
        lines.append(f"Created: {self.generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        lines.append("")

        pkg_idx = 0
        all_packages = (
            list(self.python_packages)
            + list(self.conda_packages)
            + list(self.system_packages)
        )

        for pkg in all_packages:
            pkg_idx += 1
            spdx_id = f"SPDXRef-Package-{pkg_idx}"
            lines.append(f"PackageName: {pkg.name}")
            lines.append(f"SPDXID: {spdx_id}")
            lines.append(f"PackageVersion: {pkg.version}")
            lines.append(f"PackageDownloadLocation: NOASSERTION")

            if pkg.license:
                lines.append(f"PackageLicenseConcluded: {pkg.license}")
            else:
                lines.append(f"PackageLicenseConcluded: NOASSERTION")
            lines.append(f"PackageLicenseDeclared: NOASSERTION")
            lines.append(f"PackageCopyrightText: NOASSERTION")

            if pkg.homepage:
                lines.append(f"PackageHomePage: {pkg.homepage}")

            if pkg.checksum:
                # checksum format: "sha256:hexdigest"
                algo, digest = pkg.checksum.split(":", 1)
                lines.append(f"PackageChecksum: SHA256: {digest}")

            lines.append(f"PackageSupplier: NOASSERTION")
            lines.append(f"FilesAnalyzed: false")
            lines.append(f"PackageComment: source={pkg.source}")
            lines.append("")

        return "\n".join(lines)

    def to_cyclonedx(self) -> str:
        """Export manifest as CycloneDX 1.5 JSON format."""
        components: list[dict[str, Any]] = []

        all_packages = (
            list(self.python_packages)
            + list(self.conda_packages)
            + list(self.system_packages)
        )

        for pkg in all_packages:
            component: dict[str, Any] = {
                "type": "library",
                "name": pkg.name,
                "version": pkg.version,
                "purl": _make_purl(pkg),
            }

            if pkg.license:
                component["licenses"] = [
                    {"license": {"name": pkg.license}}
                ]

            if pkg.homepage:
                component["externalReferences"] = [
                    {"type": "website", "url": pkg.homepage}
                ]

            if pkg.checksum:
                algo, digest = pkg.checksum.split(":", 1)
                component["hashes"] = [
                    {"alg": algo.upper(), "content": digest}
                ]

            if pkg.dependencies:
                component["properties"] = [
                    {"name": "sniff:dependencies", "value": ",".join(pkg.dependencies)}
                ]

            components.append(component)

        bom: dict[str, Any] = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "timestamp": self.generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tools": [
                    {
                        "vendor": "sniff",
                        "name": self.generated_by,
                        "version": self.manifest_version,
                    }
                ],
            },
            "components": components,
        }

        return json.dumps(bom, indent=2)

    def validate_checksums(self) -> list[str]:
        """Validate file checksums, return list of mismatches.

        Returns:
            List of mismatch descriptions. Empty list means all valid.
        """
        mismatches: list[str] = []

        for file_path, expected in self.file_checksums.items():
            try:
                if not file_path.exists():
                    mismatches.append(f"{file_path}: file not found")
                    continue

                if not file_path.is_file():
                    mismatches.append(f"{file_path}: not a regular file")
                    continue

                # Parse expected checksum
                if ":" in expected:
                    algo, expected_digest = expected.split(":", 1)
                else:
                    algo = "sha256"
                    expected_digest = expected

                if algo.lower() == "sha256":
                    actual_digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
                elif algo.lower() == "md5":
                    actual_digest = hashlib.md5(file_path.read_bytes()).hexdigest()
                elif algo.lower() == "sha1":
                    actual_digest = hashlib.sha1(file_path.read_bytes()).hexdigest()
                else:
                    mismatches.append(f"{file_path}: unsupported algorithm '{algo}'")
                    continue

                if actual_digest != expected_digest:
                    mismatches.append(
                        f"{file_path}: expected {expected}, got {algo}:{actual_digest}"
                    )
            except (OSError, PermissionError) as exc:
                mismatches.append(f"{file_path}: {exc}")

        return mismatches

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to JSON-serializable dict."""
        result: dict[str, Any] = {
            "manifest_version": self.manifest_version,
            "generated_at": self.generated_at.isoformat(),
            "generated_by": self.generated_by,
            "python_packages": [asdict(p) for p in self.python_packages],
            "system_packages": [asdict(p) for p in self.system_packages],
            "conda_packages": [asdict(p) for p in self.conda_packages],
            "file_checksums": {str(k): v for k, v in self.file_checksums.items()},
        }

        # Context
        if hasattr(self.context, "to_dict"):
            result["context"] = self.context.to_dict()
        elif hasattr(self.context, "__dataclass_fields__"):
            from sniff.context import _serialize_value
            result["context"] = _serialize_value(asdict(self.context))
        else:
            result["context"] = self.context

        return result


def _make_purl(pkg: PackageInfo) -> str:
    """Create a Package URL (purl) for a package."""
    if pkg.source == "pypi":
        return f"pkg:pypi/{pkg.name}@{pkg.version}"
    elif pkg.source == "conda":
        return f"pkg:conda/{pkg.name}@{pkg.version}"
    else:
        system = platform.system().lower()
        return f"pkg:generic/{pkg.name}@{pkg.version}?platform={system}"
