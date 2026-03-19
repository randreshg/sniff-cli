"""Tests for built-in CLI example templates."""

from __future__ import annotations

import pytest

from sniff_cli.cli.commands import _load_example_template
from sniff_cli.cli.errors import ConfigError


class TestLoadExampleTemplate:
    def test_loads_minimal_template(self):
        content = _load_example_template("minimal")
        assert "[project]" in content
        assert "[tools]" in content

    def test_injects_project_name(self):
        content = _load_example_template("conda", project_name="demo-app")
        assert 'name = "demo-app"' in content
        assert 'name = "ml-project"' not in content

    def test_unknown_template_raises(self):
        with pytest.raises(ConfigError, match="Unknown example template"):
            _load_example_template("does-not-exist")
