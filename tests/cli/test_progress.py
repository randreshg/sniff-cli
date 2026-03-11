"""Tests for sniff.cli.progress -- progress bars, spinners, and StatusReporter."""

from __future__ import annotations

import io

from rich.console import Console
from rich.progress import Progress

from sniff.cli.progress import StatusReporter, progress_bar, spinner
from sniff.cli.styles import CLI_THEME, Symbols


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture(fn, *args, **kwargs) -> str:
    """Capture stdout console output from a function."""
    buf = io.StringIO()
    capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)

    import sniff.cli.styles as _mod

    orig = _mod.console
    _mod.console = capture_console
    try:
        fn(*args, **kwargs)
    finally:
        _mod.console = orig
    return buf.getvalue()


def _capture_err(fn, *args, **kwargs) -> str:
    """Capture stderr console output from a function."""
    buf = io.StringIO()
    capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)

    import sniff.cli.styles as _mod

    orig = _mod.err_console
    _mod.err_console = capture_console
    try:
        fn(*args, **kwargs)
    finally:
        _mod.err_console = orig
    return buf.getvalue()


# ---------------------------------------------------------------------------
# progress_bar
# ---------------------------------------------------------------------------


class TestProgressBar:
    """Tests for the progress_bar context manager."""

    def test_yields_progress_instance(self):
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        try:
            with progress_bar("Test", total=10) as p:
                assert isinstance(p, Progress)
        finally:
            _mod.console = orig

    def test_task_auto_added(self):
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        try:
            with progress_bar("Building", total=5) as p:
                assert len(p.tasks) == 1
                assert p.tasks[0].description == "Building"
                assert p.tasks[0].total == 5
        finally:
            _mod.console = orig

    def test_indeterminate_total(self):
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        try:
            with progress_bar("Loading", total=None) as p:
                assert p.tasks[0].total is None
        finally:
            _mod.console = orig

    def test_advance_updates_completed(self):
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        try:
            with progress_bar("Work", total=3) as p:
                task = p.tasks[0]
                p.update(task.id, advance=1)
                assert task.completed == 1
                p.update(task.id, advance=2)
                assert task.completed == 3
        finally:
            _mod.console = orig

    def test_context_manager_cleans_up(self):
        """Progress should not raise on exit."""
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        try:
            with progress_bar("Done", total=1) as p:
                p.update(p.tasks[0].id, advance=1)
            # No exception means cleanup succeeded
        finally:
            _mod.console = orig


# ---------------------------------------------------------------------------
# spinner
# ---------------------------------------------------------------------------


class TestSpinner:
    """Tests for the spinner context manager."""

    def test_does_not_raise(self):
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        try:
            with spinner("Resolving..."):
                pass
        finally:
            _mod.console = orig

    def test_yields_none(self):
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        try:
            with spinner("Working...") as result:
                assert result is None
        finally:
            _mod.console = orig

    def test_code_runs_inside_block(self):
        """Code within the spinner block should execute normally."""
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        executed = False
        try:
            with spinner("Testing..."):
                executed = True
            assert executed
        finally:
            _mod.console = orig


# ---------------------------------------------------------------------------
# StatusReporter
# ---------------------------------------------------------------------------


class TestStatusReporter:
    """Tests for the StatusReporter class."""

    def test_init_prints_header(self):
        out = _capture(StatusReporter, "Deployment")
        assert "Deployment" in out

    def test_start(self):
        def _run():
            import sniff.cli.styles as _mod

            reporter = StatusReporter.__new__(StatusReporter)
            reporter.title = "Test"
            print_step = _mod.print_step
            print_step("Starting step")

        out = _capture(_run)
        assert "Starting step" in out

    def test_success_message(self):
        def _run():
            reporter = StatusReporter.__new__(StatusReporter)
            reporter.title = "Test"
            from sniff.cli.styles import print_success

            print_success("All good")

        out = _capture(_run)
        assert "All good" in out
        assert Symbols.PASS in out

    def test_error_message(self):
        def _run():
            from sniff.cli.styles import print_error

            print_error("Build failed")

        out = _capture_err(_run)
        assert "Build failed" in out
        assert Symbols.FAIL in out

    def test_warning_message(self):
        def _run():
            from sniff.cli.styles import print_warning

            print_warning("Slow network")

        out = _capture_err(_run)
        assert "Slow network" in out

    def test_info_message(self):
        def _run():
            from sniff.cli.styles import print_info

            print_info("Detail here")

        out = _capture(_run)
        assert "Detail here" in out

    def test_full_workflow(self):
        """Test a complete multi-step workflow through StatusReporter."""
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        stdout_console = Console(file=stdout_buf, theme=CLI_THEME, force_terminal=True, width=120)
        stderr_console = Console(file=stderr_buf, theme=CLI_THEME, force_terminal=True, width=120)

        import sniff.cli.styles as _mod

        orig_out = _mod.console
        orig_err = _mod.err_console
        _mod.console = stdout_console
        _mod.err_console = stderr_console
        try:
            reporter = StatusReporter("Build Pipeline")
            reporter.start("Checking environment")
            reporter.success("Environment OK")
            reporter.start("Compiling")
            reporter.warning("Deprecated API used")
            reporter.error("Compilation failed")
            reporter.info("See logs for details")
        finally:
            _mod.console = orig_out
            _mod.err_console = orig_err

        stdout = stdout_buf.getvalue()
        stderr = stderr_buf.getvalue()

        assert "Build Pipeline" in stdout
        assert "Checking environment" in stdout
        assert "Environment OK" in stdout
        assert "Compiling" in stdout
        assert "See logs for details" in stdout
        assert "Deprecated API used" in stderr
        assert "Compilation failed" in stderr

    def test_title_attribute(self):
        buf = io.StringIO()
        capture_console = Console(file=buf, theme=CLI_THEME, force_terminal=True, width=120)
        import sniff.cli.styles as _mod

        orig = _mod.console
        _mod.console = capture_console
        try:
            reporter = StatusReporter("My Title")
            assert reporter.title == "My Title"
        finally:
            _mod.console = orig
