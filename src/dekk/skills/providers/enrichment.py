"""Shared enrichment detection and MCP stub generation.

Analyzes ``.dekk.toml`` metadata (commands, tools, env) to produce
project-agnostic enrichment data consumed by all provider implementations.
"""

from __future__ import annotations

import textwrap
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dekk.environment.spec import CommandSpec, EnvironmentSpec

# Known formatters and their file-glob associations.
KNOWN_FORMATTERS: dict[str, str] = {
    "clang-format": "**/*.cpp|**/*.h|**/*.td|**/*.cc|**/*.hpp",
    "prettier": "**/*.js|**/*.ts|**/*.jsx|**/*.tsx|**/*.css|**/*.json",
    "black": "**/*.py",
    "ruff": "**/*.py",
    "rustfmt": "**/*.rs",
    "gofmt": "**/*.go",
}

# Raw build tools that should be blocked when a CLI wrapper exists.
RAW_BUILD_TOOLS: frozenset[str] = frozenset({
    "make", "ninja", "cmake", "cargo", "gradle", "mvn",
})


# -----------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------

@dataclass(frozen=True)
class McpToolDef:
    """A tool definition derived from a ``[commands]`` entry with ``skill=true``."""

    name: str
    command_name: str
    description: str
    run: str


@dataclass(frozen=True)
class HookDef:
    """A detected hook from ``[tools]``/``[commands]`` analysis."""

    event: str
    matcher: dict[str, str]
    command: str
    description: str


@dataclass(frozen=True)
class EnrichmentData:
    """Computed once from ``.dekk.toml``, consumed by all providers."""

    project_name: str
    project_description: str
    version: str
    cli_name: str | None
    env_vars: dict[str, str] = field(default_factory=dict)
    mcp_tools: list[McpToolDef] = field(default_factory=list)
    hooks: list[HookDef] = field(default_factory=list)
    blocked_commands: list[str] = field(default_factory=list)
    has_doctor: bool = False
    has_formatter: bool = False
    formatter_name: str = ""
    formatter_extensions: str = ""


# -----------------------------------------------------------------------
# Detection helpers
# -----------------------------------------------------------------------

def _flatten_commands(
    commands: dict[str, CommandSpec],
    prefix: str = "",
) -> list[tuple[str, CommandSpec]]:
    """Flatten nested command groups into ``(dotted_name, spec)`` pairs."""
    result: list[tuple[str, CommandSpec]] = []
    for name, spec in commands.items():
        full = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"
        result.append((full, spec))
        if spec.is_group:
            result.extend(_flatten_commands(spec.commands, full))
    return result


def detect_mcp_tools(
    commands: dict[str, CommandSpec],
    project_name: str,
) -> list[McpToolDef]:
    """Extract MCP tool definitions from ``[commands]`` entries with ``skill=true``."""
    tools: list[McpToolDef] = []
    for name, spec in _flatten_commands(commands):
        if not spec.skill or not spec.run:
            continue
        tool_name = f"{project_name}_{name.replace('.', '_').replace('-', '_')}"
        tools.append(McpToolDef(
            name=tool_name,
            command_name=name,
            description=spec.description or f"Run {name}",
            run=spec.run,
        ))
    return tools


def detect_formatter(
    tools: Mapping[str, Any],
) -> tuple[str, str]:
    """Return ``(formatter_name, extensions)`` for the first known formatter found."""
    for fmt_name, extensions in KNOWN_FORMATTERS.items():
        if fmt_name in tools:
            return fmt_name, extensions
    return "", ""


def detect_blocked_commands(
    tools: Mapping[str, Any],
    commands: dict[str, CommandSpec],
    cli_name: str | None,
) -> list[str]:
    """Detect raw build tools that should be blocked when a CLI wrapper exists."""
    if not cli_name and "build" not in commands:
        return []
    return [name for name in tools if name in RAW_BUILD_TOOLS]


def detect_hooks(
    tools: Mapping[str, Any],
    commands: dict[str, CommandSpec],
    cli_name: str | None,
) -> list[HookDef]:
    """Auto-detect hooks from tools and commands analysis."""
    hooks: list[HookDef] = []

    # Formatter hook: auto-format on file write/edit
    fmt_name, fmt_extensions = detect_formatter(tools)
    if fmt_name:
        for pattern in fmt_extensions.split("|"):
            hooks.append(HookDef(
                event="PostToolUse",
                matcher={"tool_name": "Write|Edit", "file_pattern": pattern},
                command=f"{fmt_name} -i $FILE_PATH",
                description=f"Auto-format with {fmt_name}",
            ))

    # Doctor hook: validate environment on session start
    if "doctor" in commands:
        cmd_spec = commands["doctor"]
        doctor_cmd = cmd_spec.run
        if cli_name:
            doctor_cmd = f"{cli_name} doctor"
        hooks.append(HookDef(
            event="SessionStart",
            matcher={},
            command=doctor_cmd,
            description="Validate environment on session start",
        ))

    # Block raw build tools
    blocked = detect_blocked_commands(tools, commands, cli_name)
    for tool_name in blocked:
        hooks.append(HookDef(
            event="PreToolUse",
            matcher={"tool_name": "Bash", "command_pattern": f"^{tool_name}\\b"},
            command=f'echo "Use {cli_name or "dekk"} instead of {tool_name}" && exit 1',
            description=f"Block raw {tool_name} usage",
        ))

    return hooks


# -----------------------------------------------------------------------
# MCP server stub generation
# -----------------------------------------------------------------------

def generate_mcp_server_stub(project_name: str, mcp_tools: list[McpToolDef]) -> str:
    """Generate a platform-agnostic Python MCP server wrapping project commands."""
    safe_name = project_name.replace("-", "_")

    tool_defs = []
    for tool in mcp_tools:
        tool_defs.append(textwrap.dedent(f"""\

    @server.tool()
    async def {tool.name}(args: str = "") -> str:
        \"\"\"{tool.description}\"\"\"
        cmd = f"{tool.run} {{args}}"
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return json.dumps({{
            "exit_code": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }})
"""))

    tools_block = "".join(tool_defs) if tool_defs else ""

    return textwrap.dedent(f"""\
#!/usr/bin/env python3
\"\"\"MCP server for {project_name} — auto-generated by dekk.

Wraps project commands as MCP tools for AI coding assistants.
Regenerate with: dekk {project_name} agents generate
\"\"\"

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

server = FastMCP("{safe_name}")
{tools_block}
if __name__ == "__main__":
    server.run()
""")


def generate_mcp_requirements() -> str:
    """Return the contents of a ``requirements.txt`` for the MCP server."""
    return "mcp>=1.0.0\n"


# -----------------------------------------------------------------------
# Master computation
# -----------------------------------------------------------------------

def compute_enrichment(
    env_spec: EnvironmentSpec,
    cli_name: str | None = None,
) -> EnrichmentData:
    """Compute all enrichment data from an ``EnvironmentSpec``."""
    mcp_tools = detect_mcp_tools(env_spec.commands, env_spec.project_name)
    fmt_name, fmt_extensions = detect_formatter(env_spec.tools)
    hooks = detect_hooks(env_spec.tools, env_spec.commands, cli_name)
    blocked = detect_blocked_commands(env_spec.tools, env_spec.commands, cli_name)

    return EnrichmentData(
        project_name=env_spec.project_name,
        project_description=env_spec.project_description,
        version=env_spec.skills.version if env_spec.skills else "0.1.0",
        cli_name=cli_name,
        env_vars=dict(env_spec.env_vars),
        mcp_tools=mcp_tools,
        hooks=hooks,
        blocked_commands=blocked,
        has_doctor="doctor" in env_spec.commands,
        has_formatter=bool(fmt_name),
        formatter_name=fmt_name,
        formatter_extensions=fmt_extensions,
    )


__all__ = [
    "EnrichmentData",
    "HookDef",
    "KNOWN_FORMATTERS",
    "McpToolDef",
    "compute_enrichment",
    "detect_blocked_commands",
    "detect_formatter",
    "detect_hooks",
    "detect_mcp_tools",
    "generate_mcp_requirements",
    "generate_mcp_server_stub",
]
