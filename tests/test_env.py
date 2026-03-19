"""Tests for dekk.env -- EnvSnapshot and EnvVarBuilder."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from dekk.env import EnvSnapshot, EnvVarBuilder


# ---------------------------------------------------------------------------
# EnvSnapshot
# ---------------------------------------------------------------------------


class TestEnvSnapshot:
    def test_frozen(self):
        snap = EnvSnapshot(vars=(("A", "1"),))
        with pytest.raises(AttributeError):
            snap.vars = ()  # type: ignore[misc]

    def test_from_dict(self):
        snap = EnvSnapshot.from_dict({"B": "2", "A": "1"})
        assert snap.get("A") == "1"
        assert snap.get("B") == "2"
        # Vars are sorted by name
        assert snap.vars == (("A", "1"), ("B", "2"))

    def test_capture(self):
        with patch.dict(os.environ, {"SNIFF_TEST_VAR": "hello"}, clear=False):
            snap = EnvSnapshot.capture()
            assert snap.get("SNIFF_TEST_VAR") == "hello"

    def test_get_missing(self):
        snap = EnvSnapshot(vars=(("A", "1"),))
        assert snap.get("MISSING") is None
        assert snap.get("MISSING", "default") == "default"

    def test_to_dict(self):
        snap = EnvSnapshot(vars=(("X", "10"), ("Y", "20")))
        d = snap.to_dict()
        assert d == {"X": "10", "Y": "20"}

    def test_contains(self):
        snap = EnvSnapshot(vars=(("HOME", "/root"),))
        assert "HOME" in snap
        assert "MISSING" not in snap

    def test_len(self):
        snap = EnvSnapshot(vars=(("A", "1"), ("B", "2"), ("C", "3")))
        assert len(snap) == 3

    def test_empty(self):
        snap = EnvSnapshot()
        assert len(snap) == 0
        assert snap.to_dict() == {}

    def test_names(self):
        snap = EnvSnapshot(vars=(("B", "2"), ("A", "1")))
        assert snap.names() == ("B", "A")

    def test_from_dict_sorted(self):
        snap = EnvSnapshot.from_dict({"Z": "z", "A": "a", "M": "m"})
        assert snap.names() == ("A", "M", "Z")

    def test_hashable(self):
        snap = EnvSnapshot(vars=(("A", "1"),))
        # Frozen dataclass -> usable as dict key
        d = {snap: "value"}
        assert d[snap] == "value"


# ---------------------------------------------------------------------------
# EnvVarBuilder
# ---------------------------------------------------------------------------


class TestEnvVarBuilder:
    def test_set(self):
        snap = EnvVarBuilder().set("CC", "gcc").build()
        assert snap.get("CC") == "gcc"

    def test_set_overwrite(self):
        snap = (
            EnvVarBuilder()
            .set("CC", "gcc")
            .set("CC", "clang")
            .build()
        )
        assert snap.get("CC") == "clang"

    def test_set_default(self):
        snap = (
            EnvVarBuilder()
            .set("CC", "gcc")
            .set_default("CC", "clang")  # should NOT overwrite
            .set_default("CXX", "g++")  # should set
            .build()
        )
        assert snap.get("CC") == "gcc"
        assert snap.get("CXX") == "g++"

    def test_set_default_after_unset(self):
        snap = (
            EnvVarBuilder()
            .set("CC", "gcc")
            .unset("CC")
            .set_default("CC", "clang")  # should NOT set because unset is sticky
            .build()
        )
        assert snap.get("CC") is None

    def test_set_from_path(self):
        snap = (
            EnvVarBuilder()
            .set_from_path("PATH", ["/usr/bin", "/bin"])
            .build()
        )
        value = snap.get("PATH")
        assert value is not None
        assert "/usr/bin" in value
        assert "/bin" in value

    def test_set_from_path_custom_sep(self):
        snap = (
            EnvVarBuilder()
            .set_from_path("INCLUDE", ["/inc/a", "/inc/b"], sep=";")
            .build()
        )
        assert snap.get("INCLUDE") == "/inc/a;/inc/b"

    def test_set_from_path_with_pathlib(self):
        from pathlib import Path
        snap = (
            EnvVarBuilder()
            .set_from_path("LIB", [Path("/opt/lib"), Path("/usr/lib")])
            .build()
        )
        value = snap.get("LIB")
        assert value is not None
        assert "/opt/lib" in value
        assert "/usr/lib" in value

    def test_unset(self):
        snap = (
            EnvVarBuilder()
            .set("CC", "gcc")
            .set("CXX", "g++")
            .unset("CC")
            .build()
        )
        assert snap.get("CC") is None
        assert snap.get("CXX") == "g++"

    def test_set_after_unset(self):
        snap = (
            EnvVarBuilder()
            .set("CC", "gcc")
            .unset("CC")
            .set("CC", "clang")  # explicit set overrides unset
            .build()
        )
        assert snap.get("CC") == "clang"

    def test_merge_builder(self):
        base = EnvVarBuilder().set("CC", "gcc").set("JOBS", "4")
        overlay = EnvVarBuilder().set("CC", "clang").set("CXX", "clang++")
        # overlay.merge(base) -- base fills in gaps
        result = overlay.merge(base).build()
        assert result.get("CC") == "clang"  # overlay wins
        assert result.get("CXX") == "clang++"
        assert result.get("JOBS") == "4"  # filled in from base

    def test_merge_snapshot(self):
        snap = EnvSnapshot.from_dict({"A": "1", "B": "2"})
        result = EnvVarBuilder().set("A", "override").merge(snap).build()
        assert result.get("A") == "override"
        assert result.get("B") == "2"

    def test_merge_dict(self):
        result = (
            EnvVarBuilder()
            .set("X", "1")
            .merge({"X": "2", "Y": "3"})
            .build()
        )
        assert result.get("X") == "1"  # existing wins
        assert result.get("Y") == "3"

    def test_merge_respects_unset(self):
        base = EnvVarBuilder().set("CC", "gcc")
        result = EnvVarBuilder().unset("CC").merge(base).build()
        assert result.get("CC") is None

    def test_to_dict(self):
        d = EnvVarBuilder().set("A", "1").set("B", "2").to_dict()
        assert d == {"A": "1", "B": "2"}

    def test_chaining(self):
        snap = (
            EnvVarBuilder()
            .set("A", "1")
            .set("B", "2")
            .set_default("C", "3")
            .set_from_path("PATH", ["/bin"])
            .unset("B")
            .build()
        )
        assert snap.get("A") == "1"
        assert snap.get("B") is None
        assert snap.get("C") == "3"
        assert snap.get("PATH") is not None

    def test_build_produces_sorted_vars(self):
        snap = (
            EnvVarBuilder()
            .set("Z", "z")
            .set("A", "a")
            .set("M", "m")
            .build()
        )
        assert snap.names() == ("A", "M", "Z")

    def test_empty_builder(self):
        snap = EnvVarBuilder().build()
        assert len(snap) == 0


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


class TestEnvIntegration:
    def test_capture_modify_rebuild(self):
        """Capture live env, overlay modifications, build new snapshot."""
        with patch.dict(os.environ, {"SNIFF_INT_TEST": "original"}, clear=False):
            base = EnvSnapshot.capture()
            result = (
                EnvVarBuilder()
                .set("SNIFF_INT_TEST", "modified")
                .set("NEW_VAR", "new_value")
                .merge(base)
                .build()
            )
            assert result.get("SNIFF_INT_TEST") == "modified"
            assert result.get("NEW_VAR") == "new_value"
            # PATH should be carried over from the captured env
            assert result.get("PATH") is not None

    def test_top_level_import(self):
        """EnvSnapshot is importable from the top-level dekk package."""
        from dekk import EnvSnapshot as ES
        assert ES is EnvSnapshot

    def test_direct_module_import(self):
        """Both types are importable from dekk.env."""
        from dekk.env import EnvSnapshot as ES, EnvVarBuilder as EVB
        assert ES is EnvSnapshot
        assert EVB is EnvVarBuilder


# ---------------------------------------------------------------------------
# Cross-module: env + toolchain
# ---------------------------------------------------------------------------


class TestEnvToolchainIntegration:
    """Tests combining dekk.env and dekk.toolchain modules."""

    def test_toolchain_env_dict_into_env_builder(self):
        """Toolchain's to_env_dict can be merged into an env.EnvVarBuilder."""
        from dekk.toolchain import CondaToolchain, CMakeToolchain
        from dekk.toolchain import EnvVarBuilder as TcBuilder
        from pathlib import Path

        prefix = Path("/opt/conda/envs/apxm")
        tc_builder = TcBuilder()
        CondaToolchain(prefix=prefix, env_name="apxm").configure(tc_builder)
        CMakeToolchain(prefix=prefix).configure(tc_builder)
        tc_env = tc_builder.to_env_dict()

        # Merge toolchain env into an env.EnvVarBuilder snapshot
        env_builder = EnvVarBuilder()
        env_builder.set("CUSTOM", "value")
        result = env_builder.merge(tc_env).build()

        assert result.get("CUSTOM") == "value"
        assert result.get("CONDA_PREFIX") == str(prefix)
        assert result.get("MLIR_DIR") is not None

    def test_env_snapshot_as_toolchain_base(self):
        """EnvSnapshot can be merged with toolchain overrides."""
        from dekk.toolchain import CondaToolchain
        from dekk.toolchain import EnvVarBuilder as TcBuilder
        from pathlib import Path

        # Simulate captured env
        base = EnvSnapshot.from_dict({"HOME": "/home/user", "LANG": "en_US.UTF-8"})

        # Build toolchain env dict
        prefix = Path("/opt/conda/envs/apxm")
        tc_builder = TcBuilder()
        CondaToolchain(prefix=prefix, env_name="apxm").configure(tc_builder)
        tc_env = tc_builder.to_env_dict()

        # Merge: toolchain takes priority, base fills gaps
        result = EnvVarBuilder().merge(tc_env).merge(base).build()
        assert result.get("CONDA_PREFIX") == str(prefix)
        assert result.get("HOME") == "/home/user"
        assert result.get("LANG") == "en_US.UTF-8"


# ---------------------------------------------------------------------------
# Cross-module: env + libpath
# ---------------------------------------------------------------------------


class TestEnvLibpathIntegration:
    """Tests combining dekk.env and dekk.libpath modules."""

    def test_libpath_to_env_var_into_builder(self):
        """LibraryPathResolver.to_env_var() integrates with env.EnvVarBuilder."""
        from dekk.libpath import LibraryPathResolver

        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/opt/lib", "/usr/local/lib")

        with patch.dict(os.environ, {}, clear=True):
            name, value = resolver.to_env_var()

        result = EnvVarBuilder().set(name, value).build()
        assert result.get("LD_LIBRARY_PATH") is not None
        assert "/opt/lib" in result.get("LD_LIBRARY_PATH", "")

    def test_env_snapshot_capture_includes_lib_path(self):
        """After libpath.apply(), the captured snapshot has the var."""
        from dekk.libpath import LibraryPathResolver

        resolver = LibraryPathResolver.for_platform("Linux")
        resolver.prepend("/snapshot/test/lib")

        with patch.dict(os.environ, {}, clear=True):
            resolver.apply()
            snap = EnvSnapshot.capture()

        assert snap.get("LD_LIBRARY_PATH") is not None
        assert "/snapshot/test/lib" in snap.get("LD_LIBRARY_PATH", "")
