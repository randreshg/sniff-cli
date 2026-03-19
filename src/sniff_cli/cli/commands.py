"""CLI commands for sniff-cli -- activate, init, uninstall, wrap."""

from __future__ import annotations

import importlib.resources as resources
import os
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    raise ImportError("typer is required. Install or repair the package with: pip install --upgrade sniff-cli")

from sniff_cli.cli.errors import ConfigError, NotFoundError
from sniff_cli.cli.styles import print_error, print_info, print_next_steps, print_success, print_warning


# ---------------------------------------------------------------------------
# activate
# ---------------------------------------------------------------------------


def activate(
    shell: Optional[str] = typer.Option(
        None,
        "--shell",
        help="Target shell for activation output (bash, zsh, fish, tcsh, powershell, pwsh)",
    ),
) -> None:
    """Activate project environment from .sniff-cli.toml.

    Examples:
        eval "$(sniff activate --shell bash)"
        Invoke-Expression (& sniff activate --shell powershell | Out-String)
    """
    from sniff_cli.activation import EnvironmentActivator
    from sniff_cli.envspec import find_envspec
    from sniff_cli.shell import ShellDetector

    spec_file = find_envspec()
    if not spec_file:
        raise NotFoundError("No .sniff-cli.toml found", hint="Run 'sniff init'")

    # Auto-detect shell
    detector = ShellDetector()
    shell_info = detector.detect(shell_override=shell)

    # Activate environment
    activator = EnvironmentActivator.from_cwd()
    result = activator.activate(shell=shell_info.kind.value if shell_info else None)

    # Report errors
    if result.missing_tools:
        print_error(f"Missing required tools: {', '.join(result.missing_tools)}")
        raise typer.Exit(1)

    # Output activation script
    if result.activation_script:
        print(result.activation_script)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

TEMPLATE = """\
[project]
name = "{project_name}"

[tools]
python = {{ command = "python", version = ">=3.10" }}

[env]
# Variables with {{project}}, {{conda}}, {{home}} placeholders
# MY_VAR = "{{project}}/data"

[paths]
# Paths to add to PATH
# bin = ["{{project}}/bin"]
"""

EXAMPLE_TEMPLATES = {
    "quickstart": "quickstart.toml",
    "minimal": "minimal.toml",
    "conda": "conda.toml",
}


def _load_example_template(template_name: str, project_name: Optional[str] = None) -> str:
    """Load a built-in example template and optionally rewrite the project name."""
    template_file = EXAMPLE_TEMPLATES.get(template_name)
    if template_file is None:
        available = ", ".join(sorted(EXAMPLE_TEMPLATES))
        raise ConfigError(
            f"Unknown example template: {template_name}",
            hint=f"Choose one of: {available}",
        )

    try:
        content = resources.files("sniff_cli").joinpath("templates", template_file).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Built-in template is missing: {template_name}",
            hint="Reinstall sniff-cli to restore packaged templates",
        ) from exc

    if project_name:
        content = re.sub(
            r'(?m)^name = "[^"]+"$',
            f'name = "{project_name}"',
            content,
            count=2,
        )
    return content


def init(
    directory: Path = typer.Argument(Path("."), help="Directory to initialize"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name"),
    example: Optional[str] = typer.Option(
        None,
        "--example",
        help="Start from a built-in template (quickstart, minimal, or conda)",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing .sniff-cli.toml"),
) -> None:
    """Initialize .sniff-cli.toml for automatic environment setup."""
    target_dir = directory.resolve()
    spec_file = target_dir / ".sniff-cli.toml"

    if spec_file.exists() and not force:
        raise ConfigError(
            f".sniff-cli.toml already exists: {spec_file}",
            hint="Use --force to overwrite",
        )

    project_name = name or target_dir.name
    if example:
        content = _load_example_template(example, project_name=project_name)
    else:
        content = TEMPLATE.format(project_name=project_name)

    spec_file.write_text(content, encoding="utf-8")
    print_success(f"Created {spec_file} - edit it and run 'sniff activate'")
    print_next_steps([
        f"Review {spec_file.name} and adjust tools, env vars, or conda settings",
        "Run sniff activate --shell bash (or --shell powershell on Windows)",
        "Generate a launcher with sniff wrap <name> <target> when your target exists",
    ])


def example(
    template: str = typer.Argument("quickstart", help="Built-in template name"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write the example to a file instead of stdout"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name to inject into the template"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite the output file if it exists"),
) -> None:
    """Print or write a built-in .sniff-cli.toml example."""
    content = _load_example_template(template, project_name=name)

    if output is None:
        print(content.rstrip())
        return

    output = output.resolve()
    if output.exists() and not force:
        raise ConfigError(
            f"Output file already exists: {output}",
            hint="Use --force to overwrite",
        )

    output.write_text(content, encoding="utf-8")
    print_success(f"Wrote example template to {output}")


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


def uninstall(
    name: str = typer.Argument(..., help="Name of the wrapper to remove"),
    install_dir: Optional[Path] = typer.Option(
        None, "--install-dir", "-d", help="Directory to look in (default: user scripts directory)"
    ),
) -> None:
    """Remove an installed wrapper script.

    Examples:
        sniff uninstall myapp
        sniff uninstall myapp --install-dir /usr/local/bin
        sniff uninstall myapp --install-dir "$env:APPDATA\\Python\\Scripts"
    """
    from sniff_cli.wrapper import WrapperGenerator

    result = WrapperGenerator.uninstall(name, install_dir=install_dir)
    print_success(result.message)


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def install(
    target: Path = typer.Argument(..., help="Script or binary to install"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Installed command name"),
    python: Optional[Path] = typer.Option(None, "--python", help="Python interpreter for script targets"),
    install_dir: Optional[Path] = typer.Option(None, "--install-dir", "-d", help="Installation directory (default: user scripts directory)"),
    spec_file: Optional[Path] = typer.Option(None, "--spec", "-s", help="Path to .sniff-cli.toml (default: auto-detect near the target)"),
) -> None:
    """Install a runnable project command with the right environment behavior.

    Rules:
    - Python scripts default to a self-bootstrapping shim driven by
      ``python -m sniff_cli`` so project dependencies are installed automatically.
    - If a conda-backed ``.sniff-cli.toml`` is present, sniff installs a full
      environment wrapper instead.
    - Non-Python targets require ``.sniff-cli.toml`` because sniff must know
      which environment variables and PATH entries to bake into the wrapper.
    """
    from sniff_cli.conda import CondaDetector
    from sniff_cli.envspec import EnvironmentSpec, find_envspec
    from sniff_cli.install import BinaryInstaller
    from sniff_cli.sniff_os import get_sniff_os

    target = target.resolve()
    if not target.exists():
        raise NotFoundError(f"Target not found: {target}", hint="Build it first or check the path")

    resolved_spec_file = spec_file.resolve() if spec_file else find_envspec(target.parent)
    spec = EnvironmentSpec.from_file(resolved_spec_file) if resolved_spec_file else None

    install_name = name or target.stem
    project_root = resolved_spec_file.parent if resolved_spec_file else target.parent
    installer = BinaryInstaller(project_root=project_root)

    inferred_python = python.resolve() if python else None
    target_is_python = target.suffix.lower() == ".py"

    if target_is_python and inferred_python is None and spec is not None and spec.conda is not None:
        prefix = CondaDetector().find_prefix(spec.conda.name)
        if prefix is not None:
            inferred_python = get_sniff_os().conda_runtime_paths(prefix)[0] / "python"
            if get_sniff_os().name == "windows":
                inferred_python = prefix / "python.exe"
            elif not inferred_python.exists():
                inferred_python = prefix / "bin" / "python"

    if target_is_python and inferred_python is None and (spec is None or spec.conda is None):
        result = installer.install_python_shim(
            target,
            name=install_name,
            install_dir=install_dir,
        )
        print_success(result.message)
        if not result.in_path:
            print_info(f"Add {result.bin_path.parent} to your PATH")
        print_next_steps([
            f"Run {install_name} --help",
            "The first run will create or refresh the local .venv from pyproject.toml if needed",
        ])
        return

    if not target_is_python and spec is None:
        raise NotFoundError(
            "No .sniff-cli.toml found for a non-Python target",
            hint="Run 'sniff init' first or pass --spec",
        )

    result = installer.install_wrapper(
        target=target,
        spec=spec,
        spec_file=resolved_spec_file,
        python=inferred_python,
        name=install_name,
        install_dir=install_dir,
    )
    print_success(result.message)
    if not result.in_path:
        print_info(f"Add {result.bin_path.parent} to your PATH")
    print_next_steps([
        f"Run {install_name} --help",
        "Re-run sniff install after changing .sniff-cli.toml, conda, or the wrapped target path",
    ])


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------


def test(extra_args: Optional[list[str]] = None) -> None:
    """Run the project's default test command."""
    from sniff_cli.cli.errors import ExitCodes
    from sniff_cli.cli.styles import print_info
    from sniff_cli.test_runner import resolve_test_plan, run_test_plan

    args = extra_args or []
    plan = resolve_test_plan(Path.cwd(), args)
    print_info(f"Running {plan.label}: {' '.join(plan.cmd)}")
    raise typer.Exit(run_test_plan(plan))


# ---------------------------------------------------------------------------
# wrap
# ---------------------------------------------------------------------------


def wrap(
    name: str = typer.Argument(..., help="Name for the wrapper binary"),
    target: Path = typer.Argument(..., help="Binary or script to wrap"),
    python: Optional[Path] = typer.Option(None, "--python", help="Python interpreter for script targets"),
    install_dir: Optional[Path] = typer.Option(None, "--install-dir", "-d", help="Installation directory (default: user scripts directory)"),
    spec_file: Optional[Path] = typer.Option(None, "--spec", "-s", help="Path to .sniff-cli.toml (default: auto-detect)"),
) -> None:
    """Generate a self-contained wrapper that activates your environment automatically.

    The wrapper bakes conda, paths, and env vars into a single executable script.
    No activation, no PATH setup -- just run the command and it works.

    Examples:
        sniff wrap myapp ./bin/myapp
        sniff wrap myapp ./tools/cli.py --python /opt/conda/envs/myapp/bin/python3
        sniff wrap myapp .\\dist\\myapp.exe --install-dir "$env:APPDATA\\Python\\Scripts"
    """
    from sniff_cli.wrapper import WrapperGenerator
    from sniff_cli.envspec import EnvironmentSpec, find_envspec

    if spec_file:
        if not spec_file.exists():
            print_error(f"Spec file not found: {spec_file}")
            raise typer.Exit(1)
    else:
        spec_file = find_envspec()
        if not spec_file:
            print_error("No .sniff-cli.toml found")
            print_info("Run 'sniff init' to create one, or pass --spec")
            raise typer.Exit(1)

    target = target.resolve()
    if not target.exists():
        print_error(f"Target not found: {target}")
        raise typer.Exit(1)

    try:
        result = WrapperGenerator.install_from_spec(
            spec_file=spec_file,
            target=target,
            python=python.resolve() if python else None,
            name=name,
            install_dir=install_dir,
        )
        print_success(result.message)
        if not result.in_path:
            print_info(f"Add {result.bin_path.parent} to your PATH")
    except Exception as e:
        print_error(f"Failed to generate wrapper: {e}")
        raise typer.Exit(1)
