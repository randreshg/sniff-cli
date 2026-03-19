"""Shell detection and integration -- identify shell, generate activation scripts, completions.

Detects the current shell environment, generates activation/deactivation scripts
for environment setup, tab-completion scripts, prompt integration helpers, and
alias suggestions.

Pure detection where possible. Script generation is deterministic output from
detected state -- no subprocess calls, no side effects beyond returning strings.
"""

from __future__ import annotations

import enum
import os
import platform
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Shell detection
# ---------------------------------------------------------------------------

class ShellKind(enum.Enum):
    """Known shell types."""

    BASH = "bash"
    ZSH = "zsh"
    FISH = "fish"
    TCSH = "tcsh"
    POWERSHELL = "powershell"
    PWSH = "pwsh"  # PowerShell Core (cross-platform)
    CMD = "cmd"
    KSH = "ksh"
    DASH = "dash"
    SH = "sh"  # Bourne shell / generic POSIX
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ShellInfo:
    """Detected shell information."""

    kind: ShellKind
    path: str | None = None  # Absolute path to shell binary
    version: str | None = None  # Shell version string
    login_shell: str | None = None  # User's login shell from /etc/passwd or SHELL
    is_interactive: bool = False  # Likely running interactively
    config_files: tuple[str, ...] = ()  # Rc/profile files that exist for this shell

    @property
    def is_posix(self) -> bool:
        """True if the shell uses POSIX-style syntax (export, $VAR)."""
        return self.kind in (
            ShellKind.BASH,
            ShellKind.ZSH,
            ShellKind.KSH,
            ShellKind.DASH,
            ShellKind.SH,
        )

    @property
    def is_csh_family(self) -> bool:
        """True if the shell uses csh-style syntax (setenv, $var)."""
        return self.kind == ShellKind.TCSH

    @property
    def is_fish(self) -> bool:
        """True if using fish shell."""
        return self.kind == ShellKind.FISH

    @property
    def is_powershell(self) -> bool:
        """True if using PowerShell (Windows or Core)."""
        return self.kind in (ShellKind.POWERSHELL, ShellKind.PWSH)

    @property
    def supports_functions(self) -> bool:
        """True if the shell supports function definitions."""
        return self.kind in (
            ShellKind.BASH,
            ShellKind.ZSH,
            ShellKind.FISH,
            ShellKind.KSH,
            ShellKind.POWERSHELL,
            ShellKind.PWSH,
        )


class ShellDetector:
    """Detect the current shell environment.

    Detection strategy (in priority order):
    1. Explicit override via argument
    2. SHELL env var (login shell on Unix)
    3. Parent process name heuristic
    4. Platform default fallback
    """

    # Map shell binary names to ShellKind
    _SHELL_MAP: dict[str, ShellKind] = {
        "bash": ShellKind.BASH,
        "zsh": ShellKind.ZSH,
        "fish": ShellKind.FISH,
        "tcsh": ShellKind.TCSH,
        "csh": ShellKind.TCSH,  # treat csh as tcsh
        "ksh": ShellKind.KSH,
        "dash": ShellKind.DASH,
        "sh": ShellKind.SH,
        "powershell": ShellKind.POWERSHELL,
        "powershell.exe": ShellKind.POWERSHELL,
        "pwsh": ShellKind.PWSH,
        "pwsh.exe": ShellKind.PWSH,
        "cmd": ShellKind.CMD,
        "cmd.exe": ShellKind.CMD,
    }

    def detect(self, shell_override: str | None = None) -> ShellInfo:
        """Detect the current shell.

        Args:
            shell_override: Force a specific shell (e.g., "bash", "fish", "/bin/zsh").
                           Useful when the caller knows what shell to target.

        Returns:
            ShellInfo with detected details. Never raises.
        """
        if shell_override:
            kind = self._parse_shell_name(shell_override)
            path = shell_override if "/" in shell_override or "\\" in shell_override else shutil.which(shell_override)
            return ShellInfo(
                kind=kind,
                path=path,
                login_shell=self._get_login_shell(),
                config_files=self._find_config_files(kind),
            )

        # Try SHELL env var (most reliable on Unix)
        shell_env = os.environ.get("SHELL", "")
        if shell_env:
            kind = self._parse_shell_name(shell_env)
            if kind != ShellKind.UNKNOWN:
                return ShellInfo(
                    kind=kind,
                    path=shell_env if Path(shell_env).is_file() else None,
                    login_shell=shell_env,
                    is_interactive=self._is_interactive(),
                    config_files=self._find_config_files(kind),
                )

        # Try parent process detection
        kind, path = self._detect_from_parent()
        if kind != ShellKind.UNKNOWN:
            return ShellInfo(
                kind=kind,
                path=path,
                login_shell=self._get_login_shell(),
                is_interactive=self._is_interactive(),
                config_files=self._find_config_files(kind),
            )

        # Platform default
        if platform.system() == "Windows":
            kind = ShellKind.POWERSHELL
            path = shutil.which("powershell") or shutil.which("pwsh")
        else:
            kind = ShellKind.SH
            path = shutil.which("sh")

        return ShellInfo(
            kind=kind,
            path=path,
            login_shell=self._get_login_shell(),
            config_files=self._find_config_files(kind),
        )

    def config_candidates(self, kind: ShellKind) -> tuple[Path, ...]:
        """Return candidate config files for a shell, whether or not they exist."""
        try:
            home = Path.home()
        except RuntimeError:
            return ()

        candidates: list[Path] = []

        if kind == ShellKind.BASH:
            candidates = [
                home / ".bashrc",
                home / ".bash_profile",
                home / ".profile",
                home / ".bash_login",
            ]
        elif kind == ShellKind.ZSH:
            candidates = [
                home / ".zshrc",
                home / ".zprofile",
                home / ".zshenv",
                home / ".zlogin",
            ]
        elif kind == ShellKind.FISH:
            config_dir = _user_config_home(home)
            candidates = [
                config_dir / "fish" / "config.fish",
                config_dir / "fish" / "fish_variables",
            ]
        elif kind == ShellKind.TCSH:
            candidates = [
                home / ".tcshrc",
                home / ".cshrc",
                home / ".login",
            ]
        elif kind in (ShellKind.POWERSHELL, ShellKind.PWSH):
            if platform.system() == "Windows":
                from platformdirs import user_documents_path

                docs = user_documents_path()
                candidates = [
                    docs / "PowerShell" / "Microsoft.PowerShell_profile.ps1",
                    docs / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1",
                ]
            else:
                config_dir = _user_config_home(home)
                candidates = [
                    config_dir / "powershell" / "Microsoft.PowerShell_profile.ps1",
                ]
        elif kind in (ShellKind.SH, ShellKind.DASH, ShellKind.KSH):
            candidates = [
                home / ".profile",
            ]

        return tuple(candidates)

    def _parse_shell_name(self, shell_str: str) -> ShellKind:
        """Extract ShellKind from a path or name string."""
        name = Path(shell_str).stem.lower()
        return self._SHELL_MAP.get(name, ShellKind.UNKNOWN)

    def _get_login_shell(self) -> str | None:
        """Get the user's login shell."""
        return os.environ.get("SHELL")

    def _is_interactive(self) -> bool:
        """Heuristic: are we likely in an interactive session?"""
        # If stdout is a TTY, likely interactive
        try:
            return os.isatty(1)
        except Exception:
            return False

    def _detect_from_parent(self) -> tuple[ShellKind, str | None]:
        """Try to detect shell from parent process on Linux/macOS."""
        if platform.system() not in ("Linux", "Darwin"):
            return ShellKind.UNKNOWN, None

        try:
            ppid = os.getppid()
            # Read /proc/ppid/comm on Linux
            comm_path = Path(f"/proc/{ppid}/comm")
            if comm_path.exists():
                name = comm_path.read_text().strip()
                kind = self._SHELL_MAP.get(name, ShellKind.UNKNOWN)
                if kind != ShellKind.UNKNOWN:
                    exe_link = Path(f"/proc/{ppid}/exe")
                    exe_path = None
                    try:
                        exe_path = str(exe_link.resolve())
                    except OSError:
                        pass
                    return kind, exe_path
        except (OSError, ValueError):
            pass

        return ShellKind.UNKNOWN, None

    def _find_config_files(self, kind: ShellKind) -> tuple[str, ...]:
        """Find existing shell config files for the given shell."""
        return tuple(str(p) for p in self.config_candidates(kind) if p.exists())


def _user_config_home(home: Path) -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))


# ---------------------------------------------------------------------------
# Activation script generation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnvVar:
    """An environment variable to set in activation scripts."""

    name: str
    value: str
    prepend_path: bool = False  # If True, prepend value to existing $name


@dataclass(frozen=True)
class ActivationConfig:
    """Configuration for generating activation/deactivation scripts."""

    env_vars: tuple[EnvVar, ...] = ()
    path_prepends: tuple[str, ...] = ()  # Directories to prepend to PATH
    app_name: str = ""  # Used in comments and deactivation function name
    banner: str | None = None  # Optional message to print on activation


class ActivationScriptBuilder:
    """Generate shell-specific activation and deactivation scripts.

    Given a set of environment variables and PATH modifications, produces
    scripts that can be eval'd or sourced to set up the environment.
    """

    def build(self, config: ActivationConfig, shell: ShellKind) -> str:
        """Generate an activation script for the given shell.

        Args:
            config: Variables and paths to set.
            shell: Target shell.

        Returns:
            Script text (ready to be eval'd or sourced).
        """
        builders = {
            ShellKind.BASH: self._build_posix,
            ShellKind.ZSH: self._build_posix,
            ShellKind.SH: self._build_posix,
            ShellKind.DASH: self._build_posix,
            ShellKind.KSH: self._build_posix,
            ShellKind.FISH: self._build_fish,
            ShellKind.TCSH: self._build_tcsh,
            ShellKind.POWERSHELL: self._build_powershell,
            ShellKind.PWSH: self._build_powershell,
            ShellKind.CMD: self._build_cmd,
        }

        builder = builders.get(shell, self._build_posix)
        return builder(config)

    def build_deactivate(self, config: ActivationConfig, shell: ShellKind) -> str:
        """Generate a deactivation script that undoes the activation.

        Args:
            config: The same config used for activation.
            shell: Target shell.

        Returns:
            Script text that undoes the environment changes.
        """
        builders = {
            ShellKind.BASH: self._deactivate_posix,
            ShellKind.ZSH: self._deactivate_posix,
            ShellKind.SH: self._deactivate_posix,
            ShellKind.DASH: self._deactivate_posix,
            ShellKind.KSH: self._deactivate_posix,
            ShellKind.FISH: self._deactivate_fish,
            ShellKind.TCSH: self._deactivate_tcsh,
            ShellKind.POWERSHELL: self._deactivate_powershell,
            ShellKind.PWSH: self._deactivate_powershell,
            ShellKind.CMD: self._deactivate_cmd,
        }

        builder = builders.get(shell, self._deactivate_posix)
        return builder(config)

    # -- POSIX (bash, zsh, sh, dash, ksh) --

    def _build_posix(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"# Activation script for {label}")

        # Save old values for deactivation
        for var in config.env_vars:
            lines.append(f'_OLD_{var.name}="${{{var.name}:-}}"')
        if config.path_prepends:
            lines.append('_OLD_PATH="${PATH:-}"')

        # Set env vars
        for var in config.env_vars:
            if var.prepend_path:
                lines.append(f'export {var.name}="{var.value}${{{var.name}:+:${var.name}}}"')
            else:
                lines.append(f'export {var.name}="{var.value}"')

        # Prepend to PATH
        if config.path_prepends:
            joined = ":".join(config.path_prepends)
            lines.append(f'export PATH="{joined}:$PATH"')

        if config.banner:
            lines.append(f'echo "{config.banner}"')

        return "\n".join(lines) + "\n"

    def _deactivate_posix(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"# Deactivation script for {label}")

        for var in config.env_vars:
            lines.append(f'if [ -n "$_OLD_{var.name}" ]; then')
            lines.append(f'  export {var.name}="$_OLD_{var.name}"')
            lines.append("else")
            lines.append(f"  unset {var.name}")
            lines.append("fi")
            lines.append(f"unset _OLD_{var.name}")

        if config.path_prepends:
            lines.append('if [ -n "$_OLD_PATH" ]; then')
            lines.append('  export PATH="$_OLD_PATH"')
            lines.append("fi")
            lines.append("unset _OLD_PATH")

        return "\n".join(lines) + "\n"

    # -- fish --

    def _build_fish(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"# Activation script for {label}")

        # Save old values
        for var in config.env_vars:
            lines.append(f"set -gx _OLD_{var.name} ${var.name}")
        if config.path_prepends:
            lines.append("set -gx _OLD_PATH $PATH")

        # Set env vars
        for var in config.env_vars:
            if var.prepend_path:
                lines.append(f"set -gx {var.name} {var.value} ${var.name}")
            else:
                lines.append(f"set -gx {var.name} {var.value}")

        # Prepend to PATH
        if config.path_prepends:
            for p in config.path_prepends:
                lines.append(f"set -gx PATH {p} $PATH")

        if config.banner:
            lines.append(f'echo "{config.banner}"')

        return "\n".join(lines) + "\n"

    def _deactivate_fish(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"# Deactivation script for {label}")

        for var in config.env_vars:
            lines.append(f"if set -q _OLD_{var.name}")
            lines.append(f"    set -gx {var.name} $_OLD_{var.name}")
            lines.append(f"    set -e _OLD_{var.name}")
            lines.append("else")
            lines.append(f"    set -e {var.name}")
            lines.append("end")

        if config.path_prepends:
            lines.append("if set -q _OLD_PATH")
            lines.append("    set -gx PATH $_OLD_PATH")
            lines.append("    set -e _OLD_PATH")
            lines.append("end")

        return "\n".join(lines) + "\n"

    # -- tcsh/csh --

    def _build_tcsh(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"# Activation script for {label}")

        # Set env vars
        for var in config.env_vars:
            if var.prepend_path:
                lines.append(f'setenv {var.name} "{var.value}:${var.name}"')
            else:
                lines.append(f'setenv {var.name} "{var.value}"')

        # Prepend to PATH
        if config.path_prepends:
            joined = ":".join(config.path_prepends)
            lines.append(f'setenv PATH "{joined}:$PATH"')

        if config.banner:
            lines.append(f'echo "{config.banner}"')

        return "\n".join(lines) + "\n"

    def _deactivate_tcsh(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"# Deactivation script for {label}")
        lines.append("# tcsh: re-source your .tcshrc to restore environment")

        for var in config.env_vars:
            lines.append(f"unsetenv {var.name}")

        return "\n".join(lines) + "\n"

    # -- PowerShell --

    def _build_powershell(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"# Activation script for {label}")

        # Save old values
        for var in config.env_vars:
            lines.append(f'$env:_OLD_{var.name} = $env:{var.name}')

        if config.path_prepends:
            lines.append('$env:_OLD_PATH = $env:PATH')

        # Set env vars
        for var in config.env_vars:
            if var.prepend_path:
                lines.append(f'$env:{var.name} = "{var.value}" + [IO.Path]::PathSeparator + $env:{var.name}')
            else:
                lines.append(f'$env:{var.name} = "{var.value}"')

        # Prepend to PATH
        if config.path_prepends:
            joined = os.pathsep.join(config.path_prepends)
            lines.append(f'$env:PATH = "{joined}" + [IO.Path]::PathSeparator + $env:PATH')

        if config.banner:
            lines.append(f'Write-Host "{config.banner}"')

        return "\n".join(lines) + "\n"

    def _deactivate_powershell(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"# Deactivation script for {label}")

        for var in config.env_vars:
            lines.append(f"if ($env:_OLD_{var.name}) {{ $env:{var.name} = $env:_OLD_{var.name}; Remove-Item Env:_OLD_{var.name} }} else {{ Remove-Item Env:{var.name} -ErrorAction SilentlyContinue }}")

        if config.path_prepends:
            lines.append("if ($env:_OLD_PATH) { $env:PATH = $env:_OLD_PATH; Remove-Item Env:_OLD_PATH }")

        return "\n".join(lines) + "\n"

    # -- cmd.exe --

    def _build_cmd(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"REM Activation script for {label}")

        for var in config.env_vars:
            lines.append(f"set _OLD_{var.name}=%{var.name}%")
        if config.path_prepends:
            lines.append("set _OLD_PATH=%PATH%")

        for var in config.env_vars:
            if var.prepend_path:
                lines.append(f"if defined {var.name} (")
                lines.append(f'  set "{var.name}={var.value};%{var.name}%"')
                lines.append(") else (")
                lines.append(f'  set "{var.name}={var.value}"')
                lines.append(")")
            else:
                lines.append(f'set "{var.name}={var.value}"')

        if config.path_prepends:
            joined = ";".join(config.path_prepends)
            lines.append('if defined PATH (')
            lines.append(f'  set "PATH={joined};%PATH%"')
            lines.append(") else (")
            lines.append(f'  set "PATH={joined}"')
            lines.append(")")

        if config.banner:
            lines.append(f'echo {config.banner}')

        return "\n".join(lines) + "\n"

    def _deactivate_cmd(self, config: ActivationConfig) -> str:
        lines: list[str] = []
        label = config.app_name or "environment"
        lines.append(f"REM Deactivation script for {label}")

        for var in config.env_vars:
            lines.append(f'if defined _OLD_{var.name} (set "{var.name}=%_OLD_{var.name}%") else set "{var.name}="')
            lines.append(f'set "_OLD_{var.name}="')

        if config.path_prepends:
            lines.append('if defined _OLD_PATH (set "PATH=%_OLD_PATH%")')
            lines.append('set "_OLD_PATH="')

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Tab completion generation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandArg:
    """A positional argument for completion."""

    name: str
    description: str = ""
    choices: tuple[str, ...] = ()  # Static choices (e.g., file extensions)
    file_completion: bool = False  # Enable file completion for this arg


@dataclass(frozen=True)
class CommandFlag:
    """A flag/option for completion."""

    long: str  # e.g., "--output"
    short: str | None = None  # e.g., "-o"
    description: str = ""
    takes_value: bool = False
    choices: tuple[str, ...] = ()  # Static completions for the value


@dataclass(frozen=True)
class Subcommand:
    """A subcommand with its own flags and args."""

    name: str
    description: str = ""
    flags: tuple[CommandFlag, ...] = ()
    args: tuple[CommandArg, ...] = ()
    subcommands: tuple[Subcommand, ...] = ()  # Nested subcommands


@dataclass(frozen=True)
class CompletionSpec:
    """Full specification for generating shell completions."""

    command: str  # Top-level command name (e.g., "apxm")
    description: str = ""
    flags: tuple[CommandFlag, ...] = ()  # Global flags
    subcommands: tuple[Subcommand, ...] = ()


class CompletionGenerator:
    """Generate tab-completion scripts from a command specification.

    Supports bash, zsh, fish, and PowerShell.
    """

    def generate(self, spec: CompletionSpec, shell: ShellKind) -> str:
        """Generate completion script.

        Args:
            spec: Command structure specification.
            shell: Target shell.

        Returns:
            Completion script text.
        """
        generators = {
            ShellKind.BASH: self._gen_bash,
            ShellKind.ZSH: self._gen_zsh,
            ShellKind.FISH: self._gen_fish,
            ShellKind.POWERSHELL: self._gen_powershell,
            ShellKind.PWSH: self._gen_powershell,
        }

        generator = generators.get(shell)
        if generator is None:
            return f"# Completions not supported for {shell.value}\n"

        return generator(spec)

    def _gen_bash(self, spec: CompletionSpec) -> str:
        """Generate bash completion script."""
        cmd = spec.command
        func = f"__{cmd}_completions"

        lines = [
            f"# Bash completion for {cmd}",
            f"# Source this file or add to ~/.bash_completion.d/",
            f"",
            f"{func}() {{",
            f'    local cur prev words cword',
            f'    _init_completion || return',
            f'',
        ]

        # Build subcommand list
        subcmd_names = [s.name for s in spec.subcommands]
        global_flags = " ".join(f.long for f in spec.flags)
        if spec.flags:
            global_flags += " " + " ".join(f.short for f in spec.flags if f.short)

        lines.append(f'    local subcommands="{" ".join(subcmd_names)}"')
        lines.append(f'    local global_flags="{global_flags}"')
        lines.append("")

        # Determine which subcommand is active
        lines.append("    # Find active subcommand")
        lines.append("    local subcmd=''")
        lines.append("    for ((i=1; i < cword; i++)); do")
        lines.append("        case ${words[i]} in")
        for sc in spec.subcommands:
            lines.append(f"            {sc.name}) subcmd={sc.name}; break;;")
        lines.append("        esac")
        lines.append("    done")
        lines.append("")

        # Complete subcommands at top level
        lines.append('    if [ -z "$subcmd" ]; then')
        lines.append(f'        COMPREPLY=($(compgen -W "$subcommands $global_flags" -- "$cur"))')
        lines.append("        return")
        lines.append("    fi")
        lines.append("")

        # Per-subcommand completions
        lines.append("    case $subcmd in")
        for sc in spec.subcommands:
            flag_words = " ".join(f.long for f in sc.flags)
            if sc.flags:
                flag_words += " " + " ".join(f.short for f in sc.flags if f.short)
            nested = " ".join(ns.name for ns in sc.subcommands)
            all_words = f"{flag_words} {nested}".strip()
            lines.append(f"        {sc.name})")
            lines.append(f'            COMPREPLY=($(compgen -W "{all_words}" -- "$cur"))')
            lines.append("            ;;")
        lines.append("    esac")

        lines.append("}")
        lines.append(f"complete -F {func} {cmd}")
        lines.append("")

        return "\n".join(lines)

    def _gen_zsh(self, spec: CompletionSpec) -> str:
        """Generate zsh completion script."""
        cmd = spec.command
        lines = [
            f"#compdef {cmd}",
            f"# Zsh completion for {cmd}",
            f"# Place in $fpath as _{cmd}",
            f"",
            f"_{cmd}() {{",
            f"    local -a commands",
        ]

        # Subcommands
        lines.append("    commands=(")
        for sc in spec.subcommands:
            desc = sc.description.replace("'", "'\\''")
            lines.append(f"        '{sc.name}:{desc}'")
        lines.append("    )")
        lines.append("")

        lines.append("    _arguments -C \\")
        for fl in spec.flags:
            desc = fl.description.replace("'", "'\\''")
            if fl.short:
                lines.append(f"        '({fl.short} {fl.long}){fl.long}[{desc}]' \\")
            else:
                lines.append(f"        '{fl.long}[{desc}]' \\")
        lines.append("        '1:command:->cmd' \\")
        lines.append("        '*::arg:->args'")
        lines.append("")

        lines.append("    case $state in")
        lines.append("        cmd)")
        lines.append("            _describe 'command' commands")
        lines.append("            ;;")
        lines.append("        args)")
        lines.append("            case $words[1] in")
        for sc in spec.subcommands:
            lines.append(f"                {sc.name})")
            if sc.flags:
                lines.append("                    _arguments \\")
                for fl in sc.flags:
                    desc = fl.description.replace("'", "'\\''")
                    val_spec = ":value:" if fl.takes_value else ""
                    if fl.choices:
                        choices = " ".join(fl.choices)
                        val_spec = f":value:({choices})"
                    lines.append(f"                        '{fl.long}[{desc}]{val_spec}' \\")
                # File completion for args
                has_file_arg = any(a.file_completion for a in sc.args)
                if has_file_arg:
                    lines.append("                        '*:file:_files'")
                else:
                    lines[-1] = lines[-1].rstrip(" \\")
            elif any(a.file_completion for a in sc.args):
                lines.append("                    _files")
            lines.append("                    ;;")
        lines.append("            esac")
        lines.append("            ;;")
        lines.append("    esac")
        lines.append("}")
        lines.append(f"_{cmd}")
        lines.append("")

        return "\n".join(lines)

    def _gen_fish(self, spec: CompletionSpec) -> str:
        """Generate fish completion script."""
        cmd = spec.command
        lines = [
            f"# Fish completion for {cmd}",
            f"# Place in ~/.config/fish/completions/{cmd}.fish",
            f"",
        ]

        # Disable file completion by default
        lines.append(f"complete -c {cmd} -f")
        lines.append("")

        # Global flags
        for fl in spec.flags:
            parts = [f"complete -c {cmd}"]
            if fl.short:
                parts.append(f"-s {fl.short.lstrip('-')}")
            parts.append(f"-l {fl.long.lstrip('-')}")
            if fl.description:
                parts.append(f"-d '{fl.description}'")
            lines.append(" ".join(parts))

        # Subcommands
        subcmd_names = [s.name for s in spec.subcommands]
        no_subcmd = f"not __fish_seen_subcommand_from {' '.join(subcmd_names)}"

        for sc in spec.subcommands:
            lines.append(f"complete -c {cmd} -n '{no_subcmd}' -a '{sc.name}' -d '{sc.description}'")

        lines.append("")

        # Per-subcommand flags
        for sc in spec.subcommands:
            for fl in sc.flags:
                parts = [f"complete -c {cmd}"]
                parts.append(f"-n '__fish_seen_subcommand_from {sc.name}'")
                if fl.short:
                    parts.append(f"-s {fl.short.lstrip('-')}")
                parts.append(f"-l {fl.long.lstrip('-')}")
                if fl.description:
                    parts.append(f"-d '{fl.description}'")
                if fl.takes_value and not fl.choices:
                    parts.append("-r")  # requires argument
                if fl.choices:
                    parts.append(f"-a '{' '.join(fl.choices)}'")
                lines.append(" ".join(parts))

            # File completion for args
            for arg in sc.args:
                if arg.file_completion:
                    lines.append(f"complete -c {cmd} -n '__fish_seen_subcommand_from {sc.name}' -F")
                elif arg.choices:
                    lines.append(f"complete -c {cmd} -n '__fish_seen_subcommand_from {sc.name}' -a '{' '.join(arg.choices)}'")

        lines.append("")
        return "\n".join(lines)

    def _gen_powershell(self, spec: CompletionSpec) -> str:
        """Generate PowerShell completion script."""
        cmd = spec.command
        lines = [
            f"# PowerShell completion for {cmd}",
            f"",
            f"Register-ArgumentCompleter -CommandName {cmd} -ScriptBlock {{",
            f"    param($commandName, $wordToComplete, $cursorPosition)",
            f"    $subcommands = @(",
        ]

        for sc in spec.subcommands:
            desc = sc.description.replace("'", "''")
            lines.append(f"        @{{ Name = '{sc.name}'; Description = '{desc}' }}")
        lines.append("    )")
        lines.append("")

        lines.append("    $words = $wordToComplete -split '\\s+'")
        lines.append("    $current = $words[-1]")
        lines.append("")
        lines.append("    # Complete subcommands")
        lines.append("    $subcommands | Where-Object { $_.Name -like \"$current*\" } | ForEach-Object {")
        lines.append("        [System.Management.Automation.CompletionResult]::new($_.Name, $_.Name, 'ParameterValue', $_.Description)")
        lines.append("    }")
        lines.append("}")
        lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt integration
# ---------------------------------------------------------------------------

class PromptHelper:
    """Generate shell prompt integration snippets.

    Provides status indicators for shell prompts -- e.g., showing the active
    conda env, project name, or tool status.
    """

    def status_snippet(
        self,
        shell: ShellKind,
        env_var: str = "SNIFF_STATUS",
        format_str: str = "[{value}]",
    ) -> str:
        """Generate a prompt snippet that displays an env var if set.

        Args:
            shell: Target shell.
            env_var: Environment variable to display.
            format_str: Format template. {value} is replaced by the var value.

        Returns:
            Shell code snippet to embed in PS1/prompt.
        """
        if shell in (ShellKind.BASH, ShellKind.SH, ShellKind.DASH, ShellKind.KSH):
            inner = format_str.replace("{value}", f"${env_var}")
            return f'${{${env_var}:+{inner}}}'

        if shell == ShellKind.ZSH:
            inner = format_str.replace("{value}", f"${env_var}")
            return f'${{${env_var}:+{inner}}}'

        if shell == ShellKind.FISH:
            # Fish uses functions for prompt
            inner = format_str.replace("{value}", "$" + env_var)
            return (
                f"if set -q {env_var}\n"
                f'    echo -n "{inner} "\n'
                f"end"
            )

        if shell == ShellKind.TCSH:
            return f'%{{$?{env_var} && echo "{format_str.replace("{value}", "$" + env_var)}" %}}'

        if shell in (ShellKind.POWERSHELL, ShellKind.PWSH):
            inner = format_str.replace("{value}", f"$env:{env_var}")
            return f'if ($env:{env_var}) {{ Write-Host -NoNewline "{inner} " }}'

        return ""


# ---------------------------------------------------------------------------
# Alias suggestions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AliasSuggestion:
    """A suggested shell alias."""

    alias: str
    command: str
    description: str


class AliasSuggestor:
    """Suggest helpful shell aliases for a CLI tool."""

    def suggest(
        self,
        command: str,
        subcommands: Sequence[str] = (),
        common_flags: dict[str, str] | None = None,
    ) -> list[AliasSuggestion]:
        """Generate alias suggestions.

        Args:
            command: Base command (e.g., "apxm").
            subcommands: Known subcommands to create shortcuts for.
            common_flags: Map of alias_suffix -> flags (e.g., {"v": "--verbose"}).

        Returns:
            List of AliasSuggestion.
        """
        suggestions: list[AliasSuggestion] = []

        # Short alias for the base command
        if len(command) > 3:
            short = command[:2]
            suggestions.append(AliasSuggestion(
                alias=short,
                command=command,
                description=f"Short alias for {command}",
            ))

        # Subcommand aliases
        for sub in subcommands:
            alias = f"{command[0]}{sub[0]}"
            suggestions.append(AliasSuggestion(
                alias=alias,
                command=f"{command} {sub}",
                description=f"{command} {sub}",
            ))

        # Common flag combos
        if common_flags:
            for suffix, flags in common_flags.items():
                suggestions.append(AliasSuggestion(
                    alias=f"{command}{suffix}",
                    command=f"{command} {flags}",
                    description=f"{command} with {flags}",
                ))

        return suggestions

    def render(
        self,
        suggestions: Sequence[AliasSuggestion],
        shell: ShellKind,
    ) -> str:
        """Render alias suggestions as shell commands.

        Args:
            suggestions: Aliases to render.
            shell: Target shell.

        Returns:
            Shell script text defining the aliases.
        """
        lines: list[str] = ["# Suggested aliases"]

        for s in suggestions:
            lines.append(f"# {s.description}")
            if shell in (ShellKind.BASH, ShellKind.ZSH, ShellKind.SH, ShellKind.KSH, ShellKind.DASH):
                lines.append(f"alias {s.alias}='{s.command}'")
            elif shell == ShellKind.FISH:
                lines.append(f"alias {s.alias} '{s.command}'")
            elif shell == ShellKind.TCSH:
                lines.append(f"alias {s.alias} '{s.command}'")
            elif shell in (ShellKind.POWERSHELL, ShellKind.PWSH):
                lines.append(f"Set-Alias -Name {s.alias} -Value {{ {s.command} }}")

        lines.append("")
        return "\n".join(lines)
