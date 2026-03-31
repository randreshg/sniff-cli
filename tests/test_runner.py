"""Tests for dekk.execution.runner helpers."""

from __future__ import annotations

from pathlib import Path

from dekk.execution import runner as runner_mod
from dekk.execution.os import PosixDekkOS, WindowsDekkOS


class TestVenvExecutable:
    def test_uses_bin_on_posix(self, tmp_path: Path, monkeypatch):
        venv = tmp_path / ".venv"
        bin_dir = venv / "bin"
        bin_dir.mkdir(parents=True)
        python = bin_dir / "python"
        python.write_text("", encoding="utf-8")

        monkeypatch.setattr(runner_mod, "get_dekk_os", lambda: PosixDekkOS())
        assert runner_mod._venv_executable(venv, "python") == python

    def test_uses_scripts_on_windows(self, tmp_path: Path, monkeypatch):
        venv = tmp_path / ".venv"
        scripts_dir = venv / "Scripts"
        scripts_dir.mkdir(parents=True)
        python = scripts_dir / "python.exe"
        python.write_text("", encoding="utf-8")

        monkeypatch.setattr(runner_mod, "get_dekk_os", lambda: WindowsDekkOS())
        assert runner_mod._venv_executable(venv, "python") == python

    def test_falls_back_to_executable_name_when_missing(self, tmp_path: Path, monkeypatch):
        venv = tmp_path / ".venv"
        scripts_dir = venv / "Scripts"
        scripts_dir.mkdir(parents=True)

        monkeypatch.setattr(runner_mod, "get_dekk_os", lambda: WindowsDekkOS())
        assert runner_mod._venv_executable(venv, "pip") == scripts_dir / "pip"
