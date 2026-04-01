"""Environment specification parser for .dekk.toml files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dekk._compat import tomllib, walk_up
from dekk.environment.types import EnvironmentKind, normalize_environment_type


@dataclass(frozen=True)
class RuntimeEnvironmentSpec:
    """Runtime environment specification."""

    type: str
    path: str
    file: str | None = None
    name: str | None = None

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


@dataclass(frozen=True)
class CommandSpec:
    """A project command that can be auto-converted to an agent skill."""

    run: str
    description: str = ""


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


@dataclass(frozen=True)
class InstallSpec:
    """Install pipeline specification parsed from ``[install]``."""

    build: str | None = None
    wrap: WrapSpec | None = None
    components: list[ComponentSpec] = field(default_factory=list)


@dataclass(frozen=True)
class AgentsSpec:
    """Configuration for agent config generation."""

    source: str = ".agents"
    targets: tuple[str, ...] = ("claude", "codex", "copilot", "cursor")


@dataclass
class EnvironmentSpec:
    """Environment specification from .dekk.toml."""

    project_name: str
    environment: RuntimeEnvironmentSpec | None = None
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    paths: dict[str, list[str]] = field(default_factory=dict)
    python: PythonSpec | None = None
    npm: NpmSpec | None = None
    commands: dict[str, CommandSpec] = field(default_factory=dict)
    agents: AgentsSpec | None = None
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

            environment = RuntimeEnvironmentSpec(
                type=normalize_environment_type(str(env_type)),
                path=str(env_path),
                file=str(env_data.get("file")) if env_data.get("file") else None,
                name=str(env_data.get("name")) if env_data.get("name") else None,
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
            if isinstance(cmd_spec, dict):
                commands[cmd_name] = CommandSpec(
                    run=cmd_spec.get("run", cmd_name),
                    description=cmd_spec.get("description", ""),
                )
            elif isinstance(cmd_spec, str):
                commands[cmd_name] = CommandSpec(run=cmd_spec)

        agents = None
        if agents_data := data.get("agents"):
            targets = agents_data.get("targets", ["claude", "codex", "copilot", "cursor"])
            agents = AgentsSpec(
                source=agents_data.get("source", ".agents"),
                targets=tuple(targets),
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
                    )
                )
            install = InstallSpec(
                build=install_data.get("build"),
                wrap=wrap,
                components=components,
            )

        return cls(
            project_name=project["name"],
            environment=environment,
            tools=tools,
            env_vars=env_vars or {},
            paths=paths,
            python=python,
            npm=npm,
            commands=commands,
            agents=agents,
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
            result[key] = os.pathsep.join(expanded)

        return result


def find_envspec(start_dir: Path | None = None) -> Path | None:
    """Find .dekk.toml by walking up the directory tree."""
    return walk_up(Path(start_dir or Path.cwd()), ".dekk.toml")


__all__ = [
    "AgentsSpec",
    "CommandSpec",
    "ComponentSpec",
    "EnvironmentSpec",
    "InstallSpec",
    "NpmSpec",
    "PythonSpec",
    "RuntimeEnvironmentSpec",
    "ToolSpec",
    "WrapSpec",
    "find_envspec",
]
