"""Tests for shell detection and integration module."""

from __future__ import annotations

import os
from unittest.mock import patch

from dekk.shell import (
    ActivationConfig,
    ActivationScriptBuilder,
    AliasSuggestor,
    CommandArg,
    CommandFlag,
    CompletionGenerator,
    CompletionSpec,
    EnvVar,
    PromptHelper,
    ShellDetector,
    ShellInfo,
    ShellKind,
    Subcommand,
)

# ---------------------------------------------------------------------------
# ShellDetector
# ---------------------------------------------------------------------------


class TestShellDetector:
    def setup_method(self):
        self.detector = ShellDetector()

    def test_detect_with_bash_override(self):
        info = self.detector.detect(shell_override="bash")
        assert info.kind == ShellKind.BASH

    def test_detect_with_zsh_override(self):
        info = self.detector.detect(shell_override="zsh")
        assert info.kind == ShellKind.ZSH

    def test_detect_with_fish_override(self):
        info = self.detector.detect(shell_override="fish")
        assert info.kind == ShellKind.FISH

    def test_detect_with_tcsh_override(self):
        info = self.detector.detect(shell_override="tcsh")
        assert info.kind == ShellKind.TCSH

    def test_detect_with_path_override(self):
        info = self.detector.detect(shell_override="/bin/bash")
        assert info.kind == ShellKind.BASH

    def test_detect_with_powershell_override(self):
        info = self.detector.detect(shell_override="pwsh")
        assert info.kind == ShellKind.PWSH

    @patch.dict(os.environ, {"SHELL": "/bin/bash"})
    def test_detect_from_env(self):
        info = self.detector.detect()
        assert info.kind == ShellKind.BASH
        assert info.login_shell == "/bin/bash"

    @patch.dict(os.environ, {"SHELL": "/usr/bin/zsh"})
    def test_detect_zsh_from_env(self):
        info = self.detector.detect()
        assert info.kind == ShellKind.ZSH

    @patch.dict(os.environ, {"SHELL": "/usr/bin/fish"})
    def test_detect_fish_from_env(self):
        info = self.detector.detect()
        assert info.kind == ShellKind.FISH

    @patch.dict(os.environ, {"SHELL": "/tool/pandora/bin/tcsh"})
    def test_detect_tcsh_from_env(self):
        info = self.detector.detect()
        assert info.kind == ShellKind.TCSH

    def test_detect_never_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            # Even with no SHELL env var, should not raise
            info = self.detector.detect()
            assert isinstance(info, ShellInfo)

    def test_shell_info_is_posix(self):
        info = ShellInfo(kind=ShellKind.BASH)
        assert info.is_posix
        assert not info.is_fish
        assert not info.is_powershell
        assert not info.is_csh_family

    def test_shell_info_is_fish(self):
        info = ShellInfo(kind=ShellKind.FISH)
        assert info.is_fish
        assert not info.is_posix

    def test_shell_info_is_powershell(self):
        info = ShellInfo(kind=ShellKind.POWERSHELL)
        assert info.is_powershell
        assert not info.is_posix

    def test_shell_info_is_tcsh(self):
        info = ShellInfo(kind=ShellKind.TCSH)
        assert info.is_csh_family
        assert not info.is_posix

    def test_supports_functions(self):
        assert ShellInfo(kind=ShellKind.BASH).supports_functions
        assert ShellInfo(kind=ShellKind.ZSH).supports_functions
        assert ShellInfo(kind=ShellKind.FISH).supports_functions
        assert not ShellInfo(kind=ShellKind.SH).supports_functions
        assert not ShellInfo(kind=ShellKind.DASH).supports_functions


# ---------------------------------------------------------------------------
# ActivationScriptBuilder
# ---------------------------------------------------------------------------


class TestActivationScriptBuilder:
    def setup_method(self):
        self.builder = ActivationScriptBuilder()
        self.config = ActivationConfig(
            env_vars=(
                EnvVar(name="MLIR_DIR", value="/opt/conda/lib/cmake/mlir"),
                EnvVar(name="LLVM_DIR", value="/opt/conda/lib/cmake/llvm"),
            ),
            path_prepends=("/opt/conda/bin",),
            app_name="apxm",
        )

    def test_posix_activation(self):
        script = self.builder.build(self.config, ShellKind.BASH)
        assert 'export MLIR_DIR="/opt/conda/lib/cmake/mlir"' in script
        assert 'export LLVM_DIR="/opt/conda/lib/cmake/llvm"' in script
        assert 'export PATH="/opt/conda/bin:$PATH"' in script
        assert "# Activation script for apxm" in script

    def test_posix_saves_old_values(self):
        script = self.builder.build(self.config, ShellKind.BASH)
        assert "_OLD_MLIR_DIR=" in script
        assert "_OLD_LLVM_DIR=" in script
        assert "_OLD_PATH=" in script

    def test_posix_deactivation(self):
        script = self.builder.build_deactivate(self.config, ShellKind.BASH)
        assert "# Deactivation script for apxm" in script
        assert "unset _OLD_MLIR_DIR" in script
        assert "unset MLIR_DIR" in script

    def test_zsh_same_as_posix(self):
        bash_script = self.builder.build(self.config, ShellKind.BASH)
        zsh_script = self.builder.build(self.config, ShellKind.ZSH)
        assert bash_script == zsh_script

    def test_fish_activation(self):
        script = self.builder.build(self.config, ShellKind.FISH)
        assert "set -gx MLIR_DIR /opt/conda/lib/cmake/mlir" in script
        assert "set -gx LLVM_DIR /opt/conda/lib/cmake/llvm" in script
        assert "set -gx PATH /opt/conda/bin $PATH" in script

    def test_fish_deactivation(self):
        script = self.builder.build_deactivate(self.config, ShellKind.FISH)
        assert "set -e _OLD_MLIR_DIR" in script

    def test_tcsh_activation(self):
        script = self.builder.build(self.config, ShellKind.TCSH)
        assert 'setenv MLIR_DIR "/opt/conda/lib/cmake/mlir"' in script
        assert 'setenv LLVM_DIR "/opt/conda/lib/cmake/llvm"' in script
        assert 'setenv PATH "/opt/conda/bin:$PATH"' in script

    def test_tcsh_deactivation(self):
        script = self.builder.build_deactivate(self.config, ShellKind.TCSH)
        assert "unsetenv MLIR_DIR" in script

    def test_powershell_activation(self):
        script = self.builder.build(self.config, ShellKind.POWERSHELL)
        assert '$env:MLIR_DIR = "/opt/conda/lib/cmake/mlir"' in script
        assert '$env:LLVM_DIR = "/opt/conda/lib/cmake/llvm"' in script

    def test_powershell_deactivation(self):
        script = self.builder.build_deactivate(self.config, ShellKind.POWERSHELL)
        assert "Remove-Item Env:MLIR_DIR" in script

    def test_prepend_path_var(self):
        config = ActivationConfig(
            env_vars=(EnvVar(name="LD_LIBRARY_PATH", value="/opt/lib", prepend_path=True),),
            app_name="test",
        )
        script = self.builder.build(config, ShellKind.BASH)
        assert 'export LD_LIBRARY_PATH="/opt/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"' in script

    def test_banner(self):
        config = ActivationConfig(
            env_vars=(),
            app_name="test",
            banner="APXM environment activated",
        )
        script = self.builder.build(config, ShellKind.BASH)
        assert 'echo "APXM environment activated"' in script

    def test_fish_banner(self):
        config = ActivationConfig(
            env_vars=(),
            app_name="test",
            banner="APXM environment activated",
        )
        script = self.builder.build(config, ShellKind.FISH)
        assert 'echo "APXM environment activated"' in script

    def test_empty_config(self):
        config = ActivationConfig()
        script = self.builder.build(config, ShellKind.BASH)
        assert "Activation script" in script

    def test_apxm_realistic_config(self):
        """Test with the actual APXM activation config pattern."""
        prefix = "/home/user/miniforge3/envs/apxm"
        config = ActivationConfig(
            env_vars=(
                EnvVar(name="MLIR_DIR", value=f"{prefix}/lib/cmake/mlir"),
                EnvVar(name="LLVM_DIR", value=f"{prefix}/lib/cmake/llvm"),
                EnvVar(name="MLIR_PREFIX", value=prefix),
                EnvVar(name="LLVM_PREFIX", value=prefix),
            ),
            path_prepends=(f"{prefix}/bin",),
            app_name="apxm",
            banner="APXM MLIR/LLVM toolchain activated",
        )

        # Test all shells
        for shell in (
            ShellKind.BASH,
            ShellKind.ZSH,
            ShellKind.FISH,
            ShellKind.TCSH,
            ShellKind.POWERSHELL,
        ):
            script = self.builder.build(config, shell)
            assert prefix in script
            assert "mlir" in script.lower() or "MLIR" in script


# ---------------------------------------------------------------------------
# CompletionGenerator
# ---------------------------------------------------------------------------


class TestCompletionGenerator:
    def setup_method(self):
        self.generator = CompletionGenerator()
        self.spec = CompletionSpec(
            command="apxm",
            description="APxM CLI",
            flags=(
                CommandFlag(long="--config", description="Config file path", takes_value=True),
                CommandFlag(
                    long="--trace",
                    description="Enable tracing",
                    takes_value=True,
                    choices=("trace", "debug", "info", "warn", "error"),
                ),
            ),
            subcommands=(
                Subcommand(
                    name="compile",
                    description="Compile ApxmGraph to artifact",
                    flags=(
                        CommandFlag(
                            long="--output", short="-o", description="Output path", takes_value=True
                        ),
                        CommandFlag(
                            long="--opt-level",
                            short="-O",
                            description="Optimization level",
                            takes_value=True,
                            choices=("0", "1", "2", "3"),
                        ),
                        CommandFlag(
                            long="--emit-diagnostics",
                            description="Emit diagnostics JSON",
                            takes_value=True,
                        ),
                    ),
                    args=(
                        CommandArg(
                            name="input", description="Input graph file", file_completion=True
                        ),
                    ),
                ),
                Subcommand(
                    name="execute",
                    description="Compile and run a graph",
                    flags=(
                        CommandFlag(
                            long="--opt-level",
                            short="-O",
                            description="Optimization level",
                            takes_value=True,
                            choices=("0", "1", "2", "3"),
                        ),
                        CommandFlag(
                            long="--emit-metrics", description="Emit metrics JSON", takes_value=True
                        ),
                    ),
                    args=(
                        CommandArg(
                            name="input", description="Input graph file", file_completion=True
                        ),
                    ),
                ),
                Subcommand(name="doctor", description="Diagnose dependencies"),
                Subcommand(
                    name="activate",
                    description="Print shell env exports",
                    flags=(
                        CommandFlag(
                            long="--shell",
                            description="Shell format",
                            takes_value=True,
                            choices=("sh", "bash", "zsh", "fish", "tcsh"),
                        ),
                    ),
                ),
                Subcommand(name="install", description="Install conda environment"),
                Subcommand(
                    name="register",
                    description="Manage LLM credentials",
                    subcommands=(
                        Subcommand(name="add", description="Add a credential"),
                        Subcommand(name="list", description="List credentials"),
                        Subcommand(name="remove", description="Remove a credential"),
                        Subcommand(name="test", description="Test credentials"),
                    ),
                ),
            ),
        )

    def test_bash_completion(self):
        script = self.generator.generate(self.spec, ShellKind.BASH)
        assert "__apxm_completions" in script
        assert "complete -F" in script
        assert "compile" in script
        assert "execute" in script
        assert "doctor" in script
        assert "activate" in script

    def test_zsh_completion(self):
        script = self.generator.generate(self.spec, ShellKind.ZSH)
        assert "#compdef apxm" in script
        assert "_apxm" in script
        assert "compile" in script
        assert "execute" in script

    def test_fish_completion(self):
        script = self.generator.generate(self.spec, ShellKind.FISH)
        assert "complete -c apxm" in script
        assert "compile" in script
        assert "opt-level" in script  # fish uses -l opt-level (no -- prefix)

    def test_powershell_completion(self):
        script = self.generator.generate(self.spec, ShellKind.POWERSHELL)
        assert "Register-ArgumentCompleter" in script
        assert "apxm" in script
        assert "compile" in script

    def test_unsupported_shell(self):
        script = self.generator.generate(self.spec, ShellKind.TCSH)
        assert "not supported" in script

    def test_nested_subcommands_in_bash(self):
        script = self.generator.generate(self.spec, ShellKind.BASH)
        assert "register" in script
        assert "add" in script  # nested under register


# ---------------------------------------------------------------------------
# PromptHelper
# ---------------------------------------------------------------------------


class TestPromptHelper:
    def setup_method(self):
        self.helper = PromptHelper()

    def test_bash_prompt(self):
        snippet = self.helper.status_snippet(ShellKind.BASH)
        assert "SNIFF_STATUS" in snippet

    def test_fish_prompt(self):
        snippet = self.helper.status_snippet(ShellKind.FISH)
        assert "set -q SNIFF_STATUS" in snippet

    def test_powershell_prompt(self):
        snippet = self.helper.status_snippet(ShellKind.POWERSHELL)
        assert "$env:SNIFF_STATUS" in snippet

    def test_custom_env_var(self):
        snippet = self.helper.status_snippet(ShellKind.BASH, env_var="APXM_ENV")
        assert "APXM_ENV" in snippet


# ---------------------------------------------------------------------------
# AliasSuggestor
# ---------------------------------------------------------------------------


class TestAliasSuggestor:
    def setup_method(self):
        self.suggestor = AliasSuggestor()

    def test_suggest_basic(self):
        suggestions = self.suggestor.suggest("apxm", subcommands=["compile", "execute", "doctor"])
        assert len(suggestions) > 0
        aliases = [s.alias for s in suggestions]
        # Should have a short alias for the base command
        assert "ap" in aliases

    def test_suggest_subcommand_aliases(self):
        suggestions = self.suggestor.suggest("apxm", subcommands=["compile", "execute"])
        aliases = [s.alias for s in suggestions]
        assert "ac" in aliases  # apxm compile -> ac
        assert "ae" in aliases  # apxm execute -> ae

    def test_render_posix(self):
        suggestions = self.suggestor.suggest("apxm", subcommands=["compile"])
        rendered = self.suggestor.render(suggestions, ShellKind.BASH)
        assert "alias " in rendered

    def test_render_fish(self):
        suggestions = self.suggestor.suggest("apxm", subcommands=["compile"])
        rendered = self.suggestor.render(suggestions, ShellKind.FISH)
        assert "alias " in rendered

    def test_render_tcsh(self):
        suggestions = self.suggestor.suggest("apxm", subcommands=["compile"])
        rendered = self.suggestor.render(suggestions, ShellKind.TCSH)
        assert "alias " in rendered

    def test_render_powershell(self):
        suggestions = self.suggestor.suggest("apxm", subcommands=["compile"])
        rendered = self.suggestor.render(suggestions, ShellKind.POWERSHELL)
        assert "Set-Alias" in rendered

    def test_common_flags(self):
        suggestions = self.suggestor.suggest(
            "apxm",
            common_flags={"v": "--trace debug"},
        )
        found = [s for s in suggestions if s.alias == "apxmv"]
        assert len(found) == 1
        assert "--trace debug" in found[0].command

