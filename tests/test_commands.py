"""Tests for the command registry."""

from dekk.core.commands import (
    CommandMeta,
    CommandProvider,
    CommandRegistry,
    CommandStatus,
    command,
)

# ---------------------------------------------------------------------------
# CommandMeta
# ---------------------------------------------------------------------------


class TestCommandMeta:
    def test_defaults(self):
        m = CommandMeta(name="build")
        assert m.name == "build"
        assert m.group == ""
        assert m.help == ""
        assert m.hidden is False
        assert m.status is CommandStatus.AVAILABLE
        assert m.requires == ()
        assert m.setup is None
        assert m.execute is None
        assert m.teardown is None
        assert m.tags == {}

    def test_qualified_name_no_group(self):
        m = CommandMeta(name="test")
        assert m.qualified_name == "test"

    def test_qualified_name_with_group(self):
        m = CommandMeta(name="compile", group="build")
        assert m.qualified_name == "build:compile"

    def test_is_available(self):
        assert CommandMeta(name="a").is_available is True
        assert CommandMeta(name="a", status=CommandStatus.DISABLED).is_available is False
        assert CommandMeta(name="a", status=CommandStatus.DEPRECATED).is_available is False

    def test_has_lifecycle(self):
        assert CommandMeta(name="a").has_lifecycle is False
        assert CommandMeta(name="a", execute=lambda: None).has_lifecycle is True
        assert CommandMeta(name="a", setup=lambda: None).has_lifecycle is True
        assert CommandMeta(name="a", teardown=lambda: None).has_lifecycle is True

    def test_frozen(self):
        m = CommandMeta(name="x")
        try:
            m.name = "y"  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# CommandRegistry -- registration
# ---------------------------------------------------------------------------


class TestRegistryRegistration:
    def test_register_and_get(self):
        reg = CommandRegistry()
        m = CommandMeta(name="build", help="Build stuff")
        reg.register(m)
        assert reg.get("build") is m
        assert "build" in reg
        assert len(reg) == 1

    def test_register_with_group(self):
        reg = CommandRegistry()
        m = CommandMeta(name="compile", group="build")
        reg.register(m)
        assert reg.get("build:compile") is m
        assert reg.get("compile") is None

    def test_duplicate_raises(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="test"))
        try:
            reg.register(CommandMeta(name="test"))
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "test" in str(e)

    def test_register_all(self):
        reg = CommandRegistry()
        reg.register_all(
            [
                CommandMeta(name="a"),
                CommandMeta(name="b"),
                CommandMeta(name="c"),
            ]
        )
        assert len(reg) == 3

    def test_unregister(self):
        reg = CommandRegistry()
        m = CommandMeta(name="old")
        reg.register(m)
        removed = reg.unregister("old")
        assert removed is m
        assert "old" not in reg
        assert len(reg) == 0

    def test_unregister_missing_returns_none(self):
        reg = CommandRegistry()
        assert reg.unregister("nope") is None


# ---------------------------------------------------------------------------
# CommandProvider protocol
# ---------------------------------------------------------------------------


class TestProvider:
    def test_register_provider(self):
        class MyPlugin:
            def commands(self):
                return [
                    CommandMeta(name="lint", group="check", help="Run linter"),
                    CommandMeta(name="fmt", group="check", help="Format code"),
                ]

        reg = CommandRegistry()
        reg.register_provider(MyPlugin())
        assert len(reg) == 2
        assert reg.get("check:lint") is not None
        assert reg.get("check:fmt") is not None

    def test_register_provider_bad_type(self):
        reg = CommandRegistry()
        try:
            reg.register_provider("not a provider")  # type: ignore[arg-type]
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass

    def test_provider_protocol_check(self):
        class Good:
            def commands(self):
                return []

        class Bad:
            pass

        assert isinstance(Good(), CommandProvider)
        assert not isinstance(Bad(), CommandProvider)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


class TestQueries:
    def _populated_registry(self) -> CommandRegistry:
        reg = CommandRegistry()
        reg.register_all(
            [
                CommandMeta(name="compile", group="build", help="Compile project"),
                CommandMeta(
                    name="link", group="build", help="Link objects", requires=("build:compile",)
                ),
                CommandMeta(name="unit", group="test", help="Unit tests"),
                CommandMeta(name="lint", group="test", help="Lint check", hidden=True),
                CommandMeta(name="doctor", help="Check env"),
                CommandMeta(
                    name="old-cmd",
                    status=CommandStatus.DEPRECATED,
                    help="Legacy",
                ),
                CommandMeta(
                    name="disabled-cmd",
                    status=CommandStatus.DISABLED,
                ),
            ]
        )
        return reg

    def test_names(self):
        reg = self._populated_registry()
        assert reg.names == sorted(
            [
                "build:compile",
                "build:link",
                "test:unit",
                "test:lint",
                "doctor",
                "old-cmd",
                "disabled-cmd",
            ]
        )

    def test_all_excludes_hidden_by_default(self):
        reg = self._populated_registry()
        visible = reg.all()
        names = [c.qualified_name for c in visible]
        assert "test:lint" not in names

    def test_all_include_hidden(self):
        reg = self._populated_registry()
        all_cmds = reg.all(include_hidden=True)
        names = [c.qualified_name for c in all_cmds]
        assert "test:lint" in names

    def test_by_group(self):
        reg = self._populated_registry()
        build_cmds = reg.by_group("build")
        assert [c.name for c in build_cmds] == ["compile", "link"]

    def test_groups(self):
        reg = self._populated_registry()
        groups = reg.groups()
        assert "" in groups
        assert "build" in groups
        assert "test" in groups

    def test_by_status(self):
        reg = self._populated_registry()
        deprecated = reg.by_status(CommandStatus.DEPRECATED)
        assert len(deprecated) == 1
        assert deprecated[0].name == "old-cmd"

    def test_by_tag(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="a", tags={"platform": "linux"}))
        reg.register(CommandMeta(name="b", tags={"platform": "darwin"}))
        reg.register(CommandMeta(name="c", tags={"experimental": "true"}))

        linux = reg.by_tag("platform", "linux")
        assert len(linux) == 1 and linux[0].name == "a"

        any_platform = reg.by_tag("platform")
        assert len(any_platform) == 2

        no_match = reg.by_tag("nonexistent")
        assert no_match == []

    def test_iter(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="x"))
        reg.register(CommandMeta(name="y"))
        names = [c.name for c in reg]
        assert sorted(names) == ["x", "y"]


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


class TestDependencies:
    def test_missing_requirements_none(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="a"))
        reg.register(CommandMeta(name="b", requires=("a",)))
        assert reg.missing_requirements("b") == []

    def test_missing_requirements_some(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="b", requires=("a", "c")))
        assert reg.missing_requirements("b") == ["a", "c"]

    def test_missing_requirements_unknown_command(self):
        reg = CommandRegistry()
        assert reg.missing_requirements("nope") == []

    def test_dependents(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="a"))
        reg.register(CommandMeta(name="b", requires=("a",)))
        reg.register(CommandMeta(name="c", requires=("a",)))
        reg.register(CommandMeta(name="d"))
        deps = reg.dependents("a")
        assert sorted(c.name for c in deps) == ["b", "c"]

    def test_resolve_order_simple(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="a"))
        reg.register(CommandMeta(name="b", requires=("a",)))
        reg.register(CommandMeta(name="c", requires=("b",)))
        order = reg.resolve_order("c")
        assert order == ["a", "b", "c"]

    def test_resolve_order_diamond(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="a"))
        reg.register(CommandMeta(name="b", requires=("a",)))
        reg.register(CommandMeta(name="c", requires=("a",)))
        reg.register(CommandMeta(name="d", requires=("b", "c")))
        order = reg.resolve_order("d")
        assert order is not None
        assert order[-1] == "d"
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")

    def test_resolve_order_cycle(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="a", requires=("b",)))
        reg.register(CommandMeta(name="b", requires=("a",)))
        assert reg.resolve_order("a") is None

    def test_resolve_order_not_found(self):
        reg = CommandRegistry()
        assert reg.resolve_order("missing") is None

    def test_resolve_order_missing_dep_still_works(self):
        """Unresolved deps are visited but don't crash -- they just have no deps themselves."""
        reg = CommandRegistry()
        reg.register(CommandMeta(name="b", requires=("a",)))
        order = reg.resolve_order("b")
        # "a" is not registered so it won't appear (no meta found), but "b" still resolves
        assert order is not None
        assert "b" in order


# ---------------------------------------------------------------------------
# Help / documentation
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_text_basic(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="build", help="Build the project"))
        text = reg.help_text("build")
        assert text is not None
        assert "build" in text
        assert "Build the project" in text

    def test_help_text_with_status(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="old", status=CommandStatus.DEPRECATED))
        text = reg.help_text("old")
        assert text is not None
        assert "deprecated" in text

    def test_help_text_with_requires(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="link", requires=("compile",)))
        text = reg.help_text("link")
        assert text is not None
        assert "compile" in text

    def test_help_text_with_tags(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="x", tags={"tier": "advanced"}))
        text = reg.help_text("x")
        assert text is not None
        assert "tier=advanced" in text

    def test_help_text_not_found(self):
        reg = CommandRegistry()
        assert reg.help_text("nope") is None

    def test_help_summary(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="compile", group="build", help="Compile"))
        reg.register(CommandMeta(name="test", help="Run tests"))
        summary = reg.help_summary()
        assert "build:" in summary
        assert "compile" in summary
        assert "(ungrouped):" in summary
        assert "test" in summary

    def test_help_summary_hides_hidden(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="visible", group="g", help="Shown"))
        reg.register(CommandMeta(name="secret", group="g", help="Hidden", hidden=True))
        summary = reg.help_summary()
        assert "visible" in summary
        assert "secret" not in summary

    def test_help_summary_shows_hidden(self):
        reg = CommandRegistry()
        reg.register(CommandMeta(name="secret", group="g", hidden=True))
        summary = reg.help_summary(include_hidden=True)
        assert "secret" in summary


# ---------------------------------------------------------------------------
# @command decorator
# ---------------------------------------------------------------------------


class TestCommandDecorator:
    def test_basic_decorator(self):
        reg = CommandRegistry()

        @command(reg, group="build", help="Build it")
        def build():
            return 42

        assert len(reg) == 1
        meta = reg.get("build:build")
        assert meta is not None
        assert meta.execute is build
        assert meta.help == "Build it"
        # Function still works
        assert build() == 42

    def test_decorator_custom_name(self):
        reg = CommandRegistry()

        @command(reg, name="compile", group="build")
        def do_compile():
            pass

        assert reg.get("build:compile") is not None

    def test_decorator_with_requires(self):
        reg = CommandRegistry()

        @command(reg, requires=("build:compile",))
        def link():
            pass

        meta = reg.get("link")
        assert meta is not None
        assert meta.requires == ("build:compile",)

    def test_decorator_uses_docstring_as_help(self):
        reg = CommandRegistry()

        @command(reg)
        def doctor():
            """Check environment health."""
            pass

        meta = reg.get("doctor")
        assert meta is not None
        assert meta.help == "Check environment health."

    def test_decorator_explicit_help_overrides_docstring(self):
        reg = CommandRegistry()

        @command(reg, help="Custom help")
        def something():
            """Docstring help."""
            pass

        meta = reg.get("something")
        assert meta is not None
        assert meta.help == "Custom help"

    def test_decorator_with_tags(self):
        reg = CommandRegistry()

        @command(reg, tags={"platform": "linux"})
        def special():
            pass

        meta = reg.get("special")
        assert meta is not None
        assert meta.tags == {"platform": "linux"}
