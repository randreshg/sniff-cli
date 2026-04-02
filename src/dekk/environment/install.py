"""One-command install pipeline: setup -> build -> components -> (optionally) wrap.

Also provides ``run_uninstall`` to tear down the environment, wrappers,
and dekk state directory.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dekk.cli.install_runner import InstallRunner, InstallRunnerResult, select_components
from dekk.environment.spec import PREPEND_ENV_VARS, EnvironmentSpec

__all__ = ["run_install", "run_uninstall"]


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


def _check_requires(requires: list[str], env: dict[str, str] | None) -> list[str]:
    """Return names of required tools that are not found on PATH."""
    path = env.get("PATH") if env else None
    return [r for r in requires if not shutil.which(r, path=path)]


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
    title = f"{spec.project_name.upper()} Install"

    # ── Phase 1: Setup environment (must complete before tool checks) ──
    if spec.environment:
        from dekk.environment.resolver import resolve_environment

        resolved = resolve_environment(spec, project_root=project_root)
        if resolved:
            try:
                setup_cmd = resolved.get_setup_command(project_root=project_root, force=force)
            except Exception as e:
                from dekk.cli.styles import print_error

                print_error(str(e))
                return InstallRunnerResult(title=title, log_path=log_path)
            if setup_cmd:
                env_runner = InstallRunner(title, log_path=log_path)
                env_runner.add("Setting up environment", setup_cmd)
                env_result = env_runner.run(cwd=project_root, verbose=verbose)
                if not env_result.ok:
                    return env_result
            else:
                from dekk.cli.styles import print_info

                print_info("Environment already exists (use --force to recreate)")

    # ── Activate environment (now reflects any packages just installed) ──
    activated_env: dict[str, str] | None = None
    if spec.environment:
        from dekk.environment.activation import EnvironmentActivator

        try:
            activator = EnvironmentActivator(spec, project_root)
            activation = activator.activate()
            activated_env = _merge_env(activation)
        except Exception:
            activated_env = None  # fall through without custom env

    # ── Gate 1: Check project-wide [tools] ──
    if spec.tools:
        from dekk.cli.output import check_tool_specs
        from dekk.cli.styles import print_blank, print_error, print_numbered_list, print_section

        print_section("Dependencies")
        activated_path = activated_env.get("PATH") if activated_env else None
        missing_tools = check_tool_specs(spec.tools, path=activated_path)
        if missing_tools:
            print_blank()
            print_error("Required tools missing:")
            print_numbered_list(missing_tools)
            print_blank()
            from dekk.cli.styles import print_info

            print_info("Install missing tools and re-run `dekk install`.")
            return InstallRunnerResult(title=title, log_path=log_path)

    # ── Phase 2: Build + components ──
    runner = InstallRunner(title, log_path=log_path)

    if spec.install and spec.install.build:
        runner.add("Building project", spec.install.build)

    selected: list[str] = []
    if spec.install and spec.install.components:
        selection = select_components(
            spec.install.components,
            preselect=components,
            interactive=interactive,
        )
        if selection is None:
            from dekk.cli.styles import print_blank, print_info

            print_blank()
            print_info("Installation cancelled.")
            return InstallRunnerResult(title=title, log_path=log_path)
        selected = selection

        # Gate 2: Check ALL selected components' requires upfront
        comp_missing: list[str] = []
        for comp in spec.install.components:
            if comp.name in selected:
                missing = _check_requires(comp.requires, activated_env)
                if missing:
                    comp_missing.append(
                        f"{comp.label}: missing {', '.join(missing)}"
                    )
        if comp_missing:
            from dekk.cli.styles import print_blank, print_error, print_info

            print_blank()
            print_error("Cannot install selected components:")
            for line in comp_missing:
                print_error(f"  {line}")
            print_blank()
            print_info("Install missing tools and re-run `dekk install`.")
            return InstallRunnerResult(title=title, log_path=log_path)

        for comp in spec.install.components:
            if comp.name in selected:
                runner.add(f"Installing {comp.label}", comp.run)

    # Step: Wrap (only if --wrap flag passed AND install.wrap configured)
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

    result = runner.run(env=activated_env, cwd=project_root, verbose=verbose)
    result.selected_components = selected
    return result


def run_uninstall(project_root: Path) -> list[str]:
    """Remove the runtime environment, wrappers, and dekk state.

    Returns a list of human-readable messages describing what was removed.
    """
    from dekk.cli.progress import spinner
    from dekk.cli.styles import print_success

    spec = EnvironmentSpec.from_file(project_root / ".dekk.toml")
    removed: list[str] = []

    # 1. Remove the wrapper + clean shell config (if install.wrap is configured)
    if spec.install and spec.install.wrap:
        from dekk.execution.install import BinaryInstaller

        wr = BinaryInstaller(project_root=project_root).uninstall_wrapper(
            spec.install.wrap.name, clean_shell=True,
        )
        removed.append(wr.message)
        print_success(wr.message)

    # 2. Remove the .install/ directory if empty
    install_dir = project_root / ".install"
    if install_dir.is_dir() and not any(install_dir.iterdir()):
        install_dir.rmdir()
        removed.append(f"Removed empty directory: {install_dir}")

    # 3. Remove the conda/venv environment (can take a while for multi-GB envs)
    dekk_dir = project_root / ".dekk"
    env_dir = dekk_dir / "env"
    if env_dir.is_dir():
        with spinner("Removing environment..."):
            shutil.rmtree(env_dir)
        msg = f"Removed environment: {env_dir}"
        removed.append(msg)
        print_success(msg)

    # 4. Remove install log
    log_path = dekk_dir / "install.log"
    if log_path.is_file():
        log_path.unlink()
        msg = f"Removed log: {log_path}"
        removed.append(msg)
        print_success(msg)

    # 5. Remove .dekk/ directory if empty
    if dekk_dir.is_dir() and not any(dekk_dir.iterdir()):
        dekk_dir.rmdir()
        removed.append(f"Removed empty directory: {dekk_dir}")

    if not removed:
        removed.append("Nothing to remove.")

    return removed
