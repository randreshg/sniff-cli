"""Tests for version constraint parsing and resolution."""

import pytest

from dekk.core.version import (
    ConstraintOp,
    Version,
    VersionConstraint,
    VersionSpec,
    compare_versions,
    version_satisfies,
)

# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------


class TestVersionParsing:
    def test_simple_semver(self):
        v = Version.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert v.pre is None
        assert v.build is None

    def test_two_part(self):
        v = Version.parse("1.80")
        assert v == Version(1, 80, 0)

    def test_one_part(self):
        v = Version.parse("21")
        assert v == Version(21, 0, 0)

    def test_v_prefix(self):
        v = Version.parse("v1.2.3")
        assert v == Version(1, 2, 3)

    def test_pre_release(self):
        v = Version.parse("1.0.0-beta.1")
        assert v.pre == "beta.1"

    def test_build_metadata(self):
        v = Version.parse("1.0.0+build42")
        assert v.build == "build42"

    def test_pre_and_build(self):
        v = Version.parse("1.0.0-rc.1+20240101")
        assert v.pre == "rc.1"
        assert v.build == "20240101"

    def test_invalid(self):
        with pytest.raises(ValueError):
            Version.parse("not-a-version")

    def test_try_parse_success(self):
        assert Version.try_parse("1.2.3") == Version(1, 2, 3)

    def test_try_parse_failure(self):
        assert Version.try_parse("bad") is None

    def test_str(self):
        assert str(Version(1, 2, 3)) == "1.2.3"
        assert str(Version(1, 0, 0, pre="alpha")) == "1.0.0-alpha"
        assert str(Version(1, 0, 0, build="b1")) == "1.0.0+b1"


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


class TestVersionComparison:
    def test_equal(self):
        assert Version(1, 2, 3) == Version(1, 2, 3)

    def test_less_than_major(self):
        assert Version(1, 0, 0) < Version(2, 0, 0)

    def test_less_than_minor(self):
        assert Version(1, 2, 0) < Version(1, 3, 0)

    def test_less_than_patch(self):
        assert Version(1, 2, 3) < Version(1, 2, 4)

    def test_greater_than(self):
        assert Version(2, 0, 0) > Version(1, 99, 99)

    def test_pre_release_before_release(self):
        assert Version(1, 0, 0, pre="alpha") < Version(1, 0, 0)

    def test_pre_release_ordering(self):
        assert Version(1, 0, 0, pre="alpha") < Version(1, 0, 0, pre="beta")

    def test_numeric_pre_release(self):
        assert Version(1, 0, 0, pre="1") < Version(1, 0, 0, pre="2")

    def test_mixed_pre_release_numeric_vs_string(self):
        # Numeric segments sort before string segments (per semver spec)
        assert Version(1, 0, 0, pre="1") < Version(1, 0, 0, pre="alpha")

    def test_mixed_pre_release_no_type_error(self):
        # Must not raise TypeError when comparing int vs str pre-release segments
        v1 = Version.parse("1.0.0-1")
        v2 = Version.parse("1.0.0-alpha")
        assert v1 < v2
        assert v2 > v1
        assert v1 != v2

    def test_gte(self):
        assert Version(1, 80, 0) >= Version(1, 80, 0)
        assert Version(1, 81, 0) >= Version(1, 80, 0)

    def test_lte(self):
        assert Version(1, 80, 0) <= Version(1, 80, 0)
        assert Version(1, 79, 0) <= Version(1, 80, 0)

    def test_hash_equality(self):
        v1 = Version(1, 2, 3)
        v2 = Version(1, 2, 3)
        assert hash(v1) == hash(v2)
        assert {v1} == {v2}

    def test_sorting(self):
        versions = [
            Version(2, 0, 0),
            Version(1, 0, 0),
            Version(1, 0, 0, pre="alpha"),
            Version(1, 1, 0),
        ]
        assert sorted(versions) == [
            Version(1, 0, 0, pre="alpha"),
            Version(1, 0, 0),
            Version(1, 1, 0),
            Version(2, 0, 0),
        ]


# ---------------------------------------------------------------------------
# Version utility methods
# ---------------------------------------------------------------------------


class TestVersionUtility:
    def test_base(self):
        v = Version(1, 2, 3, pre="alpha", build="b1")
        assert v.base == Version(1, 2, 3)

    def test_bump_major(self):
        assert Version(1, 2, 3).bump_major() == Version(2, 0, 0)

    def test_bump_minor(self):
        assert Version(1, 2, 3).bump_minor() == Version(1, 3, 0)

    def test_bump_patch(self):
        assert Version(1, 2, 3).bump_patch() == Version(1, 2, 4)


# ---------------------------------------------------------------------------
# VersionConstraint
# ---------------------------------------------------------------------------


class TestVersionConstraint:
    def test_eq(self):
        c = VersionConstraint(ConstraintOp.EQ, Version(1, 2, 3))
        assert c.satisfied_by(Version(1, 2, 3))
        assert not c.satisfied_by(Version(1, 2, 4))

    def test_neq(self):
        c = VersionConstraint(ConstraintOp.NEQ, Version(1, 0, 0))
        assert c.satisfied_by(Version(1, 0, 1))
        assert not c.satisfied_by(Version(1, 0, 0))

    def test_gte(self):
        c = VersionConstraint(ConstraintOp.GTE, Version(1, 80, 0))
        assert c.satisfied_by(Version(1, 80, 0))
        assert c.satisfied_by(Version(1, 81, 0))
        assert not c.satisfied_by(Version(1, 79, 0))

    def test_gt(self):
        c = VersionConstraint(ConstraintOp.GT, Version(2, 0, 0))
        assert c.satisfied_by(Version(2, 0, 1))
        assert not c.satisfied_by(Version(2, 0, 0))

    def test_lte(self):
        c = VersionConstraint(ConstraintOp.LTE, Version(3, 0, 0))
        assert c.satisfied_by(Version(3, 0, 0))
        assert c.satisfied_by(Version(2, 99, 0))
        assert not c.satisfied_by(Version(3, 0, 1))

    def test_lt(self):
        c = VersionConstraint(ConstraintOp.LT, Version(4, 0, 0))
        assert c.satisfied_by(Version(3, 99, 99))
        assert not c.satisfied_by(Version(4, 0, 0))

    def test_compat_two_part(self):
        # ~=3.11 -> >=3.11.0, <4.0.0
        c = VersionConstraint(ConstraintOp.COMPAT, Version.parse("3.11"))
        assert c.satisfied_by(Version(3, 11, 0))
        assert c.satisfied_by(Version(3, 12, 0))
        assert c.satisfied_by(Version(3, 99, 0))
        assert not c.satisfied_by(Version(4, 0, 0))
        assert not c.satisfied_by(Version(3, 10, 0))

    def test_compat_three_part(self):
        # ~=1.2.3 -> >=1.2.3, <1.3.0
        c = VersionConstraint(ConstraintOp.COMPAT, Version(1, 2, 3))
        assert c.satisfied_by(Version(1, 2, 3))
        assert c.satisfied_by(Version(1, 2, 9))
        assert not c.satisfied_by(Version(1, 3, 0))

    def test_compat_three_part_patch_zero(self):
        # ~=3.11.0 -> >=3.11.0, <3.12.0  (NOT <4.0.0)
        c = VersionConstraint(ConstraintOp.COMPAT, Version.parse("3.11.0"))
        assert c.satisfied_by(Version(3, 11, 0))
        assert c.satisfied_by(Version(3, 11, 5))
        assert not c.satisfied_by(Version(3, 12, 0))
        assert not c.satisfied_by(Version(4, 0, 0))

    def test_tilde(self):
        # ~1.2.3 -> >=1.2.3, <1.3.0
        c = VersionConstraint(ConstraintOp.TILDE, Version(1, 2, 3))
        assert c.satisfied_by(Version(1, 2, 3))
        assert c.satisfied_by(Version(1, 2, 99))
        assert not c.satisfied_by(Version(1, 3, 0))

    def test_caret_major(self):
        # ^1.2.3 -> >=1.2.3, <2.0.0
        c = VersionConstraint(ConstraintOp.CARET, Version(1, 2, 3))
        assert c.satisfied_by(Version(1, 2, 3))
        assert c.satisfied_by(Version(1, 99, 99))
        assert not c.satisfied_by(Version(2, 0, 0))

    def test_caret_zero_major(self):
        # ^0.2.3 -> >=0.2.3, <0.3.0
        c = VersionConstraint(ConstraintOp.CARET, Version(0, 2, 3))
        assert c.satisfied_by(Version(0, 2, 3))
        assert c.satisfied_by(Version(0, 2, 99))
        assert not c.satisfied_by(Version(0, 3, 0))

    def test_caret_zero_zero(self):
        # ^0.0.3 -> >=0.0.3, <0.0.4
        c = VersionConstraint(ConstraintOp.CARET, Version(0, 0, 3))
        assert c.satisfied_by(Version(0, 0, 3))
        assert not c.satisfied_by(Version(0, 0, 4))

    def test_str(self):
        c = VersionConstraint(ConstraintOp.GTE, Version(1, 80, 0))
        assert str(c) == ">=1.80.0"


# ---------------------------------------------------------------------------
# VersionSpec
# ---------------------------------------------------------------------------


class TestVersionSpec:
    def test_parse_gte(self):
        spec = VersionSpec.parse(">=1.80")
        assert spec.satisfied_by("1.80.0")
        assert spec.satisfied_by("1.81.0")
        assert not spec.satisfied_by("1.79.0")

    def test_parse_compat(self):
        spec = VersionSpec.parse("~=3.11")
        assert spec.satisfied_by("3.11.0")
        assert spec.satisfied_by("3.12.5")
        assert not spec.satisfied_by("4.0.0")
        assert not spec.satisfied_by("3.10.0")

    def test_parse_compat_three_part_patch_zero(self):
        # ~=3.11.0 means >=3.11.0, <3.12.0 -- NOT <4.0.0
        spec = VersionSpec.parse("~=3.11.0")
        assert spec.satisfied_by("3.11.0")
        assert spec.satisfied_by("3.11.5")
        assert not spec.satisfied_by("3.12.0")
        assert not spec.satisfied_by("4.0.0")

    def test_parse_caret(self):
        spec = VersionSpec.parse("^2.0.0")
        assert spec.satisfied_by("2.0.0")
        assert spec.satisfied_by("2.99.99")
        assert not spec.satisfied_by("3.0.0")

    def test_parse_range(self):
        spec = VersionSpec.parse(">=1.0,<2.0")
        assert spec.satisfied_by("1.0.0")
        assert spec.satisfied_by("1.99.0")
        assert not spec.satisfied_by("2.0.0")
        assert not spec.satisfied_by("0.99.0")

    def test_parse_wildcard(self):
        spec = VersionSpec.parse("1.2.*")
        assert spec.satisfied_by("1.2.0")
        assert spec.satisfied_by("1.2.99")
        assert not spec.satisfied_by("1.3.0")
        assert not spec.satisfied_by("1.1.99")

    def test_parse_wildcard_major(self):
        spec = VersionSpec.parse("1.*")
        assert spec.satisfied_by("1.0.0")
        assert spec.satisfied_by("1.99.99")
        assert not spec.satisfied_by("2.0.0")

    def test_parse_exact(self):
        spec = VersionSpec.parse("==1.0.0")
        assert spec.satisfied_by("1.0.0")
        assert not spec.satisfied_by("1.0.1")

    def test_parse_single_eq(self):
        spec = VersionSpec.parse("=1.0.0")
        assert spec.satisfied_by("1.0.0")
        assert not spec.satisfied_by("1.0.1")

    def test_parse_bare_version(self):
        # Bare version -> >=
        spec = VersionSpec.parse("1.80")
        assert spec.satisfied_by("1.80.0")
        assert spec.satisfied_by("2.0.0")
        assert not spec.satisfied_by("1.79.0")

    def test_parse_empty_raises(self):
        with pytest.raises(ValueError):
            VersionSpec.parse("")

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            VersionSpec.parse(">>>bad")

    def test_try_parse_success(self):
        assert VersionSpec.try_parse(">=1.0") is not None

    def test_try_parse_failure(self):
        assert VersionSpec.try_parse(">>>bad") is None

    def test_best_match(self):
        spec = VersionSpec.parse(">=1.0,<2.0")
        candidates = ["0.9.0", "1.0.0", "1.5.0", "1.9.0", "2.0.0", "2.1.0"]
        best = spec.best_match(candidates)
        assert best == Version(1, 9, 0)

    def test_best_match_none(self):
        spec = VersionSpec.parse(">=5.0")
        best = spec.best_match(["1.0.0", "2.0.0"])
        assert best is None

    def test_best_match_version_objects(self):
        spec = VersionSpec.parse("^1.0.0")
        candidates = [Version(1, 0, 0), Version(1, 5, 0), Version(2, 0, 0)]
        assert spec.best_match(candidates) == Version(1, 5, 0)

    def test_satisfied_by_string(self):
        spec = VersionSpec.parse(">=1.80")
        assert spec.satisfied_by("1.80.0")

    def test_satisfied_by_version_object(self):
        spec = VersionSpec.parse(">=1.80")
        assert spec.satisfied_by(Version(1, 80, 0))

    def test_satisfied_by_bad_string(self):
        spec = VersionSpec.parse(">=1.80")
        assert not spec.satisfied_by("not-a-version")

    def test_str(self):
        spec = VersionSpec.parse(">=1.0,<2.0")
        assert str(spec) == ">=1.0,<2.0"

    def test_repr(self):
        spec = VersionSpec.parse(">=1.0")
        assert ">=1.0" in repr(spec)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    def test_compare_versions_lt(self):
        assert compare_versions("1.0.0", "2.0.0") == -1

    def test_compare_versions_eq(self):
        assert compare_versions("1.2.3", "1.2.3") == 0

    def test_compare_versions_gt(self):
        assert compare_versions("2.0.0", "1.0.0") == 1

    def test_compare_versions_invalid(self):
        with pytest.raises(ValueError):
            compare_versions("bad", "1.0.0")

    def test_version_satisfies_true(self):
        assert version_satisfies("1.80.0", ">=1.80")

    def test_version_satisfies_false(self):
        assert not version_satisfies("1.79.0", ">=1.80")

    def test_version_satisfies_bad_spec(self):
        assert not version_satisfies("1.0.0", ">>>bad")

    def test_version_satisfies_bad_version(self):
        assert not version_satisfies("bad", ">=1.0")


# ---------------------------------------------------------------------------
# APXM integration scenarios
# ---------------------------------------------------------------------------


class TestAPXMScenarios:
    """Tests modeled on APXM's actual dependency version requirements."""

    def test_rust_min_version(self):
        spec = VersionSpec.parse(">=1.80")
        assert spec.satisfied_by("1.80.0")
        assert spec.satisfied_by("1.85.0")
        assert not spec.satisfied_by("1.79.0")

    def test_cmake_min_version(self):
        spec = VersionSpec.parse(">=3.20")
        assert spec.satisfied_by("3.20.0")
        assert spec.satisfied_by("3.28.1")
        assert not spec.satisfied_by("3.19.0")

    def test_llvm_min_version(self):
        spec = VersionSpec.parse(">=21.0")
        assert spec.satisfied_by("21.0.0")
        assert spec.satisfied_by("21.1.0")
        assert not spec.satisfied_by("20.0.0")

    def test_python_compatible_release(self):
        spec = VersionSpec.parse("~=3.11")
        assert spec.satisfied_by("3.11.0")
        assert spec.satisfied_by("3.13.1")
        assert not spec.satisfied_by("4.0.0")
        assert not spec.satisfied_by("3.10.0")
