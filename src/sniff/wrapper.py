"""Self-contained wrapper script generation for zero-activation CLI tools.

The WrapperGenerator creates shell scripts that bake in all environment
variables, PATH entries, and conda configuration from a .sniff.toml spec.
The result is a single executable file that activates the full project
environment and execs the target binary -- no manual activation needed.

Usage:
    from sniff.wrapper import WrapperGenerator

    # From .sniff.toml (simplest)
    result = WrapperGenerator.install_from_spec(
        spec_file=Path(".sniff.toml"),
        target=Path("bin/myapp"),
        name="myapp",
    )

    # With a Python entry point
    result = WrapperGenerator.install_from_spec(
        spec_file=Path(".sniff.toml"),
        target=Path("tools/cli.py"),
        python=Path("/path/to/conda/bin/python3"),
        name="myapp",
    )
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .activation import ActivationResult, EnvironmentActivator
from .cli.errors import NotFoundError, ValidationError
from .envspec import EnvironmentSpec, find_envspec
from .install import InstallResult


# ---------------------------------------------------------------------------
# Shell-safe quoting
# ---------------------------------------------------------------------------

# Characters that are safe inside single quotes in POSIX sh.  Everything else
# is handled by replacing ' with '\'' (end quote, escaped literal quote, start
# quote again).  We use single-quoting because it is the most predictable
# strategy for #!/bin/sh scripts -- only single-quote itself needs escaping.

def _sh_quote(value: str) -> str:
    """Quote *value* for safe embedding in a POSIX ``#!/bin/sh`` script.

    Uses single-quoting so that ``$``, ``"``, ``\\``, backticks, and all
    other shell metacharacters are treated literally.

    The only character that cannot appear inside single quotes is the
    single-quote itself; we handle it with the standard ``'\\''`` idiom
    (end the current single-quoted segment, emit an escaped literal
    single-quote, re-open a new single-quoted segment).

    Returns the quoted string *including* the surrounding quotes.
    """
    if not value:
        return "''"
    return "'" + value.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# WrapperGenerator
# ---------------------------------------------------------------------------


class WrapperGenerator:
    """Generate and install self-contained shell wrapper scripts.

    A wrapper is a tiny ``#!/bin/sh`` script that:

    1. Exports every environment variable needed by the project (hardcoded
       absolute values -- no runtime detection).
    2. Prepends the required directories to ``PATH``.
    3. ``exec``s the target binary (or ``python target``), replacing the
       wrapper process so there is a clean PID.

    Because the wrapper uses ``/bin/sh`` and plain ``export`` statements it
    works in *any* shell the user may be running -- bash, zsh, fish, tcsh,
    dash, etc.  No ``conda activate`` is needed.

    The class is intentionally stateless: every method is either a
    ``@staticmethod`` or a ``@classmethod`` that composes the statics.
    """

    # ------------------------------------------------------------------ #
    # Core generation
    # ------------------------------------------------------------------ #

    @staticmethod
    def generate(
        target: Path,
        env_vars: dict[str, str],
        path_prepends: list[str],
        project_name: str,
        *,
        prepend_vars: Optional[dict[str, str]] = None,
        python: Optional[Path] = None,
    ) -> str:
        """Generate a self-contained ``#!/bin/sh`` wrapper script.

        Args:
            target: Absolute path to the binary (or Python script) to run.
            env_vars: Mapping of environment-variable names to their values.
                Values are embedded literally (hard set).
            path_prepends: Directories to prepend to ``$PATH`` (in order).
            project_name: Human-readable project label (used in the header
                comment only).
            prepend_vars: Mapping of variable names to values that should be
                *prepended* to existing values (e.g. ``LD_LIBRARY_PATH``).
                Each is rendered as ``export VAR="value:$VAR"``.
            python: If provided, the wrapper will ``exec python target "$@"``
                instead of ``exec target "$@"``.

        Returns:
            The complete wrapper script as a string, ready to be written to
            a file and made executable.

        Raises:
            NotFoundError: If *target* does not exist on disk.
        """
        target = target.resolve()
        if not target.exists():
            raise NotFoundError(
                f"Target does not exist: {target}",
                hint="Build or install the target binary first",
            )

        if python is not None:
            python = python.resolve()
            if not python.exists():
                raise NotFoundError(
                    f"Python interpreter does not exist: {python}",
                    hint="Check the conda environment or virtualenv path",
                )

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        lines: list[str] = [
            "#!/bin/sh",
            f"# Wrapper for {project_name}",
            f"# Generated by sniff on {timestamp}",
            f"# Regenerate with: sniff wrapper --target {target}"
            + (f" --python {python}" if python else ""),
            "#",
            "# This script bakes in the full project environment so the",
            "# tool can be invoked without manually activating anything.",
            "",
        ]

        # -- Environment variables ------------------------------------------
        if env_vars:
            lines.append("# --- Environment variables ---")
            for name, value in env_vars.items():
                # Skip PATH -- handled separately via path_prepends.
                if name == "PATH":
                    continue
                lines.append(f"export {name}={_sh_quote(value)}")
            lines.append("")

        # -- Prepend variables (LD_LIBRARY_PATH, etc.) -----------------------
        if prepend_vars:
            for name, value in prepend_vars.items():
                escaped = _sh_escape_double(value)
                lines.append(f'export {name}="{escaped}:${name}"')
            lines.append("")

        # -- PATH prepends ---------------------------------------------------
        if path_prepends:
            lines.append("# --- PATH ---")
            raw_joined = ":".join(path_prepends)
            lines.append(f'export PATH="{_sh_escape_double(raw_joined)}:$PATH"')
            lines.append("")

        # -- Exec target -----------------------------------------------------
        lines.append("# --- Exec (replaces this process) ---")
        if python:
            lines.append(f'exec {_sh_quote(str(python))} {_sh_quote(str(target))} "$@"')
        else:
            lines.append(f'exec {_sh_quote(str(target))} "$@"')
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def from_spec(
        cls,
        spec_file: Path | EnvironmentSpec,
        project_root: Path,
        target: Path,
        *,
        python: Optional[Path] = None,
    ) -> str:
        """Generate a wrapper from a ``.sniff.toml`` spec (or ``EnvironmentSpec``).

        This resolves the full environment (conda prefix, env vars, PATH
        entries) via :class:`~sniff.activation.EnvironmentActivator` and
        then delegates to :meth:`generate`.

        Args:
            spec_file: Path to a ``.sniff.toml`` file, or an already-parsed
                :class:`~sniff.envspec.EnvironmentSpec`.
            project_root: Root directory of the project (used for placeholder
                expansion and as the activation context).
            target: Absolute (or project-relative) path to the binary.
            python: Optional Python interpreter for script targets.

        Returns:
            The wrapper script as a string.
        """
        if isinstance(spec_file, EnvironmentSpec):
            spec = spec_file
        else:
            spec_file = Path(spec_file).resolve()
            spec = EnvironmentSpec.from_file(spec_file)

        project_root = Path(project_root).resolve()

        activator = EnvironmentActivator(spec, project_root)
        result = activator.activate()

        return cls._generate_from_activation(
            result,
            target=target,
            project_name=spec.project_name,
            python=python,
        )

    @classmethod
    def from_activation(
        cls,
        activation: ActivationResult,
        target: Path,
        project_name: str,
        *,
        python: Optional[Path] = None,
    ) -> str:
        """Generate a wrapper from an existing :class:`ActivationResult`.

        Useful when the caller has already performed activation and wants
        to reuse the result.

        Args:
            activation: A previously obtained activation result.
            target: Absolute path to the binary.
            project_name: Project label for the header comment.
            python: Optional Python interpreter for script targets.

        Returns:
            The wrapper script as a string.
        """
        return cls._generate_from_activation(
            activation,
            target=target,
            project_name=project_name,
            python=python,
        )

    # ------------------------------------------------------------------ #
    # Installation
    # ------------------------------------------------------------------ #

    @staticmethod
    def install(
        script: str,
        name: str,
        *,
        install_dir: Optional[Path] = None,
    ) -> InstallResult:
        """Write a wrapper script to disk and make it executable.

        Args:
            script: The wrapper script content (as returned by
                :meth:`generate`, :meth:`from_spec`, etc.).
            name: File name for the wrapper (e.g. ``"myapp"``).  Must not
                contain path separators.
            install_dir: Directory in which to place the wrapper.  Defaults
                to ``~/.local/bin`` which is on ``$PATH`` for most Linux
                distributions.

        Returns:
            An :class:`~sniff.install.InstallResult` with the written path,
            whether the directory is in ``$PATH``, and a human-readable
            message.

        Raises:
            ValidationError: If *name* contains a path separator.
        """
        if os.sep in name or (os.altsep and os.altsep in name):
            raise ValidationError(
                f"Wrapper name must not contain path separators: {name!r}",
                hint="Pass just the file name, e.g. 'myapp'",
            )

        if install_dir is None:
            install_dir = Path.home() / ".local" / "bin"

        install_dir = Path(install_dir).resolve()
        install_dir.mkdir(parents=True, exist_ok=True)

        wrapper_path = install_dir / name
        wrapper_path.write_text(script, encoding="utf-8")

        # chmod +x  (owner rwx, group rx, other rx)
        wrapper_path.chmod(
            wrapper_path.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )

        # Check if install_dir is in $PATH
        in_path = _dir_in_path(install_dir)

        if in_path:
            message = f"Installed wrapper '{name}' -> {wrapper_path}"
        else:
            message = (
                f"Installed wrapper '{name}' -> {wrapper_path} "
                f"(add {install_dir} to PATH to use it directly)"
            )

        return InstallResult(bin_path=wrapper_path, in_path=in_path, message=message)

    @staticmethod
    def uninstall(
        name: str,
        *,
        install_dir: Optional[Path] = None,
    ) -> InstallResult:
        """Remove a previously installed wrapper script.

        Idempotent: returns success even if the wrapper does not exist.

        Args:
            name: Wrapper file name (e.g. ``"myapp"``).
            install_dir: Directory the wrapper lives in.  Defaults to
                ``~/.local/bin``.

        Returns:
            :class:`~sniff.install.InstallResult` describing what was removed.
        """
        if install_dir is None:
            install_dir = Path.home() / ".local" / "bin"

        install_dir = Path(install_dir).resolve()
        wrapper_path = install_dir / name

        if wrapper_path.exists():
            wrapper_path.unlink()
            message = f"Removed wrapper '{name}' from {install_dir}"
        else:
            message = f"Wrapper '{name}' not found in {install_dir} (nothing to remove)"

        return InstallResult(bin_path=wrapper_path, in_path=_dir_in_path(install_dir), message=message)

    # ------------------------------------------------------------------ #
    # Convenience: from_spec + install in one shot
    # ------------------------------------------------------------------ #

    @classmethod
    def install_from_spec(
        cls,
        spec_file: Path | EnvironmentSpec,
        target: Path,
        name: str,
        *,
        python: Optional[Path] = None,
        install_dir: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> InstallResult:
        """Generate a wrapper from a spec and install it in one step.

        This is the highest-level entry point: pass a ``.sniff.toml`` path,
        the target binary, and a wrapper name, and get back an installed,
        executable wrapper.

        Args:
            spec_file: Path to ``.sniff.toml`` (or an ``EnvironmentSpec``).
            target: Path to the binary or Python script to wrap.
            name: Wrapper file name (e.g. ``"myapp"``).
            python: Optional Python interpreter.
            install_dir: Where to install (default ``~/.local/bin``).
            project_root: Project root directory.  If *None*, inferred from
                *spec_file*'s parent directory (when a path is given) or the
                current working directory (when an ``EnvironmentSpec`` is
                given).

        Returns:
            :class:`~sniff.install.InstallResult`.
        """
        if project_root is not None:
            root = Path(project_root).resolve()
        elif isinstance(spec_file, Path):
            root = Path(spec_file).resolve().parent
        else:
            root = Path.cwd().resolve()

        script = cls.from_spec(
            spec_file,
            project_root=root,
            target=target,
            python=python,
        )

        return cls.install(script, name, install_dir=install_dir)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def _generate_from_activation(
        cls,
        activation: ActivationResult,
        target: Path,
        project_name: str,
        *,
        python: Optional[Path] = None,
    ) -> str:
        """Translate an ``ActivationResult`` into ``generate()`` arguments.

        The ``ActivationResult.env_vars`` dict may contain a ``"PATH"`` key
        whose value holds the directories to prepend.  We split that out
        into the ``path_prepends`` list so that :meth:`generate` can build
        the correct ``export PATH="...:$PATH"`` line.
        """
        env_vars = dict(activation.env_vars)
        path_prepends: list[str] = []
        prepend_vars: dict[str, str] = {}

        # Variables that should be prepended to existing values, not hard-set.
        _PREPEND_KEYS = {"PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "PYTHONPATH", "PKG_CONFIG_PATH"}

        # Extract PATH entries from the env dict (the activator merges them
        # into a single colon-separated value under the "PATH" key).
        # Filter out entries that are already in the current $PATH to keep
        # the wrapper lean — it appends $PATH at the end anyway.
        raw_path = env_vars.pop("PATH", "")
        if raw_path:
            current_path = set(os.environ.get("PATH", "").split(os.pathsep))
            seen: set[str] = set()
            for p in raw_path.split(os.pathsep):
                if p and p not in current_path and p not in seen:
                    path_prepends.append(p)
                    seen.add(p)

        # Extract other prepend-style vars (LD_LIBRARY_PATH, etc.)
        for key in list(env_vars):
            if key in _PREPEND_KEYS:
                prepend_vars[key] = env_vars.pop(key)

        return cls.generate(
            target=target,
            env_vars=env_vars,
            path_prepends=path_prepends,
            project_name=project_name,
            prepend_vars=prepend_vars,
            python=python,
        )


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _sh_escape_double(value: str) -> str:
    """Escape a string for safe embedding inside POSIX double quotes.

    Inside double quotes the following characters are special and must be
    escaped with a backslash: ``$``, `` ` ``, ``"``, ``\\``, ``!`` (in
    interactive bash, though ``!`` is not special in ``/bin/sh``).

    We escape ``$``, `` ` ``, ``"``, and ``\\`` which covers the POSIX
    specification.  We intentionally do *not* escape ``!`` because the
    wrapper runs under ``/bin/sh`` where it is not special.
    """
    result: list[str] = []
    for ch in value:
        if ch in ('$', '`', '"', '\\'):
            result.append('\\')
        result.append(ch)
    return "".join(result)


def _dir_in_path(directory: Path) -> bool:
    """Return ``True`` if *directory* is present in the current ``$PATH``."""
    dir_resolved = str(directory.resolve())
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            if str(Path(entry).resolve()) == dir_resolved:
                return True
        except (OSError, ValueError):
            continue
    return False
