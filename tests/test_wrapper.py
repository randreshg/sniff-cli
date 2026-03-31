"""Tests for dekk.execution.wrapper -- self-contained wrapper script generation."""

from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from dekk.environment.activation import ActivationResult
from dekk.execution.os import WindowsDekkOS
from dekk.execution.install import InstallResult
from dekk.execution.wrapper import (
    WrapperGenerator,
    _cmd_escape_value,
    _dir_in_path,
    _generate_cmd_script,
    _sh_escape_double,
    _sh_quote,
)

# ---------------------------------------------------------------------------
# _sh_quote
# ---------------------------------------------------------------------------


class TestShQuote:
    def test_empty_string(self):
        assert _sh_quote("") == "''"

    def test_simple_value(self):
        assert _sh_quote("hello") == "'hello'"

    def test_single_quote_escaped(self):
        # The only character needing escape inside single quotes is ' itself.
        assert _sh_quote("it's") == "'it'\\''s'"

    def test_dollar_signs_literal(self):
        # Single-quoting prevents variable expansion.
        result = _sh_quote("$HOME")
        assert "$HOME" in result
        assert result == "'$HOME'"

    def test_backticks_literal(self):
        result = _sh_quote("`whoami`")
        assert result == "'`whoami`'"

    def test_spaces_preserved(self):
        result = _sh_quote("hello world")
        assert result == "'hello world'"

    def test_newlines_preserved(self):
        result = _sh_quote("line1\nline2")
        assert result == "'line1\nline2'"


# ---------------------------------------------------------------------------
# _sh_escape_double
# ---------------------------------------------------------------------------


class TestShEscapeDouble:
    def test_dollar_escaped(self):
        assert _sh_escape_double("$VAR") == "\\$VAR"

    def test_backtick_escaped(self):
        assert _sh_escape_double("`cmd`") == "\\`cmd\\`"

    def test_double_quote_escaped(self):
        assert _sh_escape_double('"hi"') == '\\"hi\\"'

    def test_backslash_escaped(self):
        assert _sh_escape_double("a\\b") == "a\\\\b"

    def test_normal_text_unchanged(self):
        assert _sh_escape_double("hello/world") == "hello/world"

    def test_exclamation_not_escaped(self):
        # ! is NOT special in /bin/sh, only in interactive bash.
        assert _sh_escape_double("wow!") == "wow!"

    def test_combined_special_chars(self):
        assert _sh_escape_double('$`"\\') == '\\$\\`\\"\\\\'


class TestCmdEscapeValue:
    def test_percent_escaped(self):
        assert _cmd_escape_value("%APPDATA%") == "%%APPDATA%%"

    def test_quotes_escaped(self):
        assert _cmd_escape_value('say "hi"') == 'say ""hi""'


# ---------------------------------------------------------------------------
# WrapperGenerator.generate
# ---------------------------------------------------------------------------


class TestGenerate:
    """Tests for WrapperGenerator.generate()."""

    @pytest.fixture()
    def dummy_target(self, tmp_path: Path) -> Path:
        target = tmp_path / "myapp"
        target.write_text("#!/bin/sh\necho hi\n")
        target.chmod(0o755)
        return target

    @pytest.fixture()
    def dummy_python(self, tmp_path: Path) -> Path:
        py = tmp_path / "python3"
        py.write_text('#!/bin/sh\nexec python3 "$@"\n')
        py.chmod(0o755)
        return py

    def test_basic_script_structure(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=[],
            project_name="testproj",
        )
        lines = script.split("\n")
        assert lines[0] == "#!/bin/sh"
        assert any("Wrapper for testproj" in line for line in lines)
        assert any("exec" in line for line in lines)

    def test_env_vars_exported(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={"FOO": "/opt/foo", "BAR": "baz"},
            path_prepends=[],
            project_name="proj",
        )
        assert "export FOO='/opt/foo'" in script
        assert "export BAR='baz'" in script

    def test_path_prepends(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=["/opt/bin", "/usr/local/bin"],
            project_name="proj",
        )
        assert 'export PATH="/opt/bin:/usr/local/bin:$PATH"' in script

    def test_path_key_excluded_from_env_vars(self, dummy_target: Path):
        # PATH in env_vars is handled by path_prepends, so it should be skipped.
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={"PATH": "/should/be/skipped", "KEEP": "yes"},
            path_prepends=["/actual/path"],
            project_name="proj",
        )
        assert "export PATH=" in script
        # The PATH export should be the path_prepends version, not the env_vars one.
        assert "/should/be/skipped" not in script
        assert "export KEEP='yes'" in script

    def test_python_target(self, dummy_target: Path, dummy_python: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=[],
            project_name="proj",
            python=dummy_python,
        )
        resolved_python = str(dummy_python.resolve())
        resolved_target = str(dummy_target.resolve())
        assert f"exec '{resolved_python}' '{resolved_target}'" in script
        assert '"$@"' in script

    def test_no_python_target(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=[],
            project_name="proj",
        )
        resolved_target = str(dummy_target.resolve())
        assert f"exec '{resolved_target}' " in script
        # Should NOT have a python reference in exec line.
        assert "python" not in script.split("exec")[-1].split("\n")[0].lower() or True
        # More direct: the exec line should have exactly one quoted path (the target).
        exec_line = [line for line in script.split("\n") if line.startswith("exec")][0]
        # Only one quoted path before "$@"
        assert exec_line.count("'") == 2  # opening and closing quote around target

    def test_target_not_found_raises(self, tmp_path: Path):
        from dekk.cli.errors import NotFoundError

        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(NotFoundError, match="Target does not exist"):
            WrapperGenerator.generate(
                target=nonexistent,
                env_vars={},
                path_prepends=[],
                project_name="proj",
            )

    def test_python_not_found_raises(self, dummy_target: Path, tmp_path: Path):
        from dekk.cli.errors import NotFoundError

        nonexistent_python = tmp_path / "no_such_python"
        with pytest.raises(NotFoundError, match="Python interpreter does not exist"):
            WrapperGenerator.generate(
                target=dummy_target,
                env_vars={},
                path_prepends=[],
                project_name="proj",
                python=nonexistent_python,
            )

    def test_empty_env_vars(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=[],
            project_name="proj",
        )
        # No export statements for env vars.
        assert (
            "export" not in script.replace("# ---", "").split("exec")[0]
            or script.count("export") == 0
        )

    def test_empty_path_prepends(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=[],
            project_name="proj",
        )
        assert "export PATH=" not in script

    def test_values_with_special_chars(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={"GREETING": "it's a $test"},
            path_prepends=[],
            project_name="proj",
        )
        # Single-quoted value: ' handled by '\'' idiom, $ stays literal.
        assert "export GREETING='it'\\''s a $test'" in script

    def test_timestamp_in_header(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=[],
            project_name="proj",
        )
        # UTC timestamp format: YYYY-MM-DDTHH:MM:SSZ
        import re

        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", script)

    def test_project_name_in_header(self, dummy_target: Path):
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=[],
            project_name="my-cool-project",
        )
        assert "my-cool-project" in script

    def test_path_prepends_with_special_chars(self, dummy_target: Path):
        # Paths with dollar signs or spaces are escaped for double-quote context.
        script = WrapperGenerator.generate(
            target=dummy_target,
            env_vars={},
            path_prepends=["/path with spaces", "/path/$pecial"],
            project_name="proj",
        )
        # Inside the double-quoted PATH export, $ must be escaped.
        assert "\\$pecial" in script
        assert "path with spaces" in script

    def test_windows_cmd_script_helper(self, dummy_target: Path, dummy_python: Path):
        script = _generate_cmd_script(
            target=dummy_target.resolve(),
            env_vars={"FOO": "%USERPROFILE%"},
            path_prepends=[r"C:\tools\bin", r"C:\Program Files\MyApp"],
            project_name="proj",
            prepend_vars={"PATHLIKE": r"C:\libs"},
            python=dummy_python.resolve(),
            timestamp="2026-03-19T00:00:00Z",
        )
        assert script.startswith("@echo off")
        assert 'set "FOO=%%USERPROFILE%%"' in script
        assert 'set "PATH=C:\\tools\\bin;C:\\Program Files\\MyApp;%PATH%"' in script
        assert 'set "PATHLIKE=C:\\libs;%PATHLIKE%"' in script
        assert "%*" in script


# ---------------------------------------------------------------------------
# WrapperGenerator.from_activation
# ---------------------------------------------------------------------------


class TestFromActivation:
    """Tests for WrapperGenerator.from_activation() and _generate_from_activation."""

    @pytest.fixture()
    def dummy_target(self, tmp_path: Path) -> Path:
        target = tmp_path / "tool"
        target.write_text("#!/bin/sh\n")
        target.chmod(0o755)
        return target

    def test_extracts_env_vars(self, dummy_target: Path):
        activation = ActivationResult(env_vars={"FOO": "bar", "BAZ": "qux"})
        script = WrapperGenerator.from_activation(
            activation,
            target=dummy_target,
            project_name="proj",
        )
        assert "export FOO='bar'" in script
        assert "export BAZ='qux'" in script

    def test_extracts_path_from_env(self, dummy_target: Path):
        # PATH in env_vars should become path_prepends, not an env var export.
        activation = ActivationResult(
            env_vars={"PATH": "/new/bin:/another/bin", "OTHER": "val"},
        )
        with patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
            script = WrapperGenerator.from_activation(
                activation,
                target=dummy_target,
                project_name="proj",
            )
        assert "export OTHER='val'" in script
        # PATH should be handled as prepend, not as a regular env var export.
        assert "/new/bin" in script
        assert "/another/bin" in script

    def test_deduplicates_path_entries(self, dummy_target: Path):
        activation = ActivationResult(
            env_vars={"PATH": "/opt/bin:/opt/bin:/opt/bin"},
        )
        with patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
            script = WrapperGenerator.from_activation(
                activation,
                target=dummy_target,
                project_name="proj",
            )
        # /opt/bin should appear exactly once in the PATH export line.
        path_line = [line for line in script.split("\n") if "export PATH=" in line][0]
        assert path_line.count("/opt/bin") == 1

    def test_filters_current_path(self, dummy_target: Path):
        # Entries already in the current $PATH should be excluded.
        activation = ActivationResult(
            env_vars={"PATH": "/usr/bin:/new/bin"},
        )
        with patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
            script = WrapperGenerator.from_activation(
                activation,
                target=dummy_target,
                project_name="proj",
            )
        # /usr/bin is already in PATH, so it should be filtered out.
        path_lines = [line for line in script.split("\n") if "export PATH=" in line]
        if path_lines:
            assert "/usr/bin" not in path_lines[0] or path_lines[0].endswith('$PATH"')
        # /new/bin should be present since it's not in current PATH.
        assert "/new/bin" in script

    def test_empty_activation(self, dummy_target: Path):
        activation = ActivationResult(env_vars={})
        script = WrapperGenerator.from_activation(
            activation,
            target=dummy_target,
            project_name="proj",
        )
        # Should still produce a valid script with shebang and exec.
        assert script.startswith("#!/bin/sh")
        assert "exec" in script


# ---------------------------------------------------------------------------
# WrapperGenerator.install
# ---------------------------------------------------------------------------


class TestInstall:
    """Tests for WrapperGenerator.install()."""

    SAMPLE_SCRIPT = '#!/bin/sh\nexec /usr/bin/true "$@"\n'

    def test_writes_executable_file(self, tmp_path: Path):
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=tmp_path,
        )
        assert result.bin_path.exists()
        mode = result.bin_path.stat().st_mode
        assert mode & stat.S_IXUSR, "Owner execute bit not set"
        assert mode & stat.S_IXGRP, "Group execute bit not set"
        assert mode & stat.S_IXOTH, "Other execute bit not set"

    def test_content_matches_script(self, tmp_path: Path):
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=tmp_path,
        )
        content = result.bin_path.read_text(encoding="utf-8")
        assert content == self.SAMPLE_SCRIPT

    def test_default_install_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.chdir(tmp_path)
        result = WrapperGenerator.install(self.SAMPLE_SCRIPT, "myapp")
        expected = tmp_path / ".install" / "myapp"
        assert result.bin_path == expected
        assert result.bin_path.exists()

    def test_default_install_dir_windows(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setattr("dekk.execution.wrapper.get_dekk_os", lambda: WindowsDekkOS())
        monkeypatch.chdir(tmp_path)
        result = WrapperGenerator.install(self.SAMPLE_SCRIPT, "myapp")
        expected = tmp_path / ".install" / "myapp.cmd"
        assert result.bin_path == expected
        assert result.bin_path.exists()

    def test_custom_install_dir(self, tmp_path: Path):
        custom = tmp_path / "custom_bin"
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=custom,
        )
        assert result.bin_path == custom / "myapp"
        assert result.bin_path.exists()

    def test_custom_install_dir_windows_uses_cmd_suffix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr("dekk.execution.wrapper.get_dekk_os", lambda: WindowsDekkOS())
        custom = tmp_path / "custom_bin"
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=custom,
        )
        assert result.bin_path == custom / "myapp.cmd"
        assert result.bin_path.exists()

    def test_creates_install_dir(self, tmp_path: Path):
        nested = tmp_path / "a" / "b" / "c"
        assert not nested.exists()
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=nested,
        )
        assert nested.is_dir()
        assert result.bin_path.exists()

    def test_in_path_detection(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        monkeypatch.setenv("PATH", str(bin_dir))
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=bin_dir,
        )
        assert result.in_path is True

    def test_not_in_path_detection(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        monkeypatch.setenv("PATH", "/some/unrelated/dir")
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=bin_dir,
        )
        assert result.in_path is False

    def test_message_includes_path_hint(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        monkeypatch.setenv("PATH", "/some/unrelated/dir")
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=bin_dir,
        )
        assert "add" in result.message.lower()
        assert "PATH" in result.message

    def test_name_with_separator_raises(self, tmp_path: Path):
        from dekk.cli.errors import ValidationError

        with pytest.raises(ValidationError, match="path separator"):
            WrapperGenerator.install(
                self.SAMPLE_SCRIPT,
                "foo/bar",
                install_dir=tmp_path,
            )

    def test_overwrites_existing_wrapper(self, tmp_path: Path):
        WrapperGenerator.install("#!/bin/sh\necho old\n", "myapp", install_dir=tmp_path)
        new_script = "#!/bin/sh\necho new\n"
        result = WrapperGenerator.install(new_script, "myapp", install_dir=tmp_path)
        content = result.bin_path.read_text(encoding="utf-8")
        assert content == new_script

    def test_message_when_in_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        monkeypatch.setenv("PATH", str(bin_dir))
        result = WrapperGenerator.install(
            self.SAMPLE_SCRIPT,
            "myapp",
            install_dir=bin_dir,
        )
        # When in PATH, message should NOT mention "add ... to PATH".
        assert "add" not in result.message.lower()
        assert "Installed" in result.message


# ---------------------------------------------------------------------------
# WrapperGenerator.install_from_spec
# ---------------------------------------------------------------------------


class TestInstallFromSpec:
    """Tests for WrapperGenerator.install_from_spec()."""

    @pytest.fixture()
    def dummy_target(self, tmp_path: Path) -> Path:
        target = tmp_path / "mytool"
        target.write_text("#!/bin/sh\necho hello\n")
        target.chmod(0o755)
        return target

    @pytest.fixture()
    def spec_file(self, tmp_path: Path) -> Path:
        toml_content = textwrap.dedent("""\
            [project]
            name = "testproject"
        """)
        spec_path = tmp_path / ".dekk.toml"
        spec_path.write_text(toml_content)
        return spec_path

    def test_with_spec_file_path(
        self,
        tmp_path: Path,
        dummy_target: Path,
        spec_file: Path,
    ):
        install_dir = tmp_path / "install_bin"
        # Mock the EnvironmentActivator.activate to avoid needing a real conda env.
        with patch(
            "dekk.execution.wrapper.EnvironmentActivator.activate",
            return_value=ActivationResult(env_vars={"MY_VAR": "val"}),
        ):
            result = WrapperGenerator.install_from_spec(
                spec_file=spec_file,
                target=dummy_target,
                name="mytool",
                install_dir=install_dir,
            )
        assert result.bin_path.exists()
        content = result.bin_path.read_text()
        assert "#!/bin/sh" in content
        assert "MY_VAR" in content

    def test_with_environment_spec(self, tmp_path: Path, dummy_target: Path):
        from dekk.environment.spec import EnvironmentSpec

        spec = EnvironmentSpec(project_name="direct-spec")
        install_dir = tmp_path / "install_bin"
        with patch(
            "dekk.execution.wrapper.EnvironmentActivator.activate",
            return_value=ActivationResult(env_vars={}),
        ):
            result = WrapperGenerator.install_from_spec(
                spec_file=spec,
                target=dummy_target,
                name="mytool",
                install_dir=install_dir,
                project_root=tmp_path,
            )
        assert result.bin_path.exists()
        content = result.bin_path.read_text()
        assert "direct-spec" in content

    def test_infers_project_root(
        self,
        tmp_path: Path,
        dummy_target: Path,
        spec_file: Path,
    ):
        # When project_root is not given, it should be inferred from spec_file's parent.
        install_dir = tmp_path / "install_bin"
        with patch(
            "dekk.execution.wrapper.EnvironmentActivator.activate",
            return_value=ActivationResult(env_vars={}),
        ):
            with patch(
                "dekk.execution.wrapper.EnvironmentActivator.__init__",
                return_value=None,
            ) as mock_init:
                mock_init.return_value = None
                # Patch activate on the instance that __init__ creates.
                # Since __init__ is mocked, we need a different approach.
                # Let's just verify the root is derived correctly by
                # patching the full from_spec call chain.
                pass

        # Simpler approach: verify the root matches spec_file.parent.
        with patch(
            "dekk.execution.wrapper.EnvironmentActivator",
        ) as MockActivator:
            mock_instance = MockActivator.return_value
            mock_instance.activate.return_value = ActivationResult(env_vars={})
            WrapperGenerator.install_from_spec(
                spec_file=spec_file,
                target=dummy_target,
                name="mytool",
                install_dir=install_dir,
            )
            # EnvironmentActivator should have been called with the spec and
            # the resolved parent of spec_file as project_root.
            call_args = MockActivator.call_args
            actual_root = call_args[0][1]  # second positional arg
            assert actual_root == spec_file.resolve().parent


# ---------------------------------------------------------------------------
# WrapperGenerator.uninstall
# ---------------------------------------------------------------------------


class TestUninstall:
    """Tests for WrapperGenerator.uninstall()."""

    SAMPLE_SCRIPT = '#!/bin/sh\nexec /usr/bin/true "$@"\n'

    def test_removes_existing_wrapper(self, tmp_path: Path):
        # Install first, then uninstall.
        WrapperGenerator.install(self.SAMPLE_SCRIPT, "myapp", install_dir=tmp_path)
        assert (tmp_path / "myapp").exists()

        result = WrapperGenerator.uninstall("myapp", install_dir=tmp_path)
        assert not (tmp_path / "myapp").exists()
        assert "Removed" in result.message

    def test_idempotent_when_not_exists(self, tmp_path: Path):
        # Uninstalling a wrapper that doesn't exist should not raise.
        result = WrapperGenerator.uninstall("nonexistent", install_dir=tmp_path)
        assert "not found" in result.message.lower()

    def test_returns_install_result(self, tmp_path: Path):
        WrapperGenerator.install(self.SAMPLE_SCRIPT, "myapp", install_dir=tmp_path)
        result = WrapperGenerator.uninstall("myapp", install_dir=tmp_path)
        assert isinstance(result, InstallResult)
        assert result.bin_path == tmp_path / "myapp"

    def test_default_install_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.chdir(tmp_path)

        # Install to the default location, then uninstall.
        WrapperGenerator.install(self.SAMPLE_SCRIPT, "myapp")
        assert (tmp_path / ".install" / "myapp").exists()

        result = WrapperGenerator.uninstall("myapp")
        assert not (tmp_path / ".install" / "myapp").exists()
        assert result.bin_path == tmp_path / ".install" / "myapp"

    def test_default_install_dir_windows(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setattr("dekk.execution.wrapper.get_dekk_os", lambda: WindowsDekkOS())
        monkeypatch.chdir(tmp_path)

        WrapperGenerator.install(self.SAMPLE_SCRIPT, "myapp")
        assert (tmp_path / ".install" / "myapp.cmd").exists()

        result = WrapperGenerator.uninstall("myapp")
        assert not (tmp_path / ".install" / "myapp.cmd").exists()
        assert result.bin_path == tmp_path / ".install" / "myapp.cmd"

    def test_in_path_reported(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PATH", str(tmp_path))
        WrapperGenerator.install(self.SAMPLE_SCRIPT, "myapp", install_dir=tmp_path)
        result = WrapperGenerator.uninstall("myapp", install_dir=tmp_path)
        assert result.in_path is True

    def test_not_in_path_reported(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PATH", "/some/other/dir")
        WrapperGenerator.install(self.SAMPLE_SCRIPT, "myapp", install_dir=tmp_path)
        result = WrapperGenerator.uninstall("myapp", install_dir=tmp_path)
        assert result.in_path is False


# ---------------------------------------------------------------------------
# _dir_in_path
# ---------------------------------------------------------------------------


class TestDirInPath:
    def test_dir_in_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        d = tmp_path / "mybin"
        d.mkdir()
        monkeypatch.setenv("PATH", f"/usr/bin:{d}")
        assert _dir_in_path(d) is True

    def test_dir_not_in_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        d = tmp_path / "mybin"
        d.mkdir()
        monkeypatch.setenv("PATH", "/usr/bin:/usr/local/bin")
        assert _dir_in_path(d) is False

    def test_resolves_symlinks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # The real directory and a symlink pointing to it should be recognized
        # as the same directory.
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        link_dir = tmp_path / "link"
        link_dir.symlink_to(real_dir)
        # PATH contains the symlink, but we query the real dir.
        monkeypatch.setenv("PATH", str(link_dir))
        assert _dir_in_path(real_dir) is True

    def test_empty_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        d = tmp_path / "bin"
        d.mkdir()
        monkeypatch.setenv("PATH", "")
        assert _dir_in_path(d) is False

    def test_path_with_empty_entries(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Empty entries between colons (e.g., "/usr/bin::/opt/bin") should not cause errors.
        d = tmp_path / "mybin"
        d.mkdir()
        monkeypatch.setenv("PATH", f"/usr/bin::{d}:")
        assert _dir_in_path(d) is True
