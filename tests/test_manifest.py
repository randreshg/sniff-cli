"""Tests for the EnvironmentManifest module."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from sniff.manifest import (
    EnvironmentManifest,
    PackageInfo,
    _compute_file_checksums,
    _detect_conda_packages,
    _detect_linux_system_packages,
    _detect_macos_system_packages,
    _detect_python_packages,
    _detect_system_packages,
    _make_purl,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_context(**overrides: object) -> MagicMock:
    """Create a minimal mock ExecutionContext."""
    ctx = MagicMock()
    ctx.to_dict.return_value = {"platform": "linux", "packages": {}}
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _make_manifest(
    *,
    python_packages: list[PackageInfo] | None = None,
    conda_packages: list[PackageInfo] | None = None,
    system_packages: list[PackageInfo] | None = None,
    file_checksums: dict[Path, str] | None = None,
    context: object | None = None,
    manifest_version: str = "1.0",
    generated_at: datetime | None = None,
    generated_by: str = "sniff",
) -> EnvironmentManifest:
    """Create a manifest with sensible defaults."""
    return EnvironmentManifest(
        manifest_version=manifest_version,
        generated_at=generated_at or datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        generated_by=generated_by,
        context=context or _make_context(),
        python_packages=python_packages or [],
        conda_packages=conda_packages or [],
        system_packages=system_packages or [],
        file_checksums=file_checksums or {},
    )


# ===========================================================================
# PackageInfo
# ===========================================================================

class TestPackageInfo:
    def test_basic_creation(self):
        pkg = PackageInfo(name="requests", version="2.31.0", source="pypi")
        assert pkg.name == "requests"
        assert pkg.version == "2.31.0"
        assert pkg.source == "pypi"

    def test_all_fields(self):
        pkg = PackageInfo(
            name="numpy",
            version="1.26.0",
            source="pypi",
            license="BSD-3-Clause",
            homepage="https://numpy.org",
            dependencies=["setuptools"],
            checksum="sha256:abc123",
        )
        assert pkg.license == "BSD-3-Clause"
        assert pkg.homepage == "https://numpy.org"
        assert pkg.dependencies == ["setuptools"]
        assert pkg.checksum == "sha256:abc123"

    def test_defaults(self):
        pkg = PackageInfo(name="x", version="1.0", source="pypi")
        assert pkg.license is None
        assert pkg.homepage is None
        assert pkg.dependencies == ()
        assert pkg.checksum is None

    def test_frozen(self):
        pkg = PackageInfo(name="x", version="1.0", source="pypi")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            pkg.name = "y"

    def test_frozen_version(self):
        pkg = PackageInfo(name="x", version="1.0", source="pypi")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            pkg.version = "2.0"

    def test_frozen_source(self):
        pkg = PackageInfo(name="x", version="1.0", source="pypi")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            pkg.source = "conda"

    def test_frozen_license(self):
        pkg = PackageInfo(name="x", version="1.0", source="pypi", license="MIT")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            pkg.license = "BSD"

    def test_frozen_homepage(self):
        pkg = PackageInfo(name="x", version="1.0", source="pypi", homepage="http://x.com")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            pkg.homepage = "http://y.com"

    def test_frozen_checksum(self):
        pkg = PackageInfo(name="x", version="1.0", source="pypi", checksum="sha256:abc")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            pkg.checksum = "sha256:def"

    def test_equality(self):
        pkg1 = PackageInfo(name="x", version="1.0", source="pypi")
        pkg2 = PackageInfo(name="x", version="1.0", source="pypi")
        assert pkg1 == pkg2

    def test_inequality_name(self):
        pkg1 = PackageInfo(name="x", version="1.0", source="pypi")
        pkg2 = PackageInfo(name="y", version="1.0", source="pypi")
        assert pkg1 != pkg2

    def test_inequality_version(self):
        pkg1 = PackageInfo(name="x", version="1.0", source="pypi")
        pkg2 = PackageInfo(name="x", version="2.0", source="pypi")
        assert pkg1 != pkg2

    def test_inequality_source(self):
        pkg1 = PackageInfo(name="x", version="1.0", source="pypi")
        pkg2 = PackageInfo(name="x", version="1.0", source="conda")
        assert pkg1 != pkg2

    def test_hash(self):
        pkg1 = PackageInfo(name="x", version="1.0", source="pypi")
        pkg2 = PackageInfo(name="x", version="1.0", source="pypi")
        assert hash(pkg1) == hash(pkg2)

    def test_asdict(self):
        pkg = PackageInfo(
            name="x", version="1.0", source="pypi",
            license="MIT", homepage="http://x.com",
            dependencies=("a",), checksum="sha256:abc",
        )
        d = asdict(pkg)
        assert d["name"] == "x"
        assert d["version"] == "1.0"
        assert d["source"] == "pypi"
        assert d["license"] == "MIT"
        assert d["homepage"] == "http://x.com"
        assert d["dependencies"] == ("a",)
        assert d["checksum"] == "sha256:abc"

    def test_conda_source(self):
        pkg = PackageInfo(name="numpy", version="1.26.0", source="conda")
        assert pkg.source == "conda"

    def test_system_source(self):
        pkg = PackageInfo(name="libssl", version="3.0.2", source="system")
        assert pkg.source == "system"

    def test_multiple_dependencies(self):
        pkg = PackageInfo(
            name="flask", version="3.0.0", source="pypi",
            dependencies=("werkzeug", "jinja2", "click"),
        )
        assert len(pkg.dependencies) == 3
        assert "click" in pkg.dependencies

    def test_empty_name(self):
        pkg = PackageInfo(name="", version="1.0", source="pypi")
        assert pkg.name == ""

    def test_empty_version(self):
        pkg = PackageInfo(name="x", version="", source="pypi")
        assert pkg.version == ""


# ===========================================================================
# EnvironmentManifest - Basic Construction
# ===========================================================================

class TestEnvironmentManifestConstruction:
    def test_basic_creation(self):
        m = _make_manifest()
        assert m.manifest_version == "1.0"
        assert m.generated_by == "sniff"
        assert isinstance(m.generated_at, datetime)

    def test_custom_version(self):
        m = _make_manifest(manifest_version="2.0")
        assert m.manifest_version == "2.0"

    def test_custom_tool_name(self):
        m = _make_manifest(generated_by="my-tool")
        assert m.generated_by == "my-tool"

    def test_with_python_packages(self):
        pkgs = [PackageInfo(name="requests", version="2.31.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        assert len(m.python_packages) == 1
        assert m.python_packages[0].name == "requests"

    def test_with_conda_packages(self):
        pkgs = [PackageInfo(name="numpy", version="1.26.0", source="conda")]
        m = _make_manifest(conda_packages=pkgs)
        assert len(m.conda_packages) == 1
        assert m.conda_packages[0].source == "conda"

    def test_with_system_packages(self):
        pkgs = [PackageInfo(name="libssl", version="3.0.2", source="system")]
        m = _make_manifest(system_packages=pkgs)
        assert len(m.system_packages) == 1
        assert m.system_packages[0].source == "system"

    def test_with_file_checksums(self):
        m = _make_manifest(file_checksums={Path("/tmp/file.py"): "sha256:abc123"})
        assert Path("/tmp/file.py") in m.file_checksums

    def test_empty_packages(self):
        m = _make_manifest()
        assert m.python_packages == []
        assert m.conda_packages == []
        assert m.system_packages == []

    def test_empty_checksums(self):
        m = _make_manifest()
        assert m.file_checksums == {}

    def test_frozen(self):
        m = _make_manifest()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            m.manifest_version = "2.0"

    def test_frozen_generated_at(self):
        m = _make_manifest()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            m.generated_at = datetime.now(timezone.utc)

    def test_frozen_generated_by(self):
        m = _make_manifest()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            m.generated_by = "other"

    def test_frozen_context(self):
        m = _make_manifest()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            m.context = None

    def test_frozen_python_packages(self):
        m = _make_manifest()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            m.python_packages = []

    def test_frozen_file_checksums(self):
        m = _make_manifest()
        with pytest.raises((AttributeError, FrozenInstanceError)):
            m.file_checksums = {}

    def test_context_stored(self):
        ctx = _make_context()
        m = _make_manifest(context=ctx)
        assert m.context is ctx


# ===========================================================================
# EnvironmentManifest.generate()
# ===========================================================================

class TestEnvironmentManifestGenerate:
    @patch("sniff.manifest._detect_python_packages")
    @patch("sniff.manifest._detect_conda_packages")
    @patch("sniff.manifest._detect_system_packages")
    @patch("sniff.manifest._compute_file_checksums")
    @patch("sniff.context.ExecutionContext.capture")
    def test_generate_basic(
        self, mock_capture, mock_checksums, mock_system, mock_conda, mock_python
    ):
        mock_capture.return_value = _make_context()
        mock_python.return_value = [
            PackageInfo(name="pip", version="23.0", source="pypi"),
        ]
        mock_conda.return_value = []
        mock_system.return_value = []
        mock_checksums.return_value = {}

        m = EnvironmentManifest.generate()
        assert m.manifest_version == "1.0"
        assert m.generated_by == "sniff"
        assert len(m.python_packages) == 1
        assert m.python_packages[0].name == "pip"
        mock_capture.assert_called_once()

    @patch("sniff.manifest._detect_python_packages")
    @patch("sniff.manifest._detect_conda_packages")
    @patch("sniff.manifest._detect_system_packages")
    @patch("sniff.context.ExecutionContext.capture")
    def test_generate_custom_tool_name(
        self, mock_capture, mock_system, mock_conda, mock_python
    ):
        mock_capture.return_value = _make_context()
        mock_python.return_value = []
        mock_conda.return_value = []
        mock_system.return_value = []

        m = EnvironmentManifest.generate(tool_name="my-scanner")
        assert m.generated_by == "my-scanner"

    @patch("sniff.manifest._detect_python_packages")
    @patch("sniff.manifest._detect_conda_packages")
    @patch("sniff.manifest._detect_system_packages")
    @patch("sniff.context.ExecutionContext.capture")
    def test_generate_no_system(
        self, mock_capture, mock_system, mock_conda, mock_python
    ):
        mock_capture.return_value = _make_context()
        mock_python.return_value = []
        mock_conda.return_value = []
        mock_system.return_value = [
            PackageInfo(name="libssl", version="3.0", source="system")
        ]

        m = EnvironmentManifest.generate(include_system=False)
        assert m.system_packages == []
        mock_system.assert_not_called()

    @patch("sniff.manifest._detect_python_packages")
    @patch("sniff.manifest._detect_conda_packages")
    @patch("sniff.manifest._detect_system_packages")
    @patch("sniff.context.ExecutionContext.capture")
    def test_generate_no_conda(
        self, mock_capture, mock_system, mock_conda, mock_python
    ):
        mock_capture.return_value = _make_context()
        mock_python.return_value = []
        mock_conda.return_value = [
            PackageInfo(name="numpy", version="1.26", source="conda")
        ]
        mock_system.return_value = []

        m = EnvironmentManifest.generate(include_conda=False)
        assert m.conda_packages == []
        mock_conda.assert_not_called()

    @patch("sniff.manifest._detect_python_packages")
    @patch("sniff.manifest._detect_conda_packages")
    @patch("sniff.manifest._detect_system_packages")
    @patch("sniff.context.ExecutionContext.capture")
    def test_generate_with_checksum_paths(
        self, mock_capture, mock_system, mock_conda, mock_python, tmp_path
    ):
        mock_capture.return_value = _make_context()
        mock_python.return_value = []
        mock_conda.return_value = []
        mock_system.return_value = []

        f = tmp_path / "test.txt"
        f.write_text("hello")

        m = EnvironmentManifest.generate(checksum_paths=[f])
        assert f in m.file_checksums
        assert m.file_checksums[f].startswith("sha256:")

    @patch("sniff.manifest._detect_python_packages")
    @patch("sniff.manifest._detect_conda_packages")
    @patch("sniff.manifest._detect_system_packages")
    @patch("sniff.context.ExecutionContext.capture")
    def test_generate_timestamp(
        self, mock_capture, mock_system, mock_conda, mock_python
    ):
        mock_capture.return_value = _make_context()
        mock_python.return_value = []
        mock_conda.return_value = []
        mock_system.return_value = []

        before = datetime.now(timezone.utc)
        m = EnvironmentManifest.generate()
        after = datetime.now(timezone.utc)
        assert before <= m.generated_at <= after


# ===========================================================================
# to_spdx()
# ===========================================================================

class TestToSpdx:
    def test_empty_manifest(self):
        m = _make_manifest()
        spdx = m.to_spdx()
        assert "SPDXVersion: SPDX-2.3" in spdx
        assert "DataLicense: CC0-1.0" in spdx
        assert "SPDXRef-DOCUMENT" in spdx

    def test_document_name(self):
        m = _make_manifest()
        spdx = m.to_spdx()
        assert "DocumentName: sniff-environment-manifest" in spdx

    def test_creator_tool(self):
        m = _make_manifest(generated_by="my-tool")
        spdx = m.to_spdx()
        assert "Creator: Tool: my-tool" in spdx

    def test_created_timestamp(self):
        dt = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        m = _make_manifest(generated_at=dt)
        spdx = m.to_spdx()
        assert "Created: 2026-03-10T12:00:00Z" in spdx

    def test_python_package(self):
        pkgs = [PackageInfo(name="requests", version="2.31.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        spdx = m.to_spdx()
        assert "PackageName: requests" in spdx
        assert "PackageVersion: 2.31.0" in spdx
        assert "SPDXRef-Package-1" in spdx

    def test_package_with_license(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi", license="MIT")]
        m = _make_manifest(python_packages=pkgs)
        spdx = m.to_spdx()
        assert "PackageLicenseConcluded: MIT" in spdx

    def test_package_without_license(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        spdx = m.to_spdx()
        assert "PackageLicenseConcluded: NOASSERTION" in spdx

    def test_package_with_homepage(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi", homepage="http://x.com")]
        m = _make_manifest(python_packages=pkgs)
        spdx = m.to_spdx()
        assert "PackageHomePage: http://x.com" in spdx

    def test_package_with_checksum(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi", checksum="sha256:abcdef")]
        m = _make_manifest(python_packages=pkgs)
        spdx = m.to_spdx()
        assert "PackageChecksum: SHA256: abcdef" in spdx

    def test_source_comment(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="conda")]
        m = _make_manifest(conda_packages=pkgs)
        spdx = m.to_spdx()
        assert "PackageComment: source=conda" in spdx

    def test_multiple_packages_numbering(self):
        pkgs = [
            PackageInfo(name="a", version="1.0", source="pypi"),
            PackageInfo(name="b", version="2.0", source="pypi"),
        ]
        m = _make_manifest(python_packages=pkgs)
        spdx = m.to_spdx()
        assert "SPDXRef-Package-1" in spdx
        assert "SPDXRef-Package-2" in spdx

    def test_combined_packages_in_spdx(self):
        m = _make_manifest(
            python_packages=[PackageInfo(name="pip", version="1.0", source="pypi")],
            conda_packages=[PackageInfo(name="numpy", version="2.0", source="conda")],
            system_packages=[PackageInfo(name="libc", version="3.0", source="system")],
        )
        spdx = m.to_spdx()
        assert "PackageName: pip" in spdx
        assert "PackageName: numpy" in spdx
        assert "PackageName: libc" in spdx

    def test_files_analyzed_false(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        spdx = m.to_spdx()
        assert "FilesAnalyzed: false" in spdx

    def test_namespace_is_unique(self):
        m = _make_manifest()
        spdx1 = m.to_spdx()
        spdx2 = m.to_spdx()
        # Each call generates a unique namespace
        ns1 = [l for l in spdx1.splitlines() if "DocumentNamespace:" in l][0]
        ns2 = [l for l in spdx2.splitlines() if "DocumentNamespace:" in l][0]
        assert ns1 != ns2

    def test_returns_string(self):
        m = _make_manifest()
        assert isinstance(m.to_spdx(), str)


# ===========================================================================
# to_cyclonedx()
# ===========================================================================

class TestToCyclonedx:
    def test_empty_manifest(self):
        m = _make_manifest()
        cdx = json.loads(m.to_cyclonedx())
        assert cdx["bomFormat"] == "CycloneDX"
        assert cdx["specVersion"] == "1.5"
        assert cdx["components"] == []

    def test_metadata_timestamp(self):
        dt = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        m = _make_manifest(generated_at=dt)
        cdx = json.loads(m.to_cyclonedx())
        assert cdx["metadata"]["timestamp"] == "2026-03-10T12:00:00Z"

    def test_metadata_tool(self):
        m = _make_manifest(generated_by="my-tool")
        cdx = json.loads(m.to_cyclonedx())
        tools = cdx["metadata"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "my-tool"

    def test_python_package_component(self):
        pkgs = [PackageInfo(name="requests", version="2.31.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        assert len(cdx["components"]) == 1
        comp = cdx["components"][0]
        assert comp["type"] == "library"
        assert comp["name"] == "requests"
        assert comp["version"] == "2.31.0"

    def test_purl_pypi(self):
        pkgs = [PackageInfo(name="requests", version="2.31.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        assert cdx["components"][0]["purl"] == "pkg:pypi/requests@2.31.0"

    def test_purl_conda(self):
        pkgs = [PackageInfo(name="numpy", version="1.26.0", source="conda")]
        m = _make_manifest(conda_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        assert cdx["components"][0]["purl"] == "pkg:conda/numpy@1.26.0"

    def test_license_in_component(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi", license="MIT")]
        m = _make_manifest(python_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        comp = cdx["components"][0]
        assert "licenses" in comp
        assert comp["licenses"][0]["license"]["name"] == "MIT"

    def test_no_license_field_when_none(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        assert "licenses" not in cdx["components"][0]

    def test_homepage_external_ref(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi", homepage="http://x.com")]
        m = _make_manifest(python_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        comp = cdx["components"][0]
        assert "externalReferences" in comp
        assert comp["externalReferences"][0]["url"] == "http://x.com"

    def test_no_homepage_field_when_none(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        assert "externalReferences" not in cdx["components"][0]

    def test_checksum_in_component(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi", checksum="sha256:abc")]
        m = _make_manifest(python_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        comp = cdx["components"][0]
        assert "hashes" in comp
        assert comp["hashes"][0]["alg"] == "SHA256"
        assert comp["hashes"][0]["content"] == "abc"

    def test_dependencies_as_property(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi", dependencies=("a", "b"))]
        m = _make_manifest(python_packages=pkgs)
        cdx = json.loads(m.to_cyclonedx())
        comp = cdx["components"][0]
        assert "properties" in comp
        prop = comp["properties"][0]
        assert prop["name"] == "sniff:dependencies"
        assert prop["value"] == "a,b"

    def test_valid_json(self):
        m = _make_manifest(
            python_packages=[PackageInfo(name="a", version="1.0", source="pypi")],
        )
        raw = m.to_cyclonedx()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_returns_string(self):
        m = _make_manifest()
        assert isinstance(m.to_cyclonedx(), str)

    def test_combined_packages(self):
        m = _make_manifest(
            python_packages=[PackageInfo(name="pip", version="1.0", source="pypi")],
            conda_packages=[PackageInfo(name="numpy", version="2.0", source="conda")],
            system_packages=[PackageInfo(name="libc", version="3.0", source="system")],
        )
        cdx = json.loads(m.to_cyclonedx())
        assert len(cdx["components"]) == 3

    def test_version_field(self):
        m = _make_manifest()
        cdx = json.loads(m.to_cyclonedx())
        assert cdx["version"] == 1


# ===========================================================================
# validate_checksums()
# ===========================================================================

class TestValidateChecksums:
    def test_empty_checksums(self):
        m = _make_manifest()
        assert m.validate_checksums() == []

    def test_valid_checksum(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        digest = hashlib.sha256(b"hello").hexdigest()
        m = _make_manifest(file_checksums={f: f"sha256:{digest}"})
        assert m.validate_checksums() == []

    def test_invalid_checksum(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        m = _make_manifest(file_checksums={f: "sha256:wrong"})
        mismatches = m.validate_checksums()
        assert len(mismatches) == 1
        assert "wrong" in mismatches[0]

    def test_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent.txt"
        m = _make_manifest(file_checksums={f: "sha256:abc"})
        mismatches = m.validate_checksums()
        assert len(mismatches) == 1
        assert "not found" in mismatches[0]

    def test_md5_checksum(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        digest = hashlib.md5(b"hello").hexdigest()
        m = _make_manifest(file_checksums={f: f"md5:{digest}"})
        assert m.validate_checksums() == []

    def test_sha1_checksum(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        digest = hashlib.sha1(b"hello").hexdigest()
        m = _make_manifest(file_checksums={f: f"sha1:{digest}"})
        assert m.validate_checksums() == []

    def test_unsupported_algorithm(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        m = _make_manifest(file_checksums={f: "blake2:abc"})
        mismatches = m.validate_checksums()
        assert len(mismatches) == 1
        assert "unsupported" in mismatches[0]

    def test_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("aaa")
        f2.write_text("bbb")
        d1 = hashlib.sha256(b"aaa").hexdigest()
        d2 = hashlib.sha256(b"bbb").hexdigest()
        m = _make_manifest(file_checksums={f1: f"sha256:{d1}", f2: f"sha256:{d2}"})
        assert m.validate_checksums() == []

    def test_mixed_valid_invalid(self, tmp_path):
        f1 = tmp_path / "good.txt"
        f2 = tmp_path / "bad.txt"
        f1.write_text("good")
        f2.write_text("bad")
        d1 = hashlib.sha256(b"good").hexdigest()
        m = _make_manifest(file_checksums={f1: f"sha256:{d1}", f2: "sha256:wrong"})
        mismatches = m.validate_checksums()
        assert len(mismatches) == 1

    def test_directory_not_file(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        m = _make_manifest(file_checksums={d: "sha256:abc"})
        mismatches = m.validate_checksums()
        assert len(mismatches) == 1
        assert "not a regular file" in mismatches[0]

    def test_bare_checksum_defaults_to_sha256(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        digest = hashlib.sha256(b"data").hexdigest()
        m = _make_manifest(file_checksums={f: digest})
        assert m.validate_checksums() == []

    def test_returns_list(self):
        m = _make_manifest()
        result = m.validate_checksums()
        assert isinstance(result, list)


# ===========================================================================
# to_dict()
# ===========================================================================

class TestToDict:
    def test_basic_fields(self):
        m = _make_manifest()
        d = m.to_dict()
        assert d["manifest_version"] == "1.0"
        assert d["generated_by"] == "sniff"
        assert "generated_at" in d

    def test_packages_in_dict(self):
        pkgs = [PackageInfo(name="x", version="1.0", source="pypi")]
        m = _make_manifest(python_packages=pkgs)
        d = m.to_dict()
        assert len(d["python_packages"]) == 1
        assert d["python_packages"][0]["name"] == "x"

    def test_empty_packages(self):
        m = _make_manifest()
        d = m.to_dict()
        assert d["python_packages"] == []
        assert d["conda_packages"] == []
        assert d["system_packages"] == []

    def test_file_checksums_stringified(self):
        m = _make_manifest(file_checksums={Path("/tmp/f.py"): "sha256:abc"})
        d = m.to_dict()
        assert "/tmp/f.py" in d["file_checksums"]
        assert d["file_checksums"]["/tmp/f.py"] == "sha256:abc"

    def test_context_with_to_dict(self):
        ctx = _make_context()
        ctx.to_dict.return_value = {"os": "linux"}
        m = _make_manifest(context=ctx)
        d = m.to_dict()
        assert d["context"] == {"os": "linux"}

    def test_json_serializable(self):
        m = _make_manifest(
            python_packages=[PackageInfo(name="x", version="1.0", source="pypi")],
        )
        d = m.to_dict()
        raw = json.dumps(d)
        assert isinstance(raw, str)

    def test_generated_at_is_iso_string(self):
        dt = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
        m = _make_manifest(generated_at=dt)
        d = m.to_dict()
        assert d["generated_at"] == "2026-03-10T12:00:00+00:00"


# ===========================================================================
# _detect_python_packages()
# ===========================================================================

class TestDetectPythonPackages:
    def test_returns_list(self):
        result = _detect_python_packages()
        assert isinstance(result, list)

    def test_packages_are_packageinfo(self):
        result = _detect_python_packages()
        for pkg in result:
            assert isinstance(pkg, PackageInfo)

    def test_packages_have_pypi_source(self):
        result = _detect_python_packages()
        for pkg in result:
            assert pkg.source == "pypi"

    def test_detects_pip(self):
        # pip should always be installed in a test environment
        result = _detect_python_packages()
        names = [p.name.lower() for p in result]
        assert "pip" in names

    def test_sorted_by_name(self):
        result = _detect_python_packages()
        names = [p.name.lower() for p in result]
        assert names == sorted(names)

    def test_import_error_returns_empty(self):
        # Temporarily hide importlib.metadata to trigger ImportError
        import importlib.metadata as im
        with patch.dict(sys.modules, {"importlib.metadata": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                result = _detect_python_packages()
        assert isinstance(result, list)
        assert result == []


# ===========================================================================
# _detect_conda_packages()
# ===========================================================================

class TestDetectCondaPackages:
    def test_no_conda_prefix_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            result = _detect_conda_packages()
            assert result == []

    @patch("subprocess.run")
    def test_conda_list_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"name": "numpy", "version": "1.26.0", "channel": "defaults"},
                {"name": "scipy", "version": "1.11.0", "channel": "conda-forge"},
            ]),
        )
        with patch.dict(os.environ, {"CONDA_PREFIX": "/opt/conda"}):
            result = _detect_conda_packages()
        assert len(result) == 2
        assert all(p.source == "conda" for p in result)

    @patch("subprocess.run")
    def test_conda_list_failure_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with patch.dict(os.environ, {"CONDA_PREFIX": "/opt/conda"}):
            result = _detect_conda_packages()
        assert result == []

    @patch("subprocess.run")
    def test_conda_timeout_returns_empty(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("conda", 30)
        with patch.dict(os.environ, {"CONDA_PREFIX": "/opt/conda"}):
            result = _detect_conda_packages()
        assert result == []

    @patch("subprocess.run")
    def test_conda_invalid_json_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        with patch.dict(os.environ, {"CONDA_PREFIX": "/opt/conda"}):
            result = _detect_conda_packages()
        assert result == []

    @patch("subprocess.run")
    def test_conda_sorted_results(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"name": "scipy", "version": "1.0", "channel": "defaults"},
                {"name": "numpy", "version": "1.0", "channel": "defaults"},
            ]),
        )
        with patch.dict(os.environ, {"CONDA_PREFIX": "/opt/conda"}):
            result = _detect_conda_packages()
        assert result[0].name == "numpy"
        assert result[1].name == "scipy"

    @patch("subprocess.run")
    def test_skips_entries_without_name(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"version": "1.0", "channel": "defaults"},
                {"name": "numpy", "version": "1.0", "channel": "defaults"},
            ]),
        )
        with patch.dict(os.environ, {"CONDA_PREFIX": "/opt/conda"}):
            result = _detect_conda_packages()
        assert len(result) == 1


# ===========================================================================
# _detect_system_packages()
# ===========================================================================

class TestDetectSystemPackages:
    @patch("sniff.manifest.platform.system", return_value="Linux")
    @patch("sniff.manifest._detect_linux_system_packages")
    def test_linux_dispatches(self, mock_linux, mock_system):
        mock_linux.return_value = [PackageInfo(name="libc", version="2.31", source="system")]
        result = _detect_system_packages()
        mock_linux.assert_called_once()
        assert len(result) == 1

    @patch("sniff.manifest.platform.system", return_value="Darwin")
    @patch("sniff.manifest._detect_macos_system_packages")
    def test_macos_dispatches(self, mock_macos, mock_system):
        mock_macos.return_value = [PackageInfo(name="openssl", version="3.0", source="system")]
        result = _detect_system_packages()
        mock_macos.assert_called_once()

    @patch("sniff.manifest.platform.system", return_value="Windows")
    def test_windows_returns_empty(self, mock_system):
        result = _detect_system_packages()
        assert result == []

    def test_returns_list(self):
        result = _detect_system_packages()
        assert isinstance(result, list)


class TestDetectLinuxSystemPackages:
    @patch("subprocess.run")
    def test_dpkg_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="libc6\t2.31-13\nlibssl3\t3.0.2-0ubuntu1\n",
        )
        result = _detect_linux_system_packages()
        assert len(result) == 2
        assert result[0].name == "libc6"
        assert result[0].version == "2.31-13"
        assert result[0].source == "system"

    @patch("subprocess.run")
    def test_dpkg_failure_falls_through_to_rpm(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "dpkg-query" in cmd:
                return MagicMock(returncode=1, stdout="")
            elif "rpm" in cmd:
                return MagicMock(returncode=0, stdout="glibc\t2.28\n")
            return MagicMock(returncode=1, stdout="")

        mock_run.side_effect = side_effect
        result = _detect_linux_system_packages()
        assert len(result) == 1
        assert result[0].name == "glibc"

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_no_package_manager_returns_empty(self, mock_run):
        result = _detect_linux_system_packages()
        assert result == []


class TestDetectMacosSystemPackages:
    @patch("subprocess.run")
    def test_brew_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="openssl 3.1.4\npython 3.12.0\n",
        )
        result = _detect_macos_system_packages()
        assert len(result) == 2
        assert result[0].name == "openssl"

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_no_brew_returns_empty(self, mock_run):
        result = _detect_macos_system_packages()
        assert result == []


# ===========================================================================
# _compute_file_checksums()
# ===========================================================================

class TestComputeFileChecksums:
    def test_empty_list(self):
        result = _compute_file_checksums([])
        assert result == {}

    def test_single_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = _compute_file_checksums([f])
        assert f in result
        expected = "sha256:" + hashlib.sha256(b"hello").hexdigest()
        assert result[f] == expected

    def test_nonexistent_file_skipped(self, tmp_path):
        f = tmp_path / "missing.txt"
        result = _compute_file_checksums([f])
        assert result == {}

    def test_directory_skipped(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        result = _compute_file_checksums([d])
        assert result == {}

    def test_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("aaa")
        f2.write_text("bbb")
        result = _compute_file_checksums([f1, f2])
        assert len(result) == 2
        assert f1 in result
        assert f2 in result


# ===========================================================================
# _make_purl()
# ===========================================================================

class TestMakePurl:
    def test_pypi_purl(self):
        pkg = PackageInfo(name="requests", version="2.31.0", source="pypi")
        assert _make_purl(pkg) == "pkg:pypi/requests@2.31.0"

    def test_conda_purl(self):
        pkg = PackageInfo(name="numpy", version="1.26.0", source="conda")
        assert _make_purl(pkg) == "pkg:conda/numpy@1.26.0"

    def test_system_purl(self):
        pkg = PackageInfo(name="libc", version="2.31", source="system")
        purl = _make_purl(pkg)
        assert purl.startswith("pkg:generic/libc@2.31")
        assert "platform=" in purl
