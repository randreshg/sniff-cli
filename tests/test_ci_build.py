"""Tests for CI build hints advisor."""

import pytest

from sniff_cli.ci import CIInfo, CIProvider, CIRunnerInfo, CIBuildAdvisor, CIBuildHints


# ── Helpers ──────────────────────────────────────────────────────────

def _ci_info(
    *,
    is_ci: bool = True,
    provider_name: str = "github_actions",
    display_name: str = "GitHub Actions",
    cpu_cores: int | None = None,
) -> CIInfo:
    """Build a CIInfo with sensible defaults for testing."""
    provider = CIProvider(name=provider_name, display_name=display_name) if is_ci else None
    runner = CIRunnerInfo(cpu_cores=cpu_cores)
    return CIInfo(is_ci=is_ci, provider=provider, runner=runner)


# ── Non-CI (local) ──────────────────────────────────────────────────

class TestLocalEnvironment:
    """When not in CI, advisor should return permissive defaults."""

    def test_local_returns_defaults(self):
        ci = _ci_info(is_ci=False)
        hints = CIBuildAdvisor(ci).advise()

        assert hints.max_jobs is None
        assert hints.max_test_workers is None
        assert hints.incremental is True
        assert hints.use_color is False
        assert hints.verbose is False
        assert hints.ci_output is False
        assert hints.env_hints == {}

    def test_local_is_default_dataclass(self):
        ci = _ci_info(is_ci=False)
        hints = CIBuildAdvisor(ci).advise()
        assert hints == CIBuildHints()


# ── CI parallelism capping ──────────────────────────────────────────

class TestParallelism:
    """Parallelism should be capped on constrained runners."""

    def test_small_runner_1_core(self):
        ci = _ci_info(cpu_cores=1)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.max_jobs == 1
        assert hints.max_test_workers == 1

    def test_small_runner_2_cores(self):
        ci = _ci_info(cpu_cores=2)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.max_jobs == 1
        assert hints.max_test_workers == 1

    def test_medium_runner_3_cores(self):
        ci = _ci_info(cpu_cores=3)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.max_jobs == 3
        assert hints.max_test_workers == 3

    def test_medium_runner_4_cores(self):
        ci = _ci_info(cpu_cores=4)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.max_jobs == 4
        assert hints.max_test_workers == 4

    def test_large_runner_8_cores(self):
        ci = _ci_info(cpu_cores=8)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.max_jobs is None
        assert hints.max_test_workers is None

    def test_large_runner_16_cores(self):
        ci = _ci_info(cpu_cores=16)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.max_jobs is None
        assert hints.max_test_workers is None

    def test_unknown_cores(self):
        ci = _ci_info(cpu_cores=None)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.max_jobs is None
        assert hints.max_test_workers is None


# ── Incremental builds ──────────────────────────────────────────────

class TestIncremental:
    """CI should disable incremental builds; local should keep them."""

    def test_ci_disables_incremental(self):
        ci = _ci_info()
        hints = CIBuildAdvisor(ci).advise()
        assert hints.incremental is False

    def test_local_keeps_incremental(self):
        ci = _ci_info(is_ci=False)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.incremental is True


# ── Color support ────────────────────────────────────────────────────

class TestColorSupport:
    """Color should be enabled for providers known to support ANSI."""

    @pytest.mark.parametrize(
        "provider_name",
        ["github_actions", "gitlab_ci", "buildkite", "circleci"],
    )
    def test_color_providers(self, provider_name):
        ci = _ci_info(provider_name=provider_name, display_name=provider_name)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.use_color is True
        assert hints.env_hints.get("FORCE_COLOR") == "1"

    @pytest.mark.parametrize(
        "provider_name",
        ["jenkins", "travis", "azure_pipelines", "bitbucket", "unknown"],
    )
    def test_no_color_providers(self, provider_name):
        ci = _ci_info(provider_name=provider_name, display_name=provider_name)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.use_color is False
        assert "FORCE_COLOR" not in hints.env_hints

    def test_no_provider_no_color(self):
        ci = CIInfo(is_ci=True)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.use_color is False


# ── Output settings ──────────────────────────────────────────────────

class TestOutputSettings:
    """CI should enable verbose and CI output mode."""

    def test_ci_verbose(self):
        ci = _ci_info()
        hints = CIBuildAdvisor(ci).advise()
        assert hints.verbose is True

    def test_ci_output_mode(self):
        ci = _ci_info()
        hints = CIBuildAdvisor(ci).advise()
        assert hints.ci_output is True

    def test_local_quiet(self):
        ci = _ci_info(is_ci=False)
        hints = CIBuildAdvisor(ci).advise()
        assert hints.verbose is False
        assert hints.ci_output is False


# ── Frozen dataclass ─────────────────────────────────────────────────

class TestCIBuildHintsFrozen:
    """CIBuildHints should be immutable."""

    def test_frozen(self):
        hints = CIBuildHints()
        with pytest.raises(AttributeError):
            hints.max_jobs = 4  # type: ignore[misc]

    def test_frozen_verbose(self):
        hints = CIBuildHints()
        with pytest.raises(AttributeError):
            hints.verbose = True  # type: ignore[misc]
