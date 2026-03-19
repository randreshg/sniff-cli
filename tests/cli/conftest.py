"""Shared fixtures for sniff-cli CLI tests.

Provides console capture helpers that patch sniff_cli.cli.styles internals
so Rich output can be captured into StringIO buffers for assertions.
"""

from __future__ import annotations

import io
from contextlib import contextmanager

import pytest
from rich.console import Console

from sniff_cli.cli.styles import CLI_THEME


@contextmanager
def _patch_console(*, stderr: bool = False, highlight: bool = True, extra_targets=None):
    """Context manager that patches sniff_cli.cli.styles console singletons.

    Yields the StringIO buffer containing captured output.
    """
    import sniff_cli.cli.styles as _mod

    buf = io.StringIO()
    capture = Console(
        file=buf, theme=CLI_THEME, force_terminal=True, width=120, highlight=highlight,
    )

    if stderr:
        orig_public = getattr(_mod, "err_console", None)
        orig_internal = _mod._err_console
        _mod.err_console = capture
        _mod._err_console = capture
    else:
        orig_public = getattr(_mod, "console", None)
        orig_internal = _mod._console
        _mod.console = capture
        _mod._console = capture

    # Patch any extra module targets (e.g., sniff_cli.cli.output.console)
    extra_originals = []
    for mod, attr in (extra_targets or []):
        extra_originals.append((mod, attr, getattr(mod, attr, None)))
        setattr(mod, attr, capture)

    try:
        yield buf
    finally:
        if stderr:
            _mod.err_console = orig_public
            _mod._err_console = orig_internal
        else:
            _mod.console = orig_public
            _mod._console = orig_internal
        for mod, attr, orig_val in extra_originals:
            setattr(mod, attr, orig_val)


@pytest.fixture
def capture_console():
    """Fixture returning a context manager that captures stdout console output.

    Usage::

        def test_example(capture_console):
            with capture_console() as buf:
                print_success("ok")
            assert "ok" in buf.getvalue()
    """
    @contextmanager
    def _capture(*, highlight=True, extra_targets=None):
        with _patch_console(stderr=False, highlight=highlight, extra_targets=extra_targets) as buf:
            yield buf
    return _capture


@pytest.fixture
def capture_err_console():
    """Fixture returning a context manager that captures stderr console output."""
    @contextmanager
    def _capture(*, highlight=True, extra_targets=None):
        with _patch_console(stderr=True, highlight=highlight, extra_targets=extra_targets) as buf:
            yield buf
    return _capture


@pytest.fixture
def capture_both_consoles():
    """Fixture returning a context manager that captures both stdout and stderr."""
    @contextmanager
    def _capture(*, highlight=True):
        import sniff_cli.cli.styles as _mod
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        stdout_console = Console(
            file=stdout_buf, theme=CLI_THEME, force_terminal=True, width=120, highlight=highlight,
        )
        stderr_console = Console(
            file=stderr_buf, theme=CLI_THEME, force_terminal=True, width=120, highlight=highlight,
        )
        orig_out = getattr(_mod, "console", None)
        orig_err = getattr(_mod, "err_console", None)
        orig_out_internal = _mod._console
        orig_err_internal = _mod._err_console
        _mod.console = stdout_console
        _mod._console = stdout_console
        _mod.err_console = stderr_console
        _mod._err_console = stderr_console
        try:
            yield stdout_buf, stderr_buf
        finally:
            _mod.console = orig_out
            _mod._console = orig_out_internal
            _mod.err_console = orig_err
            _mod._err_console = orig_err_internal
    return _capture
