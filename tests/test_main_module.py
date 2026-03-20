"""Tests for the ``python -m dekk`` entry point."""

from __future__ import annotations

import runpy
from unittest.mock import patch

import pytest

from dekk.cli.errors import ExitCodes, NotFoundError
from dekk.cli.main import main


def test_python_m_dekk_delegates_to_cli_main() -> None:
    with patch("dekk.cli.main.main") as mock_main:
        runpy.run_module("dekk", run_name="__main__")

    mock_main.assert_called_once_with()


def test_main_formats_dekk_error_for_users() -> None:
    with (
        patch("sys.argv", ["dekk"]),
        patch("dekk.cli.main._app", None),
        patch(
            "dekk.cli.main._make_app",
            side_effect=NotFoundError("Missing config", hint="Run 'dekk init'"),
        ),
        patch("dekk.cli.styles.print_error") as mock_error,
        patch("dekk.cli.styles.print_info") as mock_info,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == int(ExitCodes.NOT_FOUND)
    mock_error.assert_called_once_with("Missing config")
    mock_info.assert_called_once_with("Hint: Run 'dekk init'")
