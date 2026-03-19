"""Tests for the ``python -m sniff_cli`` entry point."""

from __future__ import annotations

import runpy
from unittest.mock import patch

import pytest

from sniff_cli.cli.errors import ExitCodes, NotFoundError
from sniff_cli.cli.main import main


def test_python_m_sniff_cli_delegates_to_cli_main() -> None:
    with patch("sniff_cli.cli.main.main") as mock_main:
        runpy.run_module("sniff_cli", run_name="__main__")

    mock_main.assert_called_once_with()


def test_main_formats_sniff_error_for_users() -> None:
    with (
        patch("sys.argv", ["sniff"]),
        patch("sniff_cli.cli.main._app", None),
        patch("sniff_cli.cli.main._make_app", side_effect=NotFoundError("Missing config", hint="Run 'sniff init'")),
        patch("sniff_cli.cli.styles.print_error") as mock_error,
        patch("sniff_cli.cli.styles.print_info") as mock_info,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == int(ExitCodes.NOT_FOUND)
    mock_error.assert_called_once_with("Missing config")
    mock_info.assert_called_once_with("Hint: Run 'sniff init'")
