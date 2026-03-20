"""Tests for compiler and toolchain detection."""

import pytest

from dekk.compiler import CompilerDetector, CompilerFamily, CompilerInfo, ToolchainInfo


def test_compiler_info_not_found():
    """CompilerInfo.found is False when path is None."""
    info = CompilerInfo(family=CompilerFamily.GCC, command="gcc")
    assert info.found is False
    assert info.path is None


def test_compiler_info_found():
    """CompilerInfo.found is True when path is set."""
    info = CompilerInfo(
        family=CompilerFamily.GCC,
        command="gcc",
        path="/usr/bin/gcc",
        version="13.2.0",
        target="x86_64-linux-gnu",
        language="c",
    )
    assert info.found is True
    assert info.version == "13.2.0"
    assert info.target == "x86_64-linux-gnu"


def test_compiler_info_is_frozen():
    """CompilerInfo is immutable."""
    info = CompilerInfo(family=CompilerFamily.CLANG, command="clang")
    with pytest.raises(AttributeError):
        info.version = "17.0.0"  # type: ignore[misc]


def test_toolchain_info_families():
    """ToolchainInfo.families returns unique families of found compilers."""
    compilers = (
        CompilerInfo(family=CompilerFamily.GCC, command="gcc", path="/usr/bin/gcc", language="c"),
        CompilerInfo(family=CompilerFamily.GCC, command="g++", path="/usr/bin/g++", language="c++"),
        CompilerInfo(family=CompilerFamily.CLANG, command="clang"),  # not found
        CompilerInfo(
            family=CompilerFamily.RUSTC, command="rustc", path="/usr/bin/rustc", language="rust"
        ),
    )
    tc = ToolchainInfo(compilers=compilers)
    assert CompilerFamily.GCC in tc.families
    assert CompilerFamily.RUSTC in tc.families
    assert CompilerFamily.CLANG not in tc.families  # not found


def test_toolchain_info_by_family():
    """ToolchainInfo.by_family filters by family."""
    compilers = (
        CompilerInfo(family=CompilerFamily.GCC, command="gcc", path="/usr/bin/gcc", language="c"),
        CompilerInfo(family=CompilerFamily.GCC, command="g++", path="/usr/bin/g++", language="c++"),
        CompilerInfo(
            family=CompilerFamily.CLANG, command="clang", path="/usr/bin/clang", language="c"
        ),
    )
    tc = ToolchainInfo(compilers=compilers)
    gcc_compilers = tc.by_family(CompilerFamily.GCC)
    assert len(gcc_compilers) == 2
    assert all(c.family == CompilerFamily.GCC for c in gcc_compilers)


def test_toolchain_info_by_language():
    """ToolchainInfo.by_language filters by language."""
    compilers = (
        CompilerInfo(family=CompilerFamily.GCC, command="gcc", path="/usr/bin/gcc", language="c"),
        CompilerInfo(
            family=CompilerFamily.CLANG, command="clang", path="/usr/bin/clang", language="c"
        ),
        CompilerInfo(
            family=CompilerFamily.RUSTC, command="rustc", path="/usr/bin/rustc", language="rust"
        ),
    )
    tc = ToolchainInfo(compilers=compilers)
    c_compilers = tc.by_language("c")
    assert len(c_compilers) == 2


def test_toolchain_info_is_frozen():
    """ToolchainInfo is immutable."""
    tc = ToolchainInfo()
    with pytest.raises(AttributeError):
        tc.compilers = ()  # type: ignore[misc]


def test_compiler_family_values():
    """CompilerFamily enum has expected values."""
    assert CompilerFamily.GCC.value == "gcc"
    assert CompilerFamily.CLANG.value == "clang"
    assert CompilerFamily.RUSTC.value == "rustc"
    assert CompilerFamily.GO.value == "go"
    assert CompilerFamily.UNKNOWN.value == "unknown"


def test_detector_always_succeeds():
    """CompilerDetector.detect() never raises."""
    detector = CompilerDetector()
    result = detector.detect()
    assert isinstance(result, ToolchainInfo)
    assert isinstance(result.compilers, tuple)


def test_detector_returns_all_probed():
    """detect() returns an entry for every probed compiler."""
    detector = CompilerDetector()
    result = detector.detect()
    # Should have at least the 6 built-in compilers probed
    assert len(result.compilers) >= 6


def test_detect_missing_compiler():
    """detect_compiler for a non-existent command returns not-found."""
    detector = CompilerDetector()
    info = detector.detect_compiler("definitely-not-a-real-compiler-xyz")
    assert info.found is False
    assert info.family == CompilerFamily.UNKNOWN


def test_detect_known_compiler():
    """detect_compiler for a known command uses its configured family."""
    detector = CompilerDetector()
    info = detector.detect_compiler("gcc")
    assert info.family == CompilerFamily.GCC
    assert info.language == "c"
    # found depends on system -- just check types
    assert isinstance(info.found, bool)


def test_detect_gcc_if_available():
    """If gcc is in PATH, its info is populated."""
    import shutil

    if not shutil.which("gcc"):
        pytest.skip("gcc not available")

    detector = CompilerDetector()
    info = detector.detect_compiler("gcc")
    assert info.found is True
    assert info.version is not None
    assert info.family == CompilerFamily.GCC


def test_detect_go_if_available():
    """If go is in PATH, version and target are populated."""
    import shutil

    if not shutil.which("go"):
        pytest.skip("go not available")

    detector = CompilerDetector()
    info = detector.detect_compiler("go")
    assert info.found is True
    assert info.version is not None
    assert info.target is not None  # go env GOOS GOARCH


def test_detect_clang_if_available():
    """If clang is in PATH, its info is populated."""
    import shutil

    if not shutil.which("clang"):
        pytest.skip("clang not available")

    detector = CompilerDetector()
    info = detector.detect_compiler("clang")
    assert info.found is True
    assert info.version is not None
    assert info.family == CompilerFamily.CLANG


def test_default_cc_detection():
    """default_cc should be set if any C compiler is found."""
    import shutil

    if not shutil.which("cc") and not shutil.which("gcc") and not shutil.which("clang"):
        pytest.skip("no C compiler available")

    detector = CompilerDetector()
    result = detector.detect()
    assert result.default_cc is not None
    assert result.default_cc.language == "c"
