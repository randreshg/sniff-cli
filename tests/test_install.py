"""Tests for sniff_cli.install."""

from __future__ import annotations

from pathlib import Path

import pytest

from sniff_cli.cli.errors import NotFoundError
from sniff_cli.install import BinaryInstaller


def test_install_python_shim_writes_wrapper(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    script = project_dir / "tools" / "cli.py"
    script.parent.mkdir()
    script.write_text("print('hi')\n", encoding="utf-8")

    result = BinaryInstaller(project_root=project_dir).install_python_shim(
        script,
        name="demo",
        install_dir=tmp_path / "bin",
    )

    assert result.bin_path.exists()
    wrapper_text = result.bin_path.read_text(encoding="utf-8")
    assert "-m sniff_cli" in wrapper_text
    assert str(script.resolve()) in wrapper_text


def test_install_python_shim_requires_pyproject(tmp_path: Path) -> None:
    script = tmp_path / "cli.py"
    script.write_text("print('hi')\n", encoding="utf-8")

    with pytest.raises(NotFoundError, match="No pyproject.toml found"):
        BinaryInstaller(project_root=tmp_path).install_python_shim(script, install_dir=tmp_path / "bin")
