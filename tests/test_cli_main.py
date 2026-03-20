"""Tests for dekk.cli.main command wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from dekk.cli.main import _make_app

runner = CliRunner()


class TestCliMain:
    def test_activate_passes_shell(self):
        app = _make_app()
        with patch("dekk.cli.commands.activate") as activate_mock:
            result = runner.invoke(app, ["activate", "--shell", "powershell"])

        assert result.exit_code == 0
        activate_mock.assert_called_once_with(shell="powershell")

    def test_init_passes_directory_name_and_force(self, tmp_path: Path):
        app = _make_app()
        target_dir = tmp_path / "demo"
        target_dir.mkdir()

        with patch("dekk.cli.commands.init") as init_mock:
            result = runner.invoke(
                app,
                ["init", str(target_dir), "--name", "demo-app", "--force"],
            )

        assert result.exit_code == 0
        init_mock.assert_called_once_with(
            directory=target_dir,
            name="demo-app",
            example=None,
            force=True,
        )

    def test_init_passes_example_template(self, tmp_path: Path):
        app = _make_app()
        target_dir = tmp_path / "demo"
        target_dir.mkdir()

        with patch("dekk.cli.commands.init") as init_mock:
            result = runner.invoke(
                app,
                ["init", str(target_dir), "--example", "conda"],
            )

        assert result.exit_code == 0
        init_mock.assert_called_once_with(
            directory=target_dir,
            name=None,
            example="conda",
            force=False,
        )

    def test_wrap_passes_paths(self, tmp_path: Path):
        app = _make_app()
        target = tmp_path / "tool.py"
        target.write_text("print('hi')", encoding="utf-8")
        python = tmp_path / "python.exe"
        python.write_text("", encoding="utf-8")
        spec = tmp_path / ".dekk.toml"
        spec.write_text("[project]\nname='demo'\n", encoding="utf-8")
        install_dir = tmp_path / "bin"

        with patch("dekk.cli.commands.wrap") as wrap_mock:
            result = runner.invoke(
                app,
                [
                    "wrap",
                    "demo",
                    str(target),
                    "--python",
                    str(python),
                    "--install-dir",
                    str(install_dir),
                    "--spec",
                    str(spec),
                ],
            )

        assert result.exit_code == 0
        wrap_mock.assert_called_once_with(
            name="demo",
            target=target,
            python=python,
            install_dir=install_dir,
            spec_file=spec,
        )

    def test_install_passes_paths(self, tmp_path: Path):
        app = _make_app()
        target = tmp_path / "tool.py"
        target.write_text("print('hi')", encoding="utf-8")
        python = tmp_path / "python.exe"
        python.write_text("", encoding="utf-8")
        spec = tmp_path / ".dekk.toml"
        spec.write_text("[project]\nname='demo'\n", encoding="utf-8")
        install_dir = tmp_path / "bin"

        with patch("dekk.cli.commands.install") as install_mock:
            result = runner.invoke(
                app,
                [
                    "install",
                    str(target),
                    "--name",
                    "demo",
                    "--python",
                    str(python),
                    "--install-dir",
                    str(install_dir),
                    "--spec",
                    str(spec),
                ],
            )

        assert result.exit_code == 0
        install_mock.assert_called_once_with(
            target=target,
            name="demo",
            python=python,
            install_dir=install_dir,
            spec_file=spec,
        )

    def test_test_passes_extra_args(self):
        app = _make_app()

        with patch("dekk.cli.commands.test") as test_mock:
            result = runner.invoke(app, ["test", "-q", "tests/test_detect.py"])

        assert result.exit_code == 0
        test_mock.assert_called_once_with(extra_args=["-q", "tests/test_detect.py"])

    def test_uninstall_passes_install_dir(self, tmp_path: Path):
        app = _make_app()
        install_dir = tmp_path / "bin"

        with patch("dekk.cli.commands.uninstall") as uninstall_mock:
            result = runner.invoke(
                app,
                ["uninstall", "demo", "--install-dir", str(install_dir)],
            )

        assert result.exit_code == 0
        uninstall_mock.assert_called_once_with(
            name="demo",
            install_dir=install_dir,
            remove_path=False,
        )

    def test_example_passes_output_and_name(self, tmp_path: Path):
        app = _make_app()
        output = tmp_path / ".dekk.toml"

        with patch("dekk.cli.commands.example") as example_mock:
            result = runner.invoke(
                app,
                ["example", "conda", "--output", str(output), "--name", "demo-app", "--force"],
            )

        assert result.exit_code == 0
        example_mock.assert_called_once_with(
            template="conda",
            output=output,
            name="demo-app",
            force=True,
        )
