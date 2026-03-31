from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_render_bootstrap_spec_for_python_project(tmp_path: Path) -> None:
    from dekk.environment.bootstrap import render_bootstrap_spec

    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "demo-app"\n'
        "\n"
        "[build-system]\n"
        'build-backend = "setuptools.build_meta"\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()

    content, source = render_bootstrap_spec(tmp_path)

    assert source == "pyproject.toml"
    assert 'name = "demo-app"' in content
    assert "[python]" in content
    assert 'pyproject = "pyproject.toml"' in content
    assert 'python = { command = "python" }' in content
    assert 'build = { run = "python -m build", description = "Build the project" }' in content
    assert 'test = { run = "pytest -q", description = "Run the test suite" }' in content


def test_render_bootstrap_spec_includes_conda_environment(tmp_path: Path) -> None:
    from dekk.environment.bootstrap import render_bootstrap_spec

    (tmp_path / "environment.yaml").write_text("name: demo\n", encoding="utf-8")

    content, _ = render_bootstrap_spec(tmp_path)

    assert "[environment]" in content
    assert 'type = "conda"' in content
    assert 'path = "{project}/.dekk/env"' in content
    assert 'file = "environment.yaml"' in content


def test_ensure_envspec_uses_project_root_for_nested_targets(tmp_path: Path) -> None:
    from dekk.environment.bootstrap import ensure_envspec

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo-app'\n\n[build-system]\nbuild-backend = 'setuptools.build_meta'\n",
        encoding="utf-8",
    )
    script = tmp_path / "tools" / "cli.py"
    script.parent.mkdir()
    script.write_text("print('hi')\n", encoding="utf-8")

    result = ensure_envspec(script.parent, target=script)

    assert result.created is True
    assert result.path == tmp_path / ".dekk.toml"
    assert result.path.exists()


def test_install_auto_creates_spec_for_target(tmp_path: Path) -> None:
    from dekk.cli.commands import install
    from dekk.execution.install import InstallResult

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo-app'\n\n[build-system]\nbuild-backend = 'setuptools.build_meta'\n",
        encoding="utf-8",
    )
    script = tmp_path / "tools" / "cli.py"
    script.parent.mkdir()
    script.write_text("print('hi')\n", encoding="utf-8")

    expected = InstallResult(bin_path=tmp_path / ".install" / "demo", in_path=True, message="ok")
    with patch(
        "dekk.execution.install.BinaryInstaller.install_wrapper",
        return_value=expected,
    ) as install_mock:
        install(
            target=script,
            name="demo",
            python=None,
            install_dir=None,
            spec_file=None,
            update_shell=False,
        )

    assert (tmp_path / ".dekk.toml").is_file()
    assert install_mock.call_args.kwargs["spec_file"] == tmp_path / ".dekk.toml"
