"""Environment specification parser for .dekk.toml files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from dekk._compat import tomllib, walk_up
from dekk.environment.types import EnvironmentKind, normalize_environment_type

# Env vars that should be prepended (not overwritten) during activation.
PREPEND_ENV_VARS: Final[frozenset[str]] = frozenset({
    "PATH",
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "PYTHONPATH",
    "PKG_CONFIG_PATH",
})

# Maps [paths] shorthand keys to their standard env var names.
PATHS_KEY_MAP: Final[dict[str, str]] = {
    "bin": "PATH",
    "lib": "LD_LIBRARY_PATH",
    "pkg_config": "PKG_CONFIG_PATH",
    "python": "PYTHONPATH",
}


@dataclass(frozen=True)
class RuntimeEnvironmentSpec:
    """Runtime environment specification."""

    type: str
    path: str
    file: str | None = None
    name: str | None = None
    channels: list[str] = field(default_factory=lambda: ["conda-forge"])
    packages: dict[str, str] = field(default_factory=dict)
    pip: dict[str, str] = field(default_factory=dict)

    @property
    def kind(self) -> EnvironmentKind | None:
        """Known provider kind, if the configured type matches one."""
        return EnvironmentKind.from_value(self.type)


@dataclass(frozen=True)
class NpmSpec:
    """Npm package dependencies (installed globally in conda env)."""

    packages: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    """Tool dependency specification."""

    command: str
    version: str | None = None
    optional: bool = False


@dataclass(frozen=True)
class PythonSpec:
    """Python environment specification."""

    pyproject: str | None = None
    script: str | None = None


RESERVED_COMMAND_KEYS: Final[frozenset[str]] = frozenset({
    "run", "description", "skill", "group",
})


@dataclass(frozen=True)
class CommandSpec:
    """A project command or command group.

    Leaf commands have a non-empty ``run`` field.  Group commands have
    children in ``commands`` and may optionally have a ``run`` for the
    bare group invocation (e.g., ``dekk app llm`` shows help).
    """

    run: str = ""
    description: str = ""
    skill: bool = False
    group: str = ""
    commands: dict[str, CommandSpec] = field(default_factory=dict)

    @property
    def is_group(self) -> bool:
        return bool(self.commands)


@dataclass(frozen=True)
class WrapSpec:
    """Wrapper install specification."""

    name: str
    target: str


@dataclass(frozen=True)
class ComponentSpec:
    """An optional install component shown during interactive selection."""

    name: str
    label: str
    description: str
    run: str  # shell command to execute
    default: bool = True  # pre-selected in interactive mode
    requires: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InstallSpec:
    """Install pipeline specification parsed from ``[install]``."""

    build: str | None = None
    wrap: WrapSpec | None = None
    components: list[ComponentSpec] = field(default_factory=list)


@dataclass(frozen=True)
class SkillsSpec:
    """Configuration for skill / agent config generation."""

    source: str = ".agents"
    targets: tuple[str, ...] = ("claude", "codex", "copilot", "cursor")
    enrich: bool = False
    version: str = "0.1.0"


def _parse_command(name: str, data: Any) -> CommandSpec:
    """Parse a single command entry from TOML.

    Handles three forms:
      - String shorthand: ``build = "make"``
      - Dict with metadata: ``build = { run = "make", description = "..." }``
      - Group with children: ``[commands.llm]`` containing sub-tables
    """
    if isinstance(data, str):
        return CommandSpec(run=data)

    if not isinstance(data, dict):
        from dekk.cli.errors import ValidationError

        raise ValidationError(
            f"Command '{name}' must be a string or table, got {type(data).__name__}"
        )

    run = data.get("run", "")
    description = data.get("description", "")
    skill = data.get("skill", False)
    group = data.get("group", "")

    # Discover child commands: any key that is not a reserved metadata key
    # and whose value is a string or dict (i.e., a sub-command).
    children: dict[str, CommandSpec] = {}
    for key, value in data.items():
        if key in RESERVED_COMMAND_KEYS:
            continue
        if isinstance(value, (str, dict)):
            children[key] = _parse_command(key, value)

    # Validation: leaf command (no children) must have a run field.
    if not children and not run:
        from dekk.cli.errors import ValidationError

        raise ValidationError(
            f"Command '{name}' has no 'run' field and no subcommands",
            hint=f"Add 'run = \"...\"' to [commands.{name}] in .dekk.toml",
        )

    return CommandSpec(
        run=run,
        description=description,
        skill=skill,
        group=group,
        commands=children,
    )


@dataclass
class EnvironmentSpec:
    """Environment specification from .dekk.toml."""

    project_name: str
    project_description: str = ""
    environment: RuntimeEnvironmentSpec | None = None
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    paths: dict[str, list[str]] = field(default_factory=dict)
    python: PythonSpec | None = None
    npm: NpmSpec | None = None
    commands: dict[str, CommandSpec] = field(default_factory=dict)
    skills: SkillsSpec | None = None
    install: InstallSpec | None = None

    @classmethod
    def from_file(cls, path: Path) -> EnvironmentSpec:
        """Parse .dekk.toml file."""
        if not path.exists():
            from dekk.cli.errors import ConfigError

            raise ConfigError(
                f"Environment spec not found: {path}",
                hint="Run 'dekk init' to create a .dekk.toml file",
            )

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as err:
            from dekk.cli.errors import ConfigError

            raise ConfigError(f"Failed to parse {path}: {err}") from err

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> EnvironmentSpec:
        """Parse dict into EnvironmentSpec."""
        project = data.get("project", {})
        if not project.get("name"):
            from dekk.cli.errors import ValidationError

            raise ValidationError(
                "Missing project.name",
                hint='Add [project]\\nname = "myproject" to .dekk.toml',
            )

        if "conda" in data:
            from dekk.cli.errors import ValidationError

            raise ValidationError(
                "Legacy [conda] section is not supported",
                hint=(
                    "Replace [conda] with:\n\n"
                    "[environment]\n"
                    'type = "conda"\n'
                    'path = "{project}/.dekk/env"\n'
                    'file = "environment.yaml"\n'
                ),
            )

        environment = None
        if env_data := data.get("environment"):
            if not isinstance(env_data, dict):
                from dekk.cli.errors import ValidationError

                raise ValidationError("environment must be a dict")

            env_type = env_data.get("type")
            env_path = env_data.get("path")
            if not env_type or not env_path:
                from dekk.cli.errors import ValidationError

                raise ValidationError(
                    "environment.type and environment.path are required",
                    hint=(
                        "Add:\n\n"
                        "[environment]\n"
                        'type = "conda"\n'
                        'path = "{project}/.dekk/env"\n'
                    ),
                )

            env_file = str(env_data.get("file")) if env_data.get("file") else None
            env_packages = {str(k): str(v) for k, v in env_data.get("packages", {}).items()}
            if env_file and env_packages:
                from dekk.cli.errors import ValidationError

                raise ValidationError(
                    "Cannot use both environment.file and environment.packages — pick one"
                )

            channels = env_data.get("channels", ["conda-forge"])
            pip_pkgs = {str(k): str(v) for k, v in env_data.get("pip", {}).items()}

            environment = RuntimeEnvironmentSpec(
                type=normalize_environment_type(str(env_type)),
                path=str(env_path),
                file=env_file,
                name=str(env_data.get("name")) if env_data.get("name") else None,
                channels=[str(c) for c in channels],
                packages=env_packages,
                pip=pip_pkgs,
            )

        tools = {}
        for name, spec in data.get("tools", {}).items():
            if isinstance(spec, dict):
                tools[name] = ToolSpec(
                    command=spec.get("command", name),
                    version=spec.get("version"),
                    optional=spec.get("optional", False),
                )
            elif isinstance(spec, str):
                tools[name] = ToolSpec(command=spec)

        env_vars = data.get("env", {})
        if env_vars and not isinstance(env_vars, dict):
            from dekk.cli.errors import ValidationError

            raise ValidationError("env must be a dict")

        paths = {}
        for key, value in data.get("paths", {}).items():
            paths[key] = [value] if isinstance(value, str) else value

        python = None
        if python_data := data.get("python"):
            python = PythonSpec(
                pyproject=python_data.get("pyproject"),
                script=python_data.get("script"),
            )

        npm = None
        if npm_data := data.get("npm"):
            npm_packages = {}
            for pkg_name, pkg_version in npm_data.items():
                npm_packages[pkg_name] = str(pkg_version) if pkg_version else "latest"
            npm = NpmSpec(packages=npm_packages)

        commands = {}
        for cmd_name, cmd_spec in data.get("commands", {}).items():
            commands[cmd_name] = _parse_command(cmd_name, cmd_spec)

        skills = None
        if skills_data := (data.get("agents") or data.get("skills")):
            targets = skills_data.get("targets", ["claude", "codex", "copilot", "cursor"])
            skills = SkillsSpec(
                source=skills_data.get("source", ".agents"),
                targets=tuple(targets),
                enrich=skills_data.get("enrich", False),
                version=str(skills_data.get("version", "0.1.0")),
            )

        install = None
        if install_data := data.get("install"):
            wrap = None
            if wrap_data := install_data.get("wrap"):
                wrap = WrapSpec(name=wrap_data["name"], target=wrap_data["target"])
            components: list[ComponentSpec] = []
            for comp_data in install_data.get("components", []):
                components.append(
                    ComponentSpec(
                        name=comp_data["name"],
                        label=comp_data.get("label", comp_data["name"]),
                        description=comp_data.get("description", ""),
                        run=comp_data["run"],
                        default=comp_data.get("default", True),
                        requires=comp_data.get("requires", []),
                    )
                )
            install = InstallSpec(
                build=install_data.get("build"),
                wrap=wrap,
                components=components,
            )

        return cls(
            project_name=project["name"],
            project_description=project.get("description", ""),
            environment=environment,
            tools=tools,
            env_vars=env_vars or {},
            paths=paths,
            python=python,
            npm=npm,
            commands=commands,
            skills=skills,
            install=install,
        )

    def expand_placeholders(
        self, project_root: Path, environment_prefix: Path | None = None
    ) -> dict[str, str]:
        """Expand {project}, {environment}, {home} placeholders."""
        replacements = {
            "{project}": str(project_root),
            "{home}": str(Path.home()),
        }
        if environment_prefix:
            replacements["{environment}"] = str(environment_prefix)

        def expand(value: str) -> str:
            for placeholder, path in replacements.items():
                value = value.replace(placeholder, path)
            return value

        result = {}

        for key, value in self.env_vars.items():
            result[key] = expand(value)

        for key, path_list in self.paths.items():
            expanded = [expand(p) for p in path_list]
            env_key = PATHS_KEY_MAP.get(key, key)
            joined = os.pathsep.join(expanded)
            # Append to existing value if key already set (e.g. from [env])
            if env_key in result:
                result[env_key] = f"{result[env_key]}{os.pathsep}{joined}"
            else:
                result[env_key] = joined

        return result


def find_envspec(start_dir: Path | None = None) -> Path | None:
    """Find .dekk.toml by walking up the directory tree."""
    return walk_up(Path(start_dir or Path.cwd()), ".dekk.toml")


__all__ = [
    "CommandSpec",
    "ComponentSpec",
    "EnvironmentSpec",
    "InstallSpec",
    "PATHS_KEY_MAP",
    "PREPEND_ENV_VARS",
    "NpmSpec",
    "PythonSpec",
    "RESERVED_COMMAND_KEYS",
    "RuntimeEnvironmentSpec",
    "SkillsSpec",
    "ToolSpec",
    "WrapSpec",
    "find_envspec",
]
