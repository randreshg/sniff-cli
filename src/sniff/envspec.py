"""Environment specification parser for .sniff.toml files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sniff._compat import tomllib, walk_up


@dataclass(frozen=True)
class CondaSpec:
    """Conda environment specification."""

    name: str
    file: Optional[str] = None


@dataclass(frozen=True)
class ToolSpec:
    """Tool dependency specification."""

    command: str
    version: Optional[str] = None
    optional: bool = False


@dataclass(frozen=True)
class PythonSpec:
    """Python environment specification."""

    pyproject: Optional[str] = None
    script: Optional[str] = None


@dataclass
class EnvironmentSpec:
    """Environment specification from .sniff.toml."""

    project_name: str
    conda: Optional[CondaSpec] = None
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    paths: dict[str, list[str]] = field(default_factory=dict)
    python: Optional[PythonSpec] = None

    @classmethod
    def from_file(cls, path: Path) -> EnvironmentSpec:
        """Parse .sniff.toml file."""
        if not path.exists():
            # Lazy import to avoid triggering Rich import chain
            from sniff.cli.errors import ConfigError

            raise ConfigError(
                f"Environment spec not found: {path}",
                hint="Run 'sniff init' to create a .sniff.toml file",
            )

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            from sniff.cli.errors import ConfigError

            raise ConfigError(f"Failed to parse {path}: {e}")

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> EnvironmentSpec:
        """Parse dict into EnvironmentSpec."""
        # Project name is required
        project = data.get("project", {})
        if not project.get("name"):
            from sniff.cli.errors import ValidationError

            raise ValidationError(
                "Missing project.name",
                hint="Add [project]\\nname = \"myproject\" to .sniff.toml",
            )

        # Conda (optional)
        conda = None
        if conda_data := data.get("conda"):
            conda = CondaSpec(
                name=conda_data.get("name", project["name"]),
                file=conda_data.get("file"),
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
            from sniff.cli.errors import ValidationError

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

        return cls(
            project_name=project["name"],
            conda=conda,
            tools=tools,
            env_vars=env_vars or {},
            paths=paths,
            python=python,
        )

    def expand_placeholders(self, project_root: Path, conda_prefix: Optional[Path] = None) -> dict[str, str]:
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


def find_envspec(start_dir: Optional[Path] = None) -> Optional[Path]:
    """Find .sniff.toml by walking up the directory tree."""
    return walk_up(Path(start_dir or Path.cwd()), ".sniff.toml")
