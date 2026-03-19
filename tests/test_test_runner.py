"""Tests for dekk.test_runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from dekk.build import BuildSystem
from dekk.cli.errors import NotFoundError
from dekk.test_runner import resolve_test_plan


def test_resolve_test_plan_python_project_uses_pytest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\nrequires = ['hatchling']\nbuild-backend = 'hatchling.build'\n",
        encoding="utf-8",
    )

    plan = resolve_test_plan(tmp_path, ("-q",))
    assert plan.cmd == (sys.executable, "-m", "pytest", "-q")


def test_resolve_test_plan_cargo_project_uses_cargo_test(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname='demo'\nversion='0.1.0'\nedition='2021'\n",
        encoding="utf-8",
    )

    plan = resolve_test_plan(tmp_path)
    assert plan.cmd == ("cargo", "test")


def test_resolve_test_plan_npm_requires_test_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "scripts": {"build": "tsc"}}),
        encoding="utf-8",
    )

    with pytest.raises(NotFoundError, match="No test script found"):
        resolve_test_plan(tmp_path)


def test_resolve_test_plan_make_uses_test_target(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("test:\n\t@echo ok\n", encoding="utf-8")

    plan = resolve_test_plan(tmp_path)
    assert plan.cmd == ("make", "test")
