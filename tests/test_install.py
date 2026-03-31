"""Tests for dekk.execution.install."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from dekk.cli.errors import NotFoundError
from dekk.execution.install import BinaryInstaller, InstallResult
from dekk.shell import ShellInfo, ShellKind


def _write_spec(project_dir: Path) -> Path:
    spec = project_dir / ".dekk.toml"
    spec.write_text('[project]\nname = "demo"\n', encoding="utf-8")
    return spec


def test_install_wrapper_prefers_local_venv_python(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    spec = _write_spec(project_dir)
    script = project_dir / "tools" / "cli.py"
    script.parent.mkdir()
    script.write_text("print('hi')\n", encoding="utf-8")

    venv_python = project_dir / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    expected = InstallResult(bin_path=tmp_path / "bin" / "demo", in_path=False, message="ok")
    with patch(
        "dekk.execution.wrapper.WrapperGenerator.install_from_spec",
        return_value=expected,
    ) as install_mock:
        result = BinaryInstaller(project_root=project_dir).install_wrapper(
            script,
            spec_file=spec,
            name="demo",
            install_dir=tmp_path / "bin",
        )

    assert result == expected
    assert install_mock.call_args.kwargs["python"] == venv_python


def test_install_wrapper_falls_back_to_path_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    spec = _write_spec(project_dir)
    script = project_dir / "tools" / "cli.py"
    script.parent.mkdir()
    script.write_text("print('hi')\n", encoding="utf-8")

    path_python = tmp_path / "python3"
    path_python.write_text("", encoding="utf-8")
    monkeypatch.setattr("dekk.execution.install.shutil.which", lambda name: str(path_python))

    expected = InstallResult(bin_path=tmp_path / "bin" / "demo", in_path=False, message="ok")
    with patch(
        "dekk.execution.wrapper.WrapperGenerator.install_from_spec",
        return_value=expected,
    ) as install_mock:
        BinaryInstaller(project_root=project_dir).install_wrapper(
            script,
            spec_file=spec,
            name="demo",
            install_dir=tmp_path / "bin",
        )

    assert install_mock.call_args.kwargs["python"] == path_python.resolve()


def test_install_wrapper_requires_python_for_python_scripts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    spec = _write_spec(project_dir)
    script = project_dir / "tools" / "cli.py"
    script.parent.mkdir()
    script.write_text("print('hi')\n", encoding="utf-8")

    monkeypatch.setattr("dekk.execution.install.shutil.which", lambda name: None)

    with pytest.raises(NotFoundError, match="No Python interpreter found"):
        BinaryInstaller(project_root=project_dir).install_wrapper(
            script,
            spec_file=spec,
            install_dir=tmp_path / "bin",
        )


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
        "dekk.execution.install.ShellDetector.detect",
        lambda self: ShellInfo(kind=ShellKind.PWSH),
    )

    result = BinaryInstaller(project_root=project_dir).install_binary(
        source,
        install_dir=tmp_path / "bin",
        update_shell=True,
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
        "dekk.execution.install.ShellDetector.detect",
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
