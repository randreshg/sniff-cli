"""One-command install pipeline: setup -> build -> components -> (optionally) wrap.

Also provides ``run_uninstall`` to tear down the environment, wrappers,
and dekk state directory.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dekk.cli.install_runner import InstallRunner, InstallRunnerResult, select_components
from dekk.environment.spec import EnvironmentSpec

__all__ = ["run_install", "run_uninstall"]

PREPEND_ENV_VARS = {
    "PATH",
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "PYTHONPATH",
    "PKG_CONFIG_PATH",
}


def _merge_env(activation: object) -> dict[str, str]:
    """Build a full environment dict from an ActivationResult."""
    env = dict(os.environ)
    for key, value in activation.env_vars.items():  # type: ignore[attr-defined]
        if key in PREPEND_ENV_VARS:
            current = env.get(key, "")
            env[key] = f"{value}{os.pathsep}{current}" if current else value
        else:
            env[key] = value
    return env


def run_install(
    project_root: Path,
    force: bool = False,
    verbose: bool = False,
    wrap: bool = False,
    interactive: bool = True,
    components: list[str] | None = None,
) -> InstallRunnerResult:
    """One-command install: setup -> build -> components -> (optionally) wrap.

    Args:
        project_root: Path to project with .dekk.toml.
        force: Recreate environment even if exists.
        verbose: Show log tail on error (human mode).
        wrap: Also install a global CLI wrapper (opt-in).
        interactive: Show component selection prompt (True for humans, False for agents/CI).
        components: Explicit component list (overrides interactive selection).
    """
    spec = EnvironmentSpec.from_file(project_root / ".dekk.toml")
    log_path = project_root / ".dekk" / "install.log"

    runner = InstallRunner(f"{spec.project_name.upper()} Install", log_path=log_path)

    # Step 1: Setup environment (if [environment] configured)
    if spec.environment:
        from dekk.environment.setup import run_setup

        def _setup_with_progress(status_fn):  # type: ignore[no-untyped-def]
            return run_setup(project_root, force=force, on_progress=status_fn).ok

        runner.add("Setting up environment", _setup_with_progress, progress=True)

    # Step 2: Build (if install.build configured)
    build_env: dict[str, str] | None = None
    if spec.install and spec.install.build:
        from dekk.environment.activation import EnvironmentActivator

        try:
            activator = EnvironmentActivator(spec, project_root)
            activation = activator.activate()
            build_env = _merge_env(activation)
        except Exception:
            build_env = None  # fall through to build without custom env
        runner.add("Building project", spec.install.build)

    # Step 3: Optional components (interactive selection or --components flag)
    selected: list[str] = []
    if spec.install and spec.install.components:
        selection = select_components(
            spec.install.components,
            preselect=components,
            interactive=interactive,
        )
        if selection is None:
            # User pressed Escape/Ctrl-C — abort installation
            from dekk.cli.styles import print_blank, print_info

            print_blank()
            print_info("Installation cancelled.")
            return InstallRunnerResult(title=runner.title, log_path=log_path)
        selected = selection
        for comp in spec.install.components:
            if comp.name in selected:
                runner.add(f"Installing {comp.label}", comp.run)

    # Step 4: Wrap (only if --wrap flag passed AND install.wrap configured)
    if wrap and spec.install and spec.install.wrap:
        wrap_spec = spec.install.wrap

        def do_wrap() -> bool:
            from dekk.execution.wrapper import WrapperGenerator

            target = project_root / wrap_spec.target
            if not target.exists():
                return False
            WrapperGenerator.install_from_spec(
                spec_file=project_root / ".dekk.toml",
                target=target,
                name=wrap_spec.name,
                project_root=project_root,
            )
            return True

        runner.add("Installing CLI wrapper", do_wrap)

    result = runner.run(env=build_env, cwd=project_root, verbose=verbose)
    result.selected_components = selected
    return result


def run_uninstall(project_root: Path) -> list[str]:
    """Remove the runtime environment, wrappers, and dekk state.

    Returns a list of human-readable messages describing what was removed.
    """
    spec = EnvironmentSpec.from_file(project_root / ".dekk.toml")
    removed: list[str] = []

    # 1. Remove the wrapper + clean shell config (if install.wrap is configured)
    if spec.install and spec.install.wrap:
        from dekk.execution.install import BinaryInstaller

        wr = BinaryInstaller(project_root=project_root).uninstall_wrapper(
            spec.install.wrap.name, clean_shell=True,
        )
        removed.append(wr.message)

    # 2. Remove the .install/ directory if empty
    install_dir = project_root / ".install"
    if install_dir.is_dir() and not any(install_dir.iterdir()):
        install_dir.rmdir()
        removed.append(f"Removed empty directory: {install_dir}")

    # 3. Remove the conda/venv environment
    dekk_dir = project_root / ".dekk"
    env_dir = dekk_dir / "env"
    if env_dir.is_dir():
        shutil.rmtree(env_dir)
        removed.append(f"Removed environment: {env_dir}")

    # 4. Remove install log
    log_path = dekk_dir / "install.log"
    if log_path.is_file():
        log_path.unlink()
        removed.append(f"Removed log: {log_path}")

    # 5. Remove .dekk/ directory if empty
    if dekk_dir.is_dir() and not any(dekk_dir.iterdir()):
        dekk_dir.rmdir()
        removed.append(f"Removed empty directory: {dekk_dir}")

    if not removed:
        removed.append("Nothing to remove.")

    return removed
