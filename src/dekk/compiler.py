"""Compiler and toolchain detection - identify installed compilers, versions, and targets."""

from __future__ import annotations

import enum
import re
import shutil
import subprocess
from dataclasses import dataclass


class CompilerFamily(enum.Enum):
    """Known compiler families."""

    GCC = "gcc"
    CLANG = "clang"
    RUSTC = "rustc"
    GO = "go"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CompilerInfo:
    """Detection result for a single compiler."""

    family: CompilerFamily
    command: str  # Binary name used (e.g., "gcc-13", "clang")
    path: str | None = None  # Resolved path from which()
    version: str | None = None  # Version string (e.g., "13.2.0")
    target: str | None = None  # Default target triple (e.g., "x86_64-linux-gnu")
    language: str | None = None  # Primary language (e.g., "c", "c++", "rust", "go")

    @property
    def found(self) -> bool:
        """True if the compiler was found in PATH."""
        return self.path is not None


@dataclass(frozen=True)
class ToolchainInfo:
    """Aggregated toolchain detection results."""

    compilers: tuple[CompilerInfo, ...] = ()
    default_cc: CompilerInfo | None = None  # Default C compiler (cc / $CC)
    default_cxx: CompilerInfo | None = None  # Default C++ compiler (c++ / $CXX)

    @property
    def families(self) -> tuple[CompilerFamily, ...]:
        """Unique compiler families detected."""
        seen: list[CompilerFamily] = []
        for c in self.compilers:
            if c.found and c.family not in seen:
                seen.append(c.family)
        return tuple(seen)

    def by_family(self, family: CompilerFamily) -> tuple[CompilerInfo, ...]:
        """Return all compilers matching a given family."""
        return tuple(c for c in self.compilers if c.family == family and c.found)

    def by_language(self, language: str) -> tuple[CompilerInfo, ...]:
        """Return all compilers for a given language."""
        return tuple(c for c in self.compilers if c.language == language and c.found)


class CompilerDetector:
    """Detect installed compilers and their capabilities.

    Uses subprocess for version detection. Always succeeds (never raises).
    """

    # Compilers to probe: (command, family, language, version_arg, version_pattern, target_pattern)
    _COMPILERS: list[tuple[str, CompilerFamily, str, str, str, str | None]] = [
        ("gcc", CompilerFamily.GCC, "c", "--version", r"(\d+\.\d+\.\d+)", r"Target:\s*(\S+)"),
        (
            "g++",
            CompilerFamily.GCC,
            "c++",
            "--version",
            r"(\d+\.\d+\.\d+)",
            r"Target:\s*(\S+)",
        ),
        (
            "clang",
            CompilerFamily.CLANG,
            "c",
            "--version",
            r"version\s+(\d+\.\d+\.\d+)",
            r"Target:\s*(\S+)",
        ),
        (
            "clang++",
            CompilerFamily.CLANG,
            "c++",
            "--version",
            r"version\s+(\d+\.\d+\.\d+)",
            r"Target:\s*(\S+)",
        ),
        (
            "rustc",
            CompilerFamily.RUSTC,
            "rust",
            "--version",
            r"rustc\s+(\d+\.\d+\.\d+)",
            None,
        ),
        (
            "go",
            CompilerFamily.GO,
            "go",
            "version",
            r"go(\d+\.\d+(?:\.\d+)?)",
            None,
        ),
    ]

    def __init__(self, timeout: float = 10.0):
        """
        Initialize compiler detector.

        Args:
            timeout: Seconds to wait for version commands.
        """
        self.timeout = timeout

    def detect(self) -> ToolchainInfo:
        """
        Detect all known compilers.

        Always succeeds (never raises).

        Returns:
            ToolchainInfo with all detected compilers.
        """
        compilers: list[CompilerInfo] = []

        for command, family, language, ver_arg, ver_pat, target_pat in self._COMPILERS:
            info = self._probe(command, family, language, ver_arg, ver_pat, target_pat)
            compilers.append(info)

        default_cc = self._detect_default_cc(compilers)
        default_cxx = self._detect_default_cxx(compilers)

        return ToolchainInfo(
            compilers=tuple(compilers),
            default_cc=default_cc,
            default_cxx=default_cxx,
        )

    def detect_compiler(self, command: str) -> CompilerInfo:
        """
        Detect a specific compiler by command name.

        Always succeeds (never raises).

        Args:
            command: Compiler command to probe (e.g., "gcc", "rustc").

        Returns:
            CompilerInfo for the given command.
        """
        for cmd, family, language, ver_arg, ver_pat, target_pat in self._COMPILERS:
            if cmd == command:
                return self._probe(command, family, language, ver_arg, ver_pat, target_pat)

        # Unknown compiler -- try generic detection
        return self._probe(
            command, CompilerFamily.UNKNOWN, "unknown", "--version", r"(\d+\.\d+\.\d+)", None
        )

    def _probe(
        self,
        command: str,
        family: CompilerFamily,
        language: str,
        version_arg: str,
        version_pattern: str,
        target_pattern: str | None,
    ) -> CompilerInfo:
        """Probe a single compiler. Never raises."""
        path = shutil.which(command)
        if not path:
            return CompilerInfo(family=family, command=command, language=language)

        version = None
        target = None

        try:
            result = subprocess.run(
                [command, version_arg],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            output = result.stdout + result.stderr

            # Extract version
            match = re.search(version_pattern, output)
            if match:
                version = match.group(1)

            # Extract target triple
            if target_pattern:
                match = re.search(target_pattern, output)
                if match:
                    target = match.group(1)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # For rustc, get target via --version --verbose or rustc -vV
        if family == CompilerFamily.RUSTC and target is None:
            target = self._get_rustc_target(command)

        # For go, get target from `go env GOOS GOARCH`
        if family == CompilerFamily.GO and target is None:
            target = self._get_go_target(command)

        return CompilerInfo(
            family=family,
            command=command,
            path=path,
            version=version,
            target=target,
            language=language,
        )

    def _get_rustc_target(self, command: str) -> str | None:
        """Extract host target from rustc -vV."""
        try:
            result = subprocess.run(
                [command, "-vV"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            match = re.search(r"host:\s*(\S+)", result.stdout, re.IGNORECASE)
            if match:
                return match.group(1)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None

    def _get_go_target(self, command: str) -> str | None:
        """Extract target from go env."""
        try:
            result = subprocess.run(
                [command, "env", "GOOS", "GOARCH"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            lines = result.stdout.strip().splitlines()
            if len(lines) == 2:
                return f"{lines[0].strip()}/{lines[1].strip()}"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None

    def _detect_default_cc(self, compilers: list[CompilerInfo]) -> CompilerInfo | None:
        """Find the default C compiler."""
        # Check cc symlink
        cc_path = shutil.which("cc")
        if cc_path:
            # Try to match against detected compilers
            for c in compilers:
                if c.found and c.language == "c" and c.path == cc_path:
                    return c
            # cc exists but doesn't match a detected compiler -- probe it
            return self._probe(
                "cc",
                CompilerFamily.UNKNOWN,
                "c",
                "--version",
                r"(\d+\.\d+\.\d+)",
                r"Target:\s*(\S+)",
            )

        # Fallback: first found C compiler
        for c in compilers:
            if c.found and c.language == "c":
                return c
        return None

    def _detect_default_cxx(self, compilers: list[CompilerInfo]) -> CompilerInfo | None:
        """Find the default C++ compiler."""
        # Check c++ symlink
        cxx_path = shutil.which("c++")
        if cxx_path:
            for c in compilers:
                if c.found and c.language == "c++" and c.path == cxx_path:
                    return c
            return self._probe(
                "c++",
                CompilerFamily.UNKNOWN,
                "c++",
                "--version",
                r"(\d+\.\d+\.\d+)",
                r"Target:\s*(\S+)",
            )

        # Fallback: first found C++ compiler
        for c in compilers:
            if c.found and c.language == "c++":
                return c
        return None
