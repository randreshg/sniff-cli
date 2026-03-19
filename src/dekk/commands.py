"""Command/plugin registry for project CLI tooling.

Passive command registry that allows projects to:
- Register commands with rich metadata (name, group, help, dependencies)
- Discover available commands dynamically
- Declare prerequisites and lifecycle hooks
- Generate help/documentation

Following dekk's detection-only philosophy: the registry stores and queries
command metadata. It never executes commands -- that's the caller's job.

Zero dependencies. Pure Python 3.10+.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence, runtime_checkable


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class CommandStatus(enum.Enum):
    """Lifecycle status of a registered command."""

    AVAILABLE = "available"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class CommandMeta:
    """Metadata for a registered command.

    Immutable descriptor -- holds everything a CLI framework needs to
    wire up a command without importing the implementation module.
    """

    name: str
    group: str = ""
    help: str = ""
    hidden: bool = False
    status: CommandStatus = CommandStatus.AVAILABLE

    # Dependencies: names of other commands that must exist (not run) first.
    requires: tuple[str, ...] = ()

    # Lifecycle callables (optional).  The registry stores them but never
    # calls them -- the host CLI is responsible for invocation order.
    setup: Callable[..., Any] | None = None
    execute: Callable[..., Any] | None = None
    teardown: Callable[..., Any] | None = None

    # Arbitrary key-value metadata for extensions.
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """Group-qualified name (e.g., 'build:compiler')."""
        if self.group:
            return f"{self.group}:{self.name}"
        return self.name

    @property
    def is_available(self) -> bool:
        return self.status is CommandStatus.AVAILABLE

    @property
    def has_lifecycle(self) -> bool:
        return any((self.setup, self.execute, self.teardown))


# ---------------------------------------------------------------------------
# Protocol -- optional, for type-safe command providers
# ---------------------------------------------------------------------------


@runtime_checkable
class CommandProvider(Protocol):
    """Protocol for objects that supply commands to a registry.

    Implement this to create a self-contained plugin that can register
    its own commands.  Alternatively, just call ``registry.register()``
    directly with ``CommandMeta`` instances.
    """

    def commands(self) -> Sequence[CommandMeta]:
        """Return the commands this provider offers."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class CommandRegistry:
    """Passive command registry.

    Stores ``CommandMeta`` descriptors and exposes query/discovery helpers.
    Never executes anything -- the caller owns the lifecycle.

    Thread-safety: not thread-safe.  Designed for single-threaded startup
    registration followed by concurrent read-only queries.
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandMeta] = {}

    # -- Registration -------------------------------------------------------

    def register(self, meta: CommandMeta) -> None:
        """Register a command.

        Raises:
            ValueError: If a command with the same qualified name already exists.
        """
        qn = meta.qualified_name
        if qn in self._commands:
            raise ValueError(f"Command already registered: {qn!r}")
        self._commands[qn] = meta

    def register_all(self, metas: Sequence[CommandMeta]) -> None:
        """Register multiple commands."""
        for m in metas:
            self.register(m)

    def register_provider(self, provider: CommandProvider) -> None:
        """Register all commands from a provider.

        Raises:
            TypeError: If *provider* does not satisfy ``CommandProvider``.
        """
        if not isinstance(provider, CommandProvider):
            raise TypeError(f"{provider} does not satisfy CommandProvider protocol")
        self.register_all(provider.commands())

    def unregister(self, qualified_name: str) -> CommandMeta | None:
        """Remove a command. Returns the removed meta, or None."""
        return self._commands.pop(qualified_name, None)

    # -- Queries ------------------------------------------------------------

    def get(self, qualified_name: str) -> CommandMeta | None:
        """Look up a command by qualified name."""
        return self._commands.get(qualified_name)

    def __contains__(self, qualified_name: str) -> bool:
        return qualified_name in self._commands

    def __len__(self) -> int:
        return len(self._commands)

    def __iter__(self):
        return iter(self._commands.values())

    @property
    def names(self) -> list[str]:
        """All qualified command names, sorted."""
        return sorted(self._commands)

    def all(self, *, include_hidden: bool = False) -> list[CommandMeta]:
        """All commands, optionally filtering hidden ones."""
        cmds = list(self._commands.values())
        if not include_hidden:
            cmds = [c for c in cmds if not c.hidden]
        return sorted(cmds, key=lambda c: c.qualified_name)

    def by_group(self, group: str) -> list[CommandMeta]:
        """Commands in a specific group, sorted by name."""
        return sorted(
            (c for c in self._commands.values() if c.group == group),
            key=lambda c: c.name,
        )

    def groups(self) -> list[str]:
        """Distinct group names, sorted. Empty string = ungrouped."""
        return sorted({c.group for c in self._commands.values()})

    def by_status(self, status: CommandStatus) -> list[CommandMeta]:
        """Commands with a given status."""
        return [c for c in self._commands.values() if c.status is status]

    def by_tag(self, key: str, value: str | None = None) -> list[CommandMeta]:
        """Commands that have a specific tag (optionally matching a value)."""
        results = []
        for c in self._commands.values():
            if key in c.tags:
                if value is None or c.tags[key] == value:
                    results.append(c)
        return sorted(results, key=lambda c: c.qualified_name)

    # -- Dependency queries -------------------------------------------------

    def missing_requirements(self, qualified_name: str) -> list[str]:
        """Return unresolved requirement names for a command.

        Returns an empty list if all requirements are registered, or if the
        command itself is not found.
        """
        meta = self.get(qualified_name)
        if meta is None:
            return []
        return [r for r in meta.requires if r not in self._commands]

    def dependents(self, qualified_name: str) -> list[CommandMeta]:
        """Commands that list *qualified_name* in their ``requires``."""
        return [
            c for c in self._commands.values()
            if qualified_name in c.requires
        ]

    def resolve_order(self, qualified_name: str) -> list[str] | None:
        """Topological order to satisfy all transitive requirements.

        Returns ``None`` if a cycle is detected or the command is not found.
        The returned list ends with *qualified_name* itself.
        """
        if qualified_name not in self._commands:
            return None

        visited: set[str] = set()
        in_stack: set[str] = set()
        order: list[str] = []

        def _visit(name: str) -> bool:
            if name in in_stack:
                return False
            if name in visited:
                return True
            in_stack.add(name)
            meta = self._commands.get(name)
            if meta:
                for dep in meta.requires:
                    if not _visit(dep):
                        return False
            in_stack.discard(name)
            visited.add(name)
            order.append(name)
            return True

        if not _visit(qualified_name):
            return None
        return order

    # -- Help / Documentation -----------------------------------------------

    def help_text(self, qualified_name: str) -> str | None:
        """Return formatted help for a single command, or None."""
        meta = self.get(qualified_name)
        if meta is None:
            return None
        lines = [meta.qualified_name]
        if meta.help:
            lines.append(f"  {meta.help}")
        if meta.status is not CommandStatus.AVAILABLE:
            lines.append(f"  Status: {meta.status.value}")
        if meta.requires:
            lines.append(f"  Requires: {', '.join(meta.requires)}")
        if meta.tags:
            tag_str = ", ".join(f"{k}={v}" for k, v in sorted(meta.tags.items()))
            lines.append(f"  Tags: {tag_str}")
        return "\n".join(lines)

    def help_summary(self, *, include_hidden: bool = False) -> str:
        """Formatted summary of all commands, grouped."""
        sections: list[str] = []
        for group in self.groups():
            cmds = self.by_group(group)
            if not include_hidden:
                cmds = [c for c in cmds if not c.hidden]
            if not cmds:
                continue
            header = group if group else "(ungrouped)"
            lines = [f"{header}:"]
            for c in cmds:
                status_suffix = ""
                if c.status is CommandStatus.DEPRECATED:
                    status_suffix = " [deprecated]"
                elif c.status is CommandStatus.DISABLED:
                    status_suffix = " [disabled]"
                help_text = f" - {c.help}" if c.help else ""
                lines.append(f"  {c.name}{help_text}{status_suffix}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Decorator -- convenience for registering functions as commands
# ---------------------------------------------------------------------------


def command(
    registry: CommandRegistry,
    name: str | None = None,
    *,
    group: str = "",
    help: str = "",
    requires: Sequence[str] = (),
    hidden: bool = False,
    tags: dict[str, str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that registers a function as a command.

    The decorated function becomes the ``execute`` callable on the
    ``CommandMeta``.  The function itself is returned unchanged.

    Usage::

        registry = CommandRegistry()

        @command(registry, group="build", help="Compile the project")
        def compile(release: bool = True):
            ...

    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        cmd_name = name or fn.__name__
        meta = CommandMeta(
            name=cmd_name,
            group=group,
            help=help or fn.__doc__ or "",
            requires=tuple(requires),
            hidden=hidden,
            execute=fn,
            tags=tags or {},
        )
        registry.register(meta)
        return fn

    return decorator
