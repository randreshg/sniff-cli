"""Version constraint parsing, validation, and resolution.

Supports PEP 440-style and semver-style version specifications:
  - Exact:       ==1.2.3, =1.2.3
  - Greater/eq:  >=1.80
  - Greater:     >2.0
  - Less/eq:     <=3.0
  - Less:        <4.0
  - Not equal:   !=1.5
  - Compatible:  ~=3.11  (>=3.11, <4.0)
  - Tilde:       ~1.2.3  (>=1.2.3, <1.3.0)
  - Caret:       ^1.2.3  (>=1.2.3, <2.0.0)
  - Wildcard:    1.2.*   (>=1.2.0, <1.3.0)
  - Range:       >=1.0,<2.0

Pure data + logic -- no I/O, no subprocesses.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from functools import total_ordering

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


@total_ordering
@dataclass(frozen=True)
class Version:
    """A parsed semantic version (major.minor.patch[-pre][+build]).

    Comparison ignores build metadata per semver spec.
    Pre-release versions sort before their release (1.0.0-alpha < 1.0.0).
    """

    major: int
    minor: int = 0
    patch: int = 0
    pre: str | None = None
    build: str | None = None
    _n_components: int = field(default=3, compare=False, repr=False)

    # -- parsing --

    _PATTERN = re.compile(
        r"^v?"
        r"(?P<major>0|[1-9]\d*)"
        r"(?:\.(?P<minor>0|[1-9]\d*))?"
        r"(?:\.(?P<patch>0|[1-9]\d*))?"
        r"(?:-(?P<pre>[0-9A-Za-z\-.]+))?"
        r"(?:\+(?P<build>[0-9A-Za-z\-.]+))?$"
    )

    @classmethod
    def parse(cls, text: str) -> Version:
        """Parse a version string.

        Accepts: "1", "1.2", "1.2.3", "v1.2.3", "1.2.3-beta.1", "1.2.3+build42"

        Raises:
            ValueError: If the string cannot be parsed.
        """
        m = cls._PATTERN.match(text.strip())
        if not m:
            raise ValueError(f"Cannot parse version: {text!r}")
        if m.group("patch") is not None:
            n_components = 3
        elif m.group("minor") is not None:
            n_components = 2
        else:
            n_components = 1
        return cls(
            major=int(m.group("major")),
            minor=int(m.group("minor") or 0),
            patch=int(m.group("patch") or 0),
            pre=m.group("pre"),
            build=m.group("build"),
            _n_components=n_components,
        )

    @classmethod
    def try_parse(cls, text: str) -> Version | None:
        """Like parse() but returns None instead of raising."""
        try:
            return cls.parse(text)
        except ValueError:
            return None

    # -- display --

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            s += f"-{self.pre}"
        if self.build:
            s += f"+{self.build}"
        return s

    def __repr__(self) -> str:
        return f"Version({self})"

    # -- comparison --

    @property
    def _cmp_tuple(self) -> tuple[int, int, int, bool, tuple[tuple[int, int | str], ...]]:
        """Tuple used for ordering.

        Pre-release versions sort *before* the release, so we use
        (has_pre=False) > (has_pre=True) by setting the flag accordingly.
        Pre-release identifiers are compared segment-by-segment: numeric
        segments compare as integers, string segments lexicographically.
        """
        if self.pre is None:
            # No pre-release: sorts after any pre-release of same version
            return (self.major, self.minor, self.patch, False, ())

        parts: list[tuple[int, int | str]] = []
        for segment in self.pre.split("."):
            if segment.isdigit():
                # (0, n) -- numeric segments sort before string segments
                parts.append((0, int(segment)))
            else:
                # (1, s) -- string segments sort after numeric segments
                parts.append((1, segment))
        return (self.major, self.minor, self.patch, True, tuple(parts))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._cmp_tuple == other._cmp_tuple

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        # Pre-release True flag means "has pre" which should sort BEFORE no-pre.
        # We want: (1,0,0, True, ...) < (1,0,0, False, ())
        # Since True > False in Python, we negate:
        s = self._cmp_tuple
        o = other._cmp_tuple
        sk = (s[0], s[1], s[2], not s[3], s[4])
        ok = (o[0], o[1], o[2], not o[3], o[4])
        return sk < ok

    def __hash__(self) -> int:
        return hash(self._cmp_tuple)

    # -- utility --

    @property
    def base(self) -> Version:
        """Version without pre-release or build metadata."""
        return Version(self.major, self.minor, self.patch)

    def bump_major(self) -> Version:
        return Version(self.major + 1, 0, 0)

    def bump_minor(self) -> Version:
        return Version(self.major, self.minor + 1, 0)

    def bump_patch(self) -> Version:
        return Version(self.major, self.minor, self.patch + 1)


# ---------------------------------------------------------------------------
# Constraint operators
# ---------------------------------------------------------------------------


class ConstraintOp(Enum):
    EQ = "=="
    NEQ = "!="
    GTE = ">="
    GT = ">"
    LTE = "<="
    LT = "<"
    COMPAT = "~="  # PEP 440 compatible release
    TILDE = "~"  # npm-style tilde
    CARET = "^"  # npm-style caret


# ---------------------------------------------------------------------------
# VersionConstraint  (single operator + version)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionConstraint:
    """A single version constraint like >=1.80 or ^2.0.0."""

    op: ConstraintOp
    version: Version

    def satisfied_by(self, v: Version) -> bool:
        """Return True if *v* satisfies this constraint."""
        target = self.version
        if self.op is ConstraintOp.EQ:
            return v == target
        if self.op is ConstraintOp.NEQ:
            return v != target
        if self.op is ConstraintOp.GTE:
            return v >= target
        if self.op is ConstraintOp.GT:
            return v > target
        if self.op is ConstraintOp.LTE:
            return v <= target
        if self.op is ConstraintOp.LT:
            return v < target
        if self.op is ConstraintOp.COMPAT:
            # ~=X.Y  -> >=X.Y, <(X+1).0
            # ~=X.Y.Z -> >=X.Y.Z, <X.(Y+1).0
            if target._n_components >= 3:
                upper = target.bump_minor()
            else:
                upper = target.bump_major()
            return v >= target and v < upper
        if self.op is ConstraintOp.TILDE:
            # ~X.Y.Z -> >=X.Y.Z, <X.(Y+1).0
            upper = target.bump_minor()
            return v >= target and v < upper
        if self.op is ConstraintOp.CARET:
            # ^X.Y.Z -> >=X.Y.Z, <(X+1).0.0  (if X>0)
            # ^0.Y.Z -> >=0.Y.Z, <0.(Y+1).0   (if X==0, Y>0)
            # ^0.0.Z -> >=0.0.Z, <0.0.(Z+1)   (if X==0, Y==0)
            if target.major > 0:
                upper = target.bump_major()
            elif target.minor > 0:
                upper = Version(0, target.minor + 1, 0)
            else:
                upper = Version(0, 0, target.patch + 1)
            return v >= target and v < upper
        return False  # pragma: no cover

    def __str__(self) -> str:
        return f"{self.op.value}{self.version}"


# ---------------------------------------------------------------------------
# VersionSpec  (conjunction of constraints)
# ---------------------------------------------------------------------------

# Regex for parsing individual constraints
_CONSTRAINT_RE = re.compile(
    r"^\s*"
    r"(?P<op>~=|==|!=|>=|>|<=|<|[~^=])"
    r"\s*"
    r"(?P<ver>[^\s,]+)"
    r"\s*$"
)

_WILDCARD_RE = re.compile(r"^\s*(?P<prefix>\d+(?:\.\d+)*)\.\*\s*$")


@dataclass(frozen=True)
class VersionSpec:
    """A version specification composed of one or more constraints.

    Supports comma-separated constraints: ">=1.0,<2.0"
    Supports wildcards: "1.2.*"
    """

    constraints: tuple[VersionConstraint, ...]
    raw: str  # original string for display

    @classmethod
    def parse(cls, text: str) -> VersionSpec:
        """Parse a version specification string.

        Examples:
            ">=1.80"
            "~=3.11"
            "^2.0.0"
            ">=1.0,<2.0"
            "1.2.*"
            "==1.0.0"

        Raises:
            ValueError: If the string cannot be parsed.
        """
        text = text.strip()
        if not text:
            raise ValueError("Empty version spec")

        constraints: list[VersionConstraint] = []

        # Check for wildcard first
        wm = _WILDCARD_RE.match(text)
        if wm:
            prefix = wm.group("prefix")
            base = Version.parse(prefix + ".0")
            # 1.2.* -> >=1.2.0, <1.3.0
            # 1.* -> >=1.0.0, <2.0.0
            parts = prefix.split(".")
            if len(parts) >= 2:
                upper = base.bump_minor()
            else:
                upper = base.bump_major()
            constraints.append(VersionConstraint(ConstraintOp.GTE, base))
            constraints.append(VersionConstraint(ConstraintOp.LT, upper))
            return cls(constraints=tuple(constraints), raw=text)

        # Split on comma for multiple constraints
        parts_list = text.split(",")
        for part in parts_list:
            part = part.strip()
            if not part:
                continue

            m = _CONSTRAINT_RE.match(part)
            if not m:
                # Bare version -> treat as >=
                ver = Version.try_parse(part)
                if ver is not None:
                    constraints.append(VersionConstraint(ConstraintOp.GTE, ver))
                    continue
                raise ValueError(f"Cannot parse version constraint: {part!r}")

            op_str = m.group("op")
            ver_str = m.group("ver")

            # Normalize single = to ==
            if op_str == "=":
                op_str = "=="

            ver = Version.parse(ver_str)

            # Map string to enum
            op_map = {e.value: e for e in ConstraintOp}
            op = op_map.get(op_str)
            if op is None:
                raise ValueError(f"Unknown operator: {op_str!r}")

            constraints.append(VersionConstraint(op, ver))

        if not constraints:
            raise ValueError(f"No constraints parsed from: {text!r}")

        return cls(constraints=tuple(constraints), raw=text)

    @classmethod
    def try_parse(cls, text: str) -> VersionSpec | None:
        """Like parse() but returns None instead of raising."""
        try:
            return cls.parse(text)
        except ValueError:
            return None

    def satisfied_by(self, version: str | Version) -> bool:
        """Check if a version satisfies all constraints.

        Args:
            version: Version string or Version object.

        Returns:
            True if all constraints are satisfied.
        """
        if isinstance(version, str):
            v = Version.try_parse(version)
            if v is None:
                return False
        else:
            v = version
        return all(c.satisfied_by(v) for c in self.constraints)

    def best_match(self, candidates: Sequence[str | Version]) -> Version | None:
        """Find the highest version that satisfies all constraints.

        Args:
            candidates: Available versions to choose from.

        Returns:
            The highest satisfying Version, or None.
        """
        matches: list[Version] = []
        for c in candidates:
            if isinstance(c, str):
                v = Version.try_parse(c)
                if v is None:
                    continue
            else:
                v = c
            if self.satisfied_by(v):
                matches.append(v)
        return max(matches) if matches else None

    def __str__(self) -> str:
        return self.raw

    def __repr__(self) -> str:
        return f"VersionSpec({self.raw!r})"


# ---------------------------------------------------------------------------
# Utility: compare two version strings
# ---------------------------------------------------------------------------


def compare_versions(a: str, b: str) -> int:
    """Compare two version strings.

    Returns:
        -1 if a < b, 0 if a == b, 1 if a > b.

    Raises:
        ValueError: If either string cannot be parsed.
    """
    va = Version.parse(a)
    vb = Version.parse(b)
    if va < vb:
        return -1
    if va > vb:
        return 1
    return 0


def version_satisfies(version: str, spec: str) -> bool:
    """Check if a version string satisfies a spec string.

    Convenience function combining Version.parse and VersionSpec.parse.

    Args:
        version: Version string (e.g., "1.80.0").
        spec: Specification string (e.g., ">=1.80").

    Returns:
        True if satisfied, False if not or if parsing fails.
    """
    vs = VersionSpec.try_parse(spec)
    if vs is None:
        return False
    return vs.satisfied_by(version)
