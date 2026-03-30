"""Environment specification parser for .dekk.toml files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dekk._compat import tomllib, walk_up


@dataclass(frozen=True)
class CondaSpec:
    """Conda environment specification."""

    name: str
    file: str | None = None
    packages: tuple[str, ...] = ()
    channel: str = "conda-forge"


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
class AgentsSpec:
    """Configuration for agent config generation."""

    source: str = ".agents"
    targets: tuple[str, ...] = ("claude", "codex", "copilot", "cursor")


@dataclass
class EnvironmentSpec:
    """Environment specification from .dekk.toml."""

    project_name: str
    conda: CondaSpec | None = None
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    paths: dict[str, list[str]] = field(default_factory=dict)
    python: PythonSpec | None = None
    npm: NpmSpec | None = None
    commands: dict[str, CommandSpec] = field(default_factory=dict)
    agents: AgentsSpec | None = None

    @classmethod
    def from_file(cls, path: Path) -> EnvironmentSpec:
        """Parse .dekk.toml file."""
        if not path.exists():
            # Lazy import to avoid triggering Rich import chain
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
        # Project name is required
        project = data.get("project", {})
        if not project.get("name"):
            from dekk.cli.errors import ValidationError

            raise ValidationError(
                "Missing project.name",
                hint='Add [project]\\nname = "myproject" to .dekk.toml',
            )

        # Conda (optional)
        conda = None
        if conda_data := data.get("conda"):
            packages = conda_data.get("packages", [])
            if isinstance(packages, str):
                packages = [packages]
            conda = CondaSpec(
                name=conda_data.get("name", project["name"]),
                file=conda_data.get("file"),
                packages=tuple(packages),
                channel=conda_data.get("channel", "conda-forge"),
            )

        # Tools
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

        # Env vars (simple dict)
        env_vars = data.get("env", {})
        if env_vars and not isinstance(env_vars, dict):
            from dekk.cli.errors import ValidationError

            raise ValidationError("env must be a dict")

        # Paths (normalize to lists)
        paths = {}
        for key, value in data.get("paths", {}).items():
            paths[key] = [value] if isinstance(value, str) else value

        # Python environment (optional)
        python = None
        if python_data := data.get("python"):
            python = PythonSpec(
                pyproject=python_data.get("pyproject"),
                script=python_data.get("script"),
            )

        # Npm packages (optional)
        npm = None
        if npm_data := data.get("npm"):
            npm_packages = {}
            for pkg_name, pkg_version in npm_data.items():
                npm_packages[pkg_name] = str(pkg_version) if pkg_version else "latest"
            npm = NpmSpec(packages=npm_packages)

        # Commands (optional)
        commands = {}
        for cmd_name, cmd_spec in data.get("commands", {}).items():
            if isinstance(cmd_spec, dict):
                commands[cmd_name] = CommandSpec(
                    run=cmd_spec.get("run", cmd_name),
                    description=cmd_spec.get("description", ""),
                )
            elif isinstance(cmd_spec, str):
                commands[cmd_name] = CommandSpec(run=cmd_spec)

        # Agents config (optional)
        agents = None
        if agents_data := data.get("agents"):
            targets = agents_data.get("targets", ["claude", "codex", "copilot", "cursor"])
            agents = AgentsSpec(
                source=agents_data.get("source", ".agents"),
                targets=tuple(targets),
            )

        return cls(
            project_name=project["name"],
            conda=conda,
            tools=tools,
            env_vars=env_vars or {},
            paths=paths,
            python=python,
            npm=npm,
            commands=commands,
            agents=agents,
        )

    def expand_placeholders(
        self, project_root: Path, conda_prefix: Path | None = None
    ) -> dict[str, str]:
        """Expand {project}, {conda}, {home} placeholders."""
        replacements = {
            "{project}": str(project_root),
            "{home}": str(Path.home()),
        }
        if conda_prefix:
            replacements["{conda}"] = str(conda_prefix)

        def expand(value: str) -> str:
            for placeholder, path in replacements.items():
                value = value.replace(placeholder, path)
            return value

        result = {}

        # Expand env vars
        for key, value in self.env_vars.items():
            result[key] = expand(value)

        # Expand and join paths
        for key, path_list in self.paths.items():
            expanded = [expand(p) for p in path_list]
            result[key] = os.pathsep.join(expanded)

        return result


def find_envspec(start_dir: Path | None = None) -> Path | None:
    """Find .dekk.toml by walking up the directory tree."""
    return walk_up(Path(start_dir or Path.cwd()), ".dekk.toml")
