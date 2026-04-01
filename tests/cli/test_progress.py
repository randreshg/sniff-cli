"""Tests for dekk.cli.progress -- progress bars and spinners."""

from __future__ import annotations

from rich.progress import Progress

from dekk.cli.progress import progress_bar, spinner

# ---------------------------------------------------------------------------
# progress_bar
# ---------------------------------------------------------------------------


class TestProgressBar:
    """Tests for the progress_bar context manager."""

    def test_yields_progress_instance(self, capture_console):
        with capture_console():
            with progress_bar("Test", total=10) as p:
                assert isinstance(p, Progress)

    def test_task_auto_added(self, capture_console):
        with capture_console():
            with progress_bar("Building", total=5) as p:
                assert len(p.tasks) == 1
                assert p.tasks[0].description == "Building"
                assert p.tasks[0].total == 5

    def test_indeterminate_total(self, capture_console):
        with capture_console():
            with progress_bar("Loading", total=None) as p:
                assert p.tasks[0].total is None

    def test_advance_updates_completed(self, capture_console):
        with capture_console():
            with progress_bar("Work", total=3) as p:
                task = p.tasks[0]
                p.update(task.id, advance=1)
                assert task.completed == 1
                p.update(task.id, advance=2)
                assert task.completed == 3

    def test_context_manager_cleans_up(self, capture_console):
        """Progress should not raise on exit."""
        with capture_console():
            with progress_bar("Done", total=1) as p:
                p.update(p.tasks[0].id, advance=1)
            # No exception means cleanup succeeded


# ---------------------------------------------------------------------------
# spinner
# ---------------------------------------------------------------------------


class TestSpinner:
    """Tests for the spinner context manager."""

    def test_does_not_raise(self, capture_console):
        with capture_console():
            with spinner("Resolving..."):
                pass

    def test_yields_status(self, capture_console):
        """Spinner yields a Rich Status object for dynamic text updates."""
        with capture_console():
            with spinner("Working...") as status:
                assert status is not None
                assert hasattr(status, "update")

    def test_code_runs_inside_block(self, capture_console):
        """Code within the spinner block should execute normally."""
        executed = False
        with capture_console():
            with spinner("Testing..."):
                executed = True
        assert executed
