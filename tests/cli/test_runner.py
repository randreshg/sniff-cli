"""Tests for dekk.cli.runner -- run_logged and RunResult."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dekk.cli.runner import _BUILD_OUTPUT_LABEL, RunResult, run_logged

# ---------------------------------------------------------------------------
# RunResult
# ---------------------------------------------------------------------------


class TestRunResult:
    def test_ok_true_when_returncode_zero(self):
        r = RunResult(returncode=0, log_path=Path("/tmp/out.log"))
        assert r.ok is True

    def test_ok_false_when_returncode_nonzero(self):
        r = RunResult(returncode=1, log_path=Path("/tmp/out.log"))
        assert r.ok is False

    def test_ok_false_negative_returncode(self):
        r = RunResult(returncode=-1, log_path=Path("/tmp/out.log"))
        assert r.ok is False

    def test_frozen(self):
        r = RunResult(returncode=0, log_path=Path("/tmp/out.log"))
        with pytest.raises((AttributeError, TypeError)):
            r.returncode = 1  # type: ignore[misc]

    def test_log_path_stored(self, tmp_path):
        p = tmp_path / "build.log"
        r = RunResult(returncode=0, log_path=p)
        assert r.log_path == p


# ---------------------------------------------------------------------------
# run_logged
# ---------------------------------------------------------------------------


def _make_completed_process(returncode=0, stdout="some output\n"):
    """Build a mock CompletedProcess with the given returncode and stdout."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    return mock


class TestRunLogged:
    """Tests for run_logged()."""

    def test_returns_run_result(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="ok\n")
        with patch("subprocess.run", return_value=proc):
            result = run_logged(
                ["echo", "hi"],
                log_path=log_path,
                label="Test",
                spinner_text="Testing...",
            )
        assert isinstance(result, RunResult)

    def test_ok_on_returncode_zero(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="success\n")
        with patch("subprocess.run", return_value=proc):
            result = run_logged(
                ["true"],
                log_path=log_path,
                label="OK run",
                spinner_text="Working...",
            )
        assert result.ok

    def test_not_ok_on_nonzero_returncode(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=1, stdout="error\n")
        with patch("subprocess.run", return_value=proc):
            result = run_logged(
                ["false"],
                log_path=log_path,
                label="Fail run",
                spinner_text="Failing...",
            )
        assert not result.ok
        assert result.returncode == 1

    def test_log_file_created(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="line one\n")
        with patch("subprocess.run", return_value=proc):
            run_logged(
                ["echo"],
                log_path=log_path,
                label="Create file",
                spinner_text="...",
            )
        assert log_path.exists()

    def test_log_contains_section_header(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="")
        with patch("subprocess.run", return_value=proc):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="My Section",
                spinner_text="...",
            )
        content = log_path.read_text()
        assert "My Section" in content

    def test_log_contains_stdout(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="build output here\n")
        with patch("subprocess.run", return_value=proc):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="Build",
                spinner_text="Building...",
            )
        content = log_path.read_text()
        assert "build output here" in content

    def test_log_path_returned(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="")
        with patch("subprocess.run", return_value=proc):
            result = run_logged(
                ["cmd"],
                log_path=log_path,
                label="Test",
                spinner_text="...",
            )
        assert result.log_path == log_path.resolve()

    def test_failure_prints_build_output_label(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=1, stdout="error\n")
        with (
            patch("subprocess.run", return_value=proc),
            patch("dekk.cli.styles.print_info") as mock_print,
        ):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="Label test",
                spinner_text="...",
            )
        calls = [str(c) for c in mock_print.call_args_list]
        assert any(_BUILD_OUTPUT_LABEL in c for c in calls)

    def test_success_does_not_print_build_output_label(self, tmp_path):
        """On success the spinner completing is the signal; no path noise."""
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="fine\n")
        with (
            patch("subprocess.run", return_value=proc),
            patch("dekk.cli.styles.print_info") as mock_print,
        ):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="OK",
                spinner_text="...",
            )
        calls = [str(c) for c in mock_print.call_args_list]
        assert len(calls) == 0

    def test_failure_prints_tail(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=1, stdout="line1\nline2\nerror line\n")
        with (
            patch("subprocess.run", return_value=proc),
            patch("dekk.cli.styles.print_info") as mock_print,
        ):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="Fail",
                spinner_text="...",
                tail_lines=5,
            )
        printed = " ".join(str(c) for c in mock_print.call_args_list)
        assert "error line" in printed

    def test_success_does_not_print_tail(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="fine\n")
        with (
            patch("subprocess.run", return_value=proc),
            patch("dekk.cli.styles.print_info") as mock_print,
        ):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="OK",
                spinner_text="...",
                tail_lines=5,
            )
        assert mock_print.call_count == 0

    def test_tail_lines_zero_suppresses_excerpt(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=1, stdout="error line\n")
        with (
            patch("subprocess.run", return_value=proc),
            patch("dekk.cli.styles.print_info") as mock_print,
        ):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="Fail no tail",
                spinner_text="...",
                tail_lines=0,
            )
        # Only the "Build output ->" line, no excerpt
        calls = [str(c) for c in mock_print.call_args_list]
        assert len(calls) == 1
        assert _BUILD_OUTPUT_LABEL in calls[0]

    def test_append_mode_adds_to_existing_log(self, tmp_path):
        log_path = tmp_path / "build.log"
        log_path.write_text("previous content\n")

        proc = _make_completed_process(returncode=0, stdout="new content\n")
        with patch("subprocess.run", return_value=proc):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="Append",
                spinner_text="...",
                append=True,
            )
        content = log_path.read_text()
        assert "previous content" in content
        assert "new content" in content

    def test_overwrite_mode_replaces_existing_log(self, tmp_path):
        log_path = tmp_path / "build.log"
        log_path.write_text("old content\n")

        proc = _make_completed_process(returncode=0, stdout="fresh content\n")
        with patch("subprocess.run", return_value=proc):
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="Overwrite",
                spinner_text="...",
                append=False,
            )
        content = log_path.read_text()
        assert "old content" not in content
        assert "fresh content" in content

    def test_env_forwarded_to_subprocess(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="")
        custom_env = {"MY_VAR": "hello"}
        with patch("subprocess.run", return_value=proc) as mock_run:
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="Env test",
                spinner_text="...",
                env=custom_env,
            )
        _, kwargs = mock_run.call_args
        assert kwargs["env"] == custom_env

    def test_cwd_forwarded_to_subprocess(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="")
        with patch("subprocess.run", return_value=proc) as mock_run:
            run_logged(
                ["cmd"],
                log_path=log_path,
                label="CWD test",
                spinner_text="...",
                cwd=tmp_path,
            )
        _, kwargs = mock_run.call_args
        assert kwargs["cwd"] == tmp_path

    def test_subprocess_called_with_correct_cmd(self, tmp_path):
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout="")
        with patch("subprocess.run", return_value=proc) as mock_run:
            run_logged(
                ["cargo", "build", "--release"],
                log_path=log_path,
                label="Cargo",
                spinner_text="Building...",
            )
        args, _ = mock_run.call_args
        assert args[0] == ["cargo", "build", "--release"]

    def test_none_stdout_handled_gracefully(self, tmp_path):
        """subprocess.run stdout=None should not crash."""
        log_path = tmp_path / "build.log"
        proc = _make_completed_process(returncode=0, stdout=None)
        with patch("subprocess.run", return_value=proc):
            result = run_logged(
                ["cmd"],
                log_path=log_path,
                label="None stdout",
                spinner_text="...",
            )
        assert result.ok
