"""Tests for dekk.install."""

from __future__ import annotations

from pathlib import Path

import pytest

from dekk.cli.errors import NotFoundError
from dekk.install import BinaryInstaller
from dekk.shell import ShellInfo, ShellKind


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
    assert "-m dekk" in wrapper_text
    assert str(script.resolve()) in wrapper_text


def test_install_python_shim_requires_pyproject(tmp_path: Path) -> None:
    script = tmp_path / "cli.py"
    script.write_text("print('hi')\n", encoding="utf-8")

    with pytest.raises(NotFoundError, match="No pyproject.toml found"):
        BinaryInstaller(project_root=tmp_path).install_python_shim(
            script, install_dir=tmp_path / "bin"
        )


def test_install_python_shim_updates_shell_config_when_missing_from_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    script = project_dir / "tools" / "cli.py"
    script.parent.mkdir()
    script.write_text("print('hi')\n", encoding="utf-8")

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(
        "dekk.install.ShellDetector.detect",
        lambda self: ShellInfo(kind=ShellKind.ZSH),
    )

    result = BinaryInstaller(project_root=project_dir).install_python_shim(
        script,
        name="demo",
        install_dir=tmp_path / "bin",
    )

    shell_config = home / ".zshrc"
    assert result.in_path is True
    assert "added to shell config" in result.message
    assert shell_config.exists()
    assert str((tmp_path / "bin").resolve()) in shell_config.read_text(encoding="utf-8")


def test_install_binary_uses_powershell_profile_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    source = project_dir / "demo"
    source.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    source.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    config_home = home / ".config"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(
        "dekk.install.ShellDetector.detect",
        lambda self: ShellInfo(kind=ShellKind.PWSH),
    )

    result = BinaryInstaller(project_root=project_dir).install_binary(
        source,
        install_dir=tmp_path / "bin",
    )

    profile = config_home / "powershell" / "Microsoft.PowerShell_profile.ps1"
    assert result.in_path is True
    assert profile.exists()
    assert str((tmp_path / "bin").resolve()) in profile.read_text(encoding="utf-8")


def test_uninstall_wrapper_can_remove_shell_config_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    shell_config = home / ".zshrc"
    shell_config.write_text("", encoding="utf-8")

    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    wrapper = install_dir / "demo"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")

    marker = f'# dekk: {project_dir.name} install dir\nexport PATH="{install_dir}:$PATH"\n'
    shell_config.write_text(marker, encoding="utf-8")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        "dekk.install.ShellDetector.detect",
        lambda self: ShellInfo(kind=ShellKind.ZSH),
    )

    result = BinaryInstaller(project_root=project_dir).uninstall_wrapper(
        "demo",
        install_dir=install_dir,
        clean_shell=True,
    )

    assert not result.bin_path.exists()
    assert "removed shell config entry" in result.message
    assert shell_config.read_text(encoding="utf-8") == ""
