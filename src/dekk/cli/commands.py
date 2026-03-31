"""CLI commands for dekk -- activate, init, uninstall, wrap."""

from __future__ import annotations

import importlib.resources as resources
import re
from pathlib import Path
from typing import Final

try:
    import typer
except ImportError as err:
    raise ImportError(
        "typer is required. Install or repair the package with: pip install --upgrade dekk"
    ) from err

from dekk.cli.errors import ConfigError, NotFoundError
from dekk.cli.styles import print_error, print_info, print_success

DEFAULT_DIRECTORY_ARGUMENT: Final = typer.Argument(
    Path("."),
    help="Directory to initialize",
)
TARGET_ARGUMENT: Final = typer.Argument(
    ...,
    help="Script or binary to install",
)
WRAP_NAME_ARGUMENT: Final = typer.Argument(
    ...,
    help="Name for the wrapper binary",
)
WRAP_TARGET_ARGUMENT: Final = typer.Argument(
    ...,
    help="Binary or script to wrap",
)
UNINSTALL_NAME_ARGUMENT: Final = typer.Argument(
    ...,
    help="Name of the wrapper to remove",
)
EXAMPLE_TEMPLATE_ARGUMENT: Final = typer.Argument(
    "quickstart",
    help="Built-in template name",
)
NAME_OPTION: Final = typer.Option(None, "--name", "-n", help="Project name")
EXAMPLE_OPTION: Final = typer.Option(
    None,
    "--example",
    help="Start from a built-in template (quickstart, minimal, conda, or agents)",
)
FORCE_OPTION: Final = typer.Option(
    False,
    "--force",
    "-f",
    help="Overwrite existing .dekk.toml",
)
SHELL_OPTION: Final = typer.Option(
    None,
    "--shell",
    help="Target shell for activation output (bash, zsh, fish, tcsh, powershell, pwsh)",
)
PYTHON_OPTION: Final = typer.Option(
    None,
    "--python",
    help="Python interpreter for script targets",
)
INSTALL_DIR_OPTION: Final = typer.Option(
    None,
    "--install-dir",
    "-d",
    help="Installation directory (default: ./.install)",
)
UNINSTALL_DIR_OPTION: Final = typer.Option(
    None,
    "--install-dir",
    "-d",
    help="Directory to look in (default: ./.install)",
)
SPEC_OPTION: Final = typer.Option(
    None,
    "--spec",
    "-s",
    help="Path to .dekk.toml (default: auto-detect near the target)",
)
WRAP_SPEC_OPTION: Final = typer.Option(
    None,
    "--spec",
    "-s",
    help="Path to .dekk.toml (default: auto-detect)",
)
REMOVE_PATH_OPTION: Final = typer.Option(
    False,
    "--remove-path",
    help="Also remove this project's PATH export from the shell config",
)
UPDATE_SHELL_OPTION: Final = typer.Option(
    False,
    "--update-shell",
    help="Add install directory to shell config (opt-in)",
)
EXAMPLE_OUTPUT_OPTION: Final = typer.Option(
    None,
    "--output",
    "-o",
    help="Write the example to a file instead of stdout",
)
EXAMPLE_NAME_OPTION: Final = typer.Option(
    None,
    "--name",
    "-n",
    help="Project name to inject into the template",
)
EXAMPLE_FORCE_OPTION: Final = typer.Option(
    False,
    "--force",
    "-f",
    help="Overwrite the output file if it exists",
)
PROJECT_SPEC_FILENAME: Final = ".dekk.toml"

# ---------------------------------------------------------------------------
# activate
# ---------------------------------------------------------------------------


def activate(
    shell: str | None = SHELL_OPTION,
) -> None:
    """Activate project environment from .dekk.toml.

    Examples:
        eval "$(dekk activate --shell bash)"
        Invoke-Expression (& dekk activate --shell powershell | Out-String)
    """
    from dekk.environment.activation import EnvironmentActivator
    from dekk.environment.spec import find_envspec
    from dekk.shell import ShellDetector

    spec_file = find_envspec()
    if not spec_file:
        raise NotFoundError(f"No {PROJECT_SPEC_FILENAME} found", hint="Run 'dekk init'")

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
# Variables with {{project}}, {{environment}}, {{home}} placeholders
# MY_VAR = "{{project}}/data"

[paths]
# Paths to add to PATH
# bin = ["{{project}}/bin"]
"""

EXAMPLE_TEMPLATES = {
    "quickstart": "quickstart.toml",
    "minimal": "minimal.toml",
    "conda": "conda.toml",
    "agents": "agents.toml",
}


def _load_example_template(template_name: str, project_name: str | None = None) -> str:
    """Load a built-in example template and optionally rewrite the project name."""
    template_file = EXAMPLE_TEMPLATES.get(template_name)
    if template_file is None:
        available = ", ".join(sorted(EXAMPLE_TEMPLATES))
        raise ConfigError(
            f"Unknown example template: {template_name}",
            hint=f"Choose one of: {available}",
        )

    try:
        template_path = resources.files("dekk").joinpath("templates", template_file)
        content = template_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Built-in template is missing: {template_name}",
            hint="Reinstall dekk to restore packaged templates",
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
    directory: Path = DEFAULT_DIRECTORY_ARGUMENT,
    name: str | None = NAME_OPTION,
    example: str | None = EXAMPLE_OPTION,
    force: bool = FORCE_OPTION,
) -> None:
    """Initialize `.dekk.toml` from a chosen template."""
    target_dir = directory.resolve()
    spec_file = target_dir / PROJECT_SPEC_FILENAME

    if spec_file.exists() and not force:
        raise ConfigError(
            f"{PROJECT_SPEC_FILENAME} already exists: {spec_file}",
            hint="Use --force to overwrite",
        )

    project_name = name or target_dir.name
    if example:
        content = _load_example_template(example, project_name=project_name)
    else:
        content = TEMPLATE.format(project_name=project_name)

    spec_file.write_text(content, encoding="utf-8")
    print_success(f"Created {spec_file}")


def example(
    template: str = EXAMPLE_TEMPLATE_ARGUMENT,
    output: Path | None = EXAMPLE_OUTPUT_OPTION,
    name: str | None = EXAMPLE_NAME_OPTION,
    force: bool = EXAMPLE_FORCE_OPTION,
) -> None:
    """Print or write a built-in `.dekk.toml` example."""
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
    name: str = UNINSTALL_NAME_ARGUMENT,
    install_dir: Path | None = UNINSTALL_DIR_OPTION,
    remove_path: bool = REMOVE_PATH_OPTION,
) -> None:
    """Remove an installed wrapper script.

    Examples:
        dekk uninstall myapp
        dekk uninstall myapp --install-dir ./.install
        dekk uninstall myapp --remove-path
    """
    from dekk.execution.install import BinaryInstaller

    project_root = Path.cwd().resolve()
    result = BinaryInstaller(project_root=project_root).uninstall_wrapper(
        name,
        install_dir=install_dir,
        clean_shell=remove_path,
    )
    print_success(result.message)


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def install(
    target: Path = TARGET_ARGUMENT,
    name: str | None = typer.Option(None, "--name", "-n", help="Installed command name"),
    python: Path | None = PYTHON_OPTION,
    install_dir: Path | None = INSTALL_DIR_OPTION,
    spec_file: Path | None = SPEC_OPTION,
    update_shell: bool = UPDATE_SHELL_OPTION,
) -> None:
    """Install a runnable project command with the right environment behavior.

    If `.dekk.toml` is missing, dekk writes a minimal starter config from the
    detected project files before installing the wrapper.
    """
    from dekk.environment.bootstrap import ensure_envspec
    from dekk.execution.install import BinaryInstaller

    target = target.resolve()
    if not target.exists():
        raise NotFoundError(f"Target not found: {target}", hint="Build it first or check the path")

    bootstrap = ensure_envspec(target.parent, target=target) if spec_file is None else None
    resolved_spec_file = spec_file.resolve() if spec_file else bootstrap.path
    install_name = name or target.stem
    installer = BinaryInstaller(project_root=resolved_spec_file.parent)

    result = installer.install_wrapper(
        target=target,
        spec_file=resolved_spec_file,
        python=python.resolve() if python else None,
        name=install_name,
        install_dir=install_dir,
        update_shell=update_shell,
    )
    if bootstrap is not None and bootstrap.created:
        print_info(f"Created {bootstrap.path.name} from {bootstrap.source}")
    print_success(result.message)
    if not result.in_path:
        print_info(f"Add {result.bin_path.parent} to your PATH")


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------


def test(extra_args: list[str] | None = None) -> None:
    """Run the project's default test command."""
    from dekk.cli.styles import print_info
    from dekk.execution.test_runner import resolve_test_plan, run_test_plan

    args = extra_args or []
    plan = resolve_test_plan(Path.cwd(), args)
    print_info(f"Running {plan.label}: {' '.join(plan.cmd)}")
    raise typer.Exit(run_test_plan(plan))


# ---------------------------------------------------------------------------
# wrap
# ---------------------------------------------------------------------------


def wrap(
    name: str = WRAP_NAME_ARGUMENT,
    target: Path = WRAP_TARGET_ARGUMENT,
    python: Path | None = PYTHON_OPTION,
    install_dir: Path | None = INSTALL_DIR_OPTION,
    spec_file: Path | None = WRAP_SPEC_OPTION,
    update_shell: bool = UPDATE_SHELL_OPTION,
) -> None:
    """Generate a self-contained wrapper that activates your environment automatically.

    The wrapper bakes conda, paths, and env vars into a single executable script.
    No activation, no PATH setup -- just run the command and it works.

    Examples:
        dekk wrap myapp ./bin/myapp
        dekk wrap myapp ./tools/cli.py --python /opt/conda/envs/myapp/bin/python3
        dekk wrap myapp .\\dist\\myapp.exe --install-dir .\\.install
    """
    from dekk.environment.bootstrap import ensure_envspec
    from dekk.execution.install import BinaryInstaller

    target = target.resolve()
    if not target.exists():
        print_error(f"Target not found: {target}")
        raise typer.Exit(1)

    bootstrap = None
    if spec_file:
        if not spec_file.exists():
            print_error(f"Spec file not found: {spec_file}")
            raise typer.Exit(1)
        resolved_spec_file = spec_file.resolve()
    else:
        bootstrap = ensure_envspec(target.parent, target=target)
        resolved_spec_file = bootstrap.path

    try:
        result = BinaryInstaller(project_root=resolved_spec_file.parent).install_wrapper(
            target=target,
            spec_file=resolved_spec_file,
            python=python.resolve() if python else None,
            name=name,
            install_dir=install_dir,
            update_shell=update_shell,
        )
        if bootstrap is not None and bootstrap.created:
            print_info(f"Created {bootstrap.path.name} from {bootstrap.source}")
        print_success(result.message)
        if not result.in_path:
            print_info(f"Add {result.bin_path.parent} to your PATH")
    except Exception as err:
        print_error(f"Failed to generate wrapper: {err}")
        raise typer.Exit(1) from err
