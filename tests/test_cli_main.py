"""Tests for dekk.cli.main command wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import dekk.cli.main as cli_main


class TestCliMain:
    def test_main_routes_unknown_first_arg_to_project_runner(self, monkeypatch):
        monkeypatch.setattr(cli_main, "_app", None)
        monkeypatch.setattr("sys.argv", ["dekk", "demo", "hello"])
        with patch("dekk.project.runner.run_project_command", return_value=0) as run_mock:
            with pytest.raises(SystemExit) as exc:
                cli_main.main()
        assert exc.value.code == 0
        run_mock.assert_called_once_with("demo", ["hello"])
