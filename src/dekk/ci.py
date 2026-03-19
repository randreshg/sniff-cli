"""CI/CD provider detection - identify CI environment, extract metadata, detect runner capabilities."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CIProvider:
    """Detected CI/CD provider information."""

    name: str  # "github_actions", "gitlab_ci", "jenkins", "circleci", "azure_pipelines", etc.
    display_name: str  # "GitHub Actions", "GitLab CI", etc.


@dataclass(frozen=True)
class CIGitInfo:
    """Git-related CI metadata."""

    branch: str | None = None  # Current branch name
    commit_sha: str | None = None  # Full commit SHA
    commit_short: str | None = None  # Short SHA (first 7-8 chars)
    tag: str | None = None  # Git tag if triggered by tag push
    default_branch: str | None = None  # Default branch (main/master)


@dataclass(frozen=True)
class CIPullRequest:
    """Pull/Merge request metadata."""

    number: str | None = None  # PR/MR number
    source_branch: str | None = None  # Source branch
    target_branch: str | None = None  # Target branch (base)
    url: str | None = None  # URL to the PR/MR

    @property
    def is_pr(self) -> bool:
        """True if this build was triggered by a pull/merge request."""
        return self.number is not None


@dataclass(frozen=True)
class CIBuildInfo:
    """Build/job identification."""

    build_id: str | None = None  # Build/run ID
    build_number: str | None = None  # Build number
    job_id: str | None = None  # Job ID
    job_name: str | None = None  # Job name
    pipeline_id: str | None = None  # Pipeline/workflow ID
    build_url: str | None = None  # URL to the build


@dataclass(frozen=True)
class CIRunnerInfo:
    """Runner/agent capabilities."""

    runner_name: str | None = None  # Runner name
    runner_os: str | None = None  # Runner OS (e.g., "Linux")
    runner_arch: str | None = None  # Runner architecture
    cpu_cores: int | None = None  # Available CPU cores
    has_docker: bool = False  # Docker available on runner
    has_gpu: bool = False  # GPU detected on runner
    workspace: str | None = None  # Workspace directory


@dataclass(frozen=True)
class CIInfo:
    """Complete CI/CD detection results.

    All fields are populated from environment variables -- no subprocess calls,
    no network I/O. Pure passive detection consistent with dekk's philosophy.
    """

    is_ci: bool  # True if running in any CI environment
    provider: CIProvider | None = None
    git: CIGitInfo = field(default_factory=CIGitInfo)
    pull_request: CIPullRequest = field(default_factory=CIPullRequest)
    build: CIBuildInfo = field(default_factory=CIBuildInfo)
    runner: CIRunnerInfo = field(default_factory=CIRunnerInfo)
    event_name: str | None = None  # Trigger event (push, pull_request, schedule, etc.)
    repository: str | None = None  # Repository slug (owner/repo)
    server_url: str | None = None  # CI server URL

    @property
    def is_pr_build(self) -> bool:
        """True if this build was triggered by a pull/merge request."""
        return self.pull_request.is_pr

    @property
    def is_tag_build(self) -> bool:
        """True if this build was triggered by a tag push."""
        return self.git.tag is not None

    @property
    def provider_name(self) -> str | None:
        """Short name of the CI provider, or None."""
        return self.provider.name if self.provider else None


class CIDetector:
    """Detect CI/CD environment, provider, and metadata.

    Reads only environment variables and filesystem markers. Never runs
    subprocesses. Never modifies state. Always succeeds (never raises).
    """

    # Provider detection order: most specific env vars first
    _PROVIDERS = [
        ("GITHUB_ACTIONS", "github_actions", "GitHub Actions"),
        ("GITLAB_CI", "gitlab_ci", "GitLab CI"),
        ("JENKINS_URL", "jenkins", "Jenkins"),
        ("CIRCLECI", "circleci", "CircleCI"),
        ("BUILDKITE", "buildkite", "Buildkite"),
        ("TRAVIS", "travis", "Travis CI"),
        ("AZURE_PIPELINES", "azure_pipelines", "Azure Pipelines"),  # TF_BUILD is also used
        ("TF_BUILD", "azure_pipelines", "Azure Pipelines"),
        ("BITBUCKET_PIPELINE_UUID", "bitbucket", "Bitbucket Pipelines"),
        ("TEAMCITY_VERSION", "teamcity", "TeamCity"),
        ("CODEBUILD_BUILD_ID", "aws_codebuild", "AWS CodeBuild"),
        ("DRONE", "drone", "Drone CI"),
        ("WOODPECKER_CI", "woodpecker", "Woodpecker CI"),
        ("HEROKU_TEST_RUN_ID", "heroku", "Heroku CI"),
    ]

    def detect(self) -> CIInfo:
        """Detect CI/CD environment.

        Always succeeds (never raises).

        Returns:
            CIInfo with detected CI/CD details. If not in CI, returns
            CIInfo(is_ci=False) with all other fields at defaults.
        """
        provider = self._detect_provider()

        if provider is None:
            # Check generic CI flag as fallback
            if not self._is_generic_ci():
                return CIInfo(is_ci=False)
            provider = CIProvider(name="unknown", display_name="Unknown CI")

        # Dispatch to provider-specific extraction
        extractors = {
            "github_actions": self._extract_github_actions,
            "gitlab_ci": self._extract_gitlab_ci,
            "jenkins": self._extract_jenkins,
            "circleci": self._extract_circleci,
            "buildkite": self._extract_buildkite,
            "travis": self._extract_travis,
            "azure_pipelines": self._extract_azure_pipelines,
            "bitbucket": self._extract_bitbucket,
        }

        extractor = extractors.get(provider.name, self._extract_generic)
        return extractor(provider)

    def _detect_provider(self) -> CIProvider | None:
        """Identify the CI provider from environment variables."""
        for env_var, name, display_name in self._PROVIDERS:
            if os.environ.get(env_var):
                return CIProvider(name=name, display_name=display_name)
        return None

    def _is_generic_ci(self) -> bool:
        """Check generic CI indicators."""
        return os.environ.get("CI", "").lower() in ("true", "1", "yes")

    def _detect_runner_capabilities(self) -> CIRunnerInfo:
        """Detect runner hardware/software capabilities."""
        cpu_cores = os.cpu_count()
        has_docker = shutil.which("docker") is not None
        has_gpu = self._detect_gpu()

        return CIRunnerInfo(
            runner_os=platform.system(),
            runner_arch=platform.machine(),
            cpu_cores=cpu_cores,
            has_docker=has_docker,
            has_gpu=has_gpu,
        )

    def _detect_gpu(self) -> bool:
        """Check for GPU availability via filesystem markers."""
        # NVIDIA
        if Path("/dev/nvidia0").exists() or Path("/proc/driver/nvidia").exists():
            return True
        # AMD ROCm
        if Path("/dev/kfd").exists():
            return True
        # Check environment hints
        if os.environ.get("NVIDIA_VISIBLE_DEVICES") or os.environ.get("CUDA_VISIBLE_DEVICES"):
            return True
        if os.environ.get("ROCR_VISIBLE_DEVICES") or os.environ.get("HIP_VISIBLE_DEVICES"):
            return True
        return False

    # ── Provider-specific extractors ──────────────────────────────────

    def _extract_github_actions(self, provider: CIProvider) -> CIInfo:
        """Extract GitHub Actions metadata."""
        env = os.environ
        ref = env.get("GITHUB_REF", "")
        sha = env.get("GITHUB_SHA")

        # Parse branch from ref
        branch = None
        tag = None
        if ref.startswith("refs/heads/"):
            branch = ref[len("refs/heads/"):]
        elif ref.startswith("refs/tags/"):
            tag = ref[len("refs/tags/"):]
        elif ref.startswith("refs/pull/"):
            # PR ref: refs/pull/123/merge
            branch = env.get("GITHUB_HEAD_REF")

        # PR info
        pr_number = None
        if ref.startswith("refs/pull/"):
            parts = ref.split("/")
            if len(parts) >= 3:
                pr_number = parts[2]

        runner = self._detect_runner_capabilities()
        runner = CIRunnerInfo(
            runner_name=env.get("RUNNER_NAME"),
            runner_os=env.get("RUNNER_OS", runner.runner_os),
            runner_arch=env.get("RUNNER_ARCH", runner.runner_arch),
            cpu_cores=runner.cpu_cores,
            has_docker=runner.has_docker,
            has_gpu=runner.has_gpu,
            workspace=env.get("GITHUB_WORKSPACE"),
        )

        server_url = env.get("GITHUB_SERVER_URL", "https://github.com")
        repo = env.get("GITHUB_REPOSITORY")
        run_id = env.get("GITHUB_RUN_ID")

        return CIInfo(
            is_ci=True,
            provider=provider,
            git=CIGitInfo(
                branch=branch or env.get("GITHUB_HEAD_REF"),
                commit_sha=sha,
                commit_short=sha[:7] if sha else None,
                tag=tag,
                default_branch=env.get("GITHUB_EVENT_NAME") == "push"
                and branch
                or None,
            ),
            pull_request=CIPullRequest(
                number=pr_number,
                source_branch=env.get("GITHUB_HEAD_REF"),
                target_branch=env.get("GITHUB_BASE_REF"),
                url=f"{server_url}/{repo}/pull/{pr_number}"
                if repo and pr_number
                else None,
            ),
            build=CIBuildInfo(
                build_id=run_id,
                build_number=env.get("GITHUB_RUN_NUMBER"),
                job_id=env.get("GITHUB_JOB"),
                job_name=env.get("GITHUB_JOB"),
                pipeline_id=env.get("GITHUB_WORKFLOW"),
                build_url=f"{server_url}/{repo}/actions/runs/{run_id}"
                if repo and run_id
                else None,
            ),
            runner=runner,
            event_name=env.get("GITHUB_EVENT_NAME"),
            repository=repo,
            server_url=server_url,
        )

    def _extract_gitlab_ci(self, provider: CIProvider) -> CIInfo:
        """Extract GitLab CI metadata."""
        env = os.environ
        sha = env.get("CI_COMMIT_SHA")
        mr_iid = env.get("CI_MERGE_REQUEST_IID")
        project_url = env.get("CI_PROJECT_URL")

        runner = self._detect_runner_capabilities()
        runner = CIRunnerInfo(
            runner_name=env.get("CI_RUNNER_DESCRIPTION"),
            runner_os=runner.runner_os,
            runner_arch=runner.runner_arch,
            cpu_cores=runner.cpu_cores,
            has_docker=runner.has_docker,
            has_gpu=runner.has_gpu,
            workspace=env.get("CI_PROJECT_DIR"),
        )

        return CIInfo(
            is_ci=True,
            provider=provider,
            git=CIGitInfo(
                branch=env.get("CI_COMMIT_BRANCH") or env.get("CI_COMMIT_REF_NAME"),
                commit_sha=sha,
                commit_short=env.get("CI_COMMIT_SHORT_SHA") or (sha[:8] if sha else None),
                tag=env.get("CI_COMMIT_TAG"),
                default_branch=env.get("CI_DEFAULT_BRANCH"),
            ),
            pull_request=CIPullRequest(
                number=mr_iid,
                source_branch=env.get("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"),
                target_branch=env.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME"),
                url=f"{project_url}/-/merge_requests/{mr_iid}"
                if project_url and mr_iid
                else None,
            ),
            build=CIBuildInfo(
                build_id=env.get("CI_JOB_ID"),
                build_number=env.get("CI_PIPELINE_IID"),
                job_id=env.get("CI_JOB_ID"),
                job_name=env.get("CI_JOB_NAME"),
                pipeline_id=env.get("CI_PIPELINE_ID"),
                build_url=env.get("CI_JOB_URL"),
            ),
            runner=runner,
            event_name=env.get("CI_PIPELINE_SOURCE"),
            repository=env.get("CI_PROJECT_PATH"),
            server_url=env.get("CI_SERVER_URL"),
        )

    def _extract_jenkins(self, provider: CIProvider) -> CIInfo:
        """Extract Jenkins metadata."""
        env = os.environ
        sha = env.get("GIT_COMMIT")

        runner = self._detect_runner_capabilities()
        runner = CIRunnerInfo(
            runner_name=env.get("NODE_NAME"),
            runner_os=runner.runner_os,
            runner_arch=runner.runner_arch,
            cpu_cores=runner.cpu_cores,
            has_docker=runner.has_docker,
            has_gpu=runner.has_gpu,
            workspace=env.get("WORKSPACE"),
        )

        return CIInfo(
            is_ci=True,
            provider=provider,
            git=CIGitInfo(
                branch=env.get("GIT_BRANCH") or env.get("BRANCH_NAME"),
                commit_sha=sha,
                commit_short=sha[:7] if sha else None,
            ),
            pull_request=CIPullRequest(
                number=env.get("CHANGE_ID"),
                source_branch=env.get("CHANGE_BRANCH"),
                target_branch=env.get("CHANGE_TARGET"),
                url=env.get("CHANGE_URL"),
            ),
            build=CIBuildInfo(
                build_id=env.get("BUILD_ID"),
                build_number=env.get("BUILD_NUMBER"),
                job_id=env.get("BUILD_TAG"),
                job_name=env.get("JOB_NAME"),
                build_url=env.get("BUILD_URL"),
            ),
            runner=runner,
            repository=env.get("JOB_NAME"),
            server_url=env.get("JENKINS_URL"),
        )

    def _extract_circleci(self, provider: CIProvider) -> CIInfo:
        """Extract CircleCI metadata."""
        env = os.environ
        sha = env.get("CIRCLE_SHA1")
        pr_number = env.get("CIRCLE_PR_NUMBER")
        pr_url = env.get("CIRCLE_PULL_REQUEST")

        runner = self._detect_runner_capabilities()
        runner = CIRunnerInfo(
            runner_name=env.get("CIRCLE_NODE_INDEX"),
            runner_os=runner.runner_os,
            runner_arch=runner.runner_arch,
            cpu_cores=runner.cpu_cores,
            has_docker=runner.has_docker,
            has_gpu=runner.has_gpu,
            workspace=env.get("CIRCLE_WORKING_DIRECTORY"),
        )

        return CIInfo(
            is_ci=True,
            provider=provider,
            git=CIGitInfo(
                branch=env.get("CIRCLE_BRANCH"),
                commit_sha=sha,
                commit_short=sha[:7] if sha else None,
                tag=env.get("CIRCLE_TAG"),
            ),
            pull_request=CIPullRequest(
                number=pr_number,
                url=pr_url,
            ),
            build=CIBuildInfo(
                build_id=env.get("CIRCLE_BUILD_NUM"),
                build_number=env.get("CIRCLE_BUILD_NUM"),
                job_id=env.get("CIRCLE_JOB"),
                job_name=env.get("CIRCLE_JOB"),
                pipeline_id=env.get("CIRCLE_PIPELINE_ID"),
                build_url=env.get("CIRCLE_BUILD_URL"),
            ),
            runner=runner,
            repository=f"{env.get('CIRCLE_PROJECT_USERNAME', '')}/{env.get('CIRCLE_PROJECT_REPONAME', '')}"
            if env.get("CIRCLE_PROJECT_USERNAME")
            else None,
        )

    def _extract_buildkite(self, provider: CIProvider) -> CIInfo:
        """Extract Buildkite metadata."""
        env = os.environ
        sha = env.get("BUILDKITE_COMMIT")

        runner = self._detect_runner_capabilities()
        runner = CIRunnerInfo(
            runner_name=env.get("BUILDKITE_AGENT_NAME"),
            runner_os=runner.runner_os,
            runner_arch=runner.runner_arch,
            cpu_cores=runner.cpu_cores,
            has_docker=runner.has_docker,
            has_gpu=runner.has_gpu,
            workspace=env.get("BUILDKITE_BUILD_CHECKOUT_PATH"),
        )

        pr_number = env.get("BUILDKITE_PULL_REQUEST")
        if pr_number == "false":
            pr_number = None

        return CIInfo(
            is_ci=True,
            provider=provider,
            git=CIGitInfo(
                branch=env.get("BUILDKITE_BRANCH"),
                commit_sha=sha,
                commit_short=sha[:7] if sha else None,
                tag=env.get("BUILDKITE_TAG"),
            ),
            pull_request=CIPullRequest(
                number=pr_number,
                source_branch=env.get("BUILDKITE_BRANCH") if pr_number else None,
                target_branch=env.get("BUILDKITE_PULL_REQUEST_BASE_BRANCH"),
            ),
            build=CIBuildInfo(
                build_id=env.get("BUILDKITE_BUILD_ID"),
                build_number=env.get("BUILDKITE_BUILD_NUMBER"),
                job_id=env.get("BUILDKITE_JOB_ID"),
                pipeline_id=env.get("BUILDKITE_PIPELINE_SLUG"),
                build_url=env.get("BUILDKITE_BUILD_URL"),
            ),
            runner=runner,
            repository=env.get("BUILDKITE_REPO"),
        )

    def _extract_travis(self, provider: CIProvider) -> CIInfo:
        """Extract Travis CI metadata."""
        env = os.environ
        sha = env.get("TRAVIS_COMMIT")
        pr_number = env.get("TRAVIS_PULL_REQUEST")
        if pr_number == "false":
            pr_number = None

        runner = self._detect_runner_capabilities()
        runner = CIRunnerInfo(
            runner_os=env.get("TRAVIS_OS_NAME", runner.runner_os),
            runner_arch=env.get("TRAVIS_CPU_ARCH", runner.runner_arch),
            cpu_cores=runner.cpu_cores,
            has_docker=runner.has_docker,
            has_gpu=runner.has_gpu,
            workspace=env.get("TRAVIS_BUILD_DIR"),
        )

        return CIInfo(
            is_ci=True,
            provider=provider,
            git=CIGitInfo(
                branch=env.get("TRAVIS_BRANCH"),
                commit_sha=sha,
                commit_short=sha[:7] if sha else None,
                tag=env.get("TRAVIS_TAG"),
            ),
            pull_request=CIPullRequest(
                number=pr_number,
                source_branch=env.get("TRAVIS_PULL_REQUEST_BRANCH"),
            ),
            build=CIBuildInfo(
                build_id=env.get("TRAVIS_BUILD_ID"),
                build_number=env.get("TRAVIS_BUILD_NUMBER"),
                job_id=env.get("TRAVIS_JOB_ID"),
                job_name=env.get("TRAVIS_JOB_NAME"),
                build_url=env.get("TRAVIS_BUILD_WEB_URL"),
            ),
            runner=runner,
            repository=env.get("TRAVIS_REPO_SLUG"),
        )

    def _extract_azure_pipelines(self, provider: CIProvider) -> CIInfo:
        """Extract Azure Pipelines metadata."""
        env = os.environ
        sha = env.get("BUILD_SOURCEVERSION")
        branch = env.get("BUILD_SOURCEBRANCH", "")

        # Parse branch from refs/heads/... format
        parsed_branch = None
        tag = None
        if branch.startswith("refs/heads/"):
            parsed_branch = branch[len("refs/heads/"):]
        elif branch.startswith("refs/tags/"):
            tag = branch[len("refs/tags/"):]
        else:
            parsed_branch = branch or None

        pr_number = env.get("SYSTEM_PULLREQUEST_PULLREQUESTID")

        runner = self._detect_runner_capabilities()
        runner = CIRunnerInfo(
            runner_name=env.get("AGENT_NAME"),
            runner_os=env.get("AGENT_OS", runner.runner_os),
            runner_arch=runner.runner_arch,
            cpu_cores=runner.cpu_cores,
            has_docker=runner.has_docker,
            has_gpu=runner.has_gpu,
            workspace=env.get("BUILD_SOURCESDIRECTORY"),
        )

        collection_uri = env.get("SYSTEM_COLLECTIONURI", "")
        project = env.get("SYSTEM_TEAMPROJECT", "")
        build_id = env.get("BUILD_BUILDID")

        return CIInfo(
            is_ci=True,
            provider=provider,
            git=CIGitInfo(
                branch=parsed_branch or env.get("BUILD_SOURCEBRANCHNAME"),
                commit_sha=sha,
                commit_short=sha[:7] if sha else None,
                tag=tag,
            ),
            pull_request=CIPullRequest(
                number=pr_number,
                source_branch=env.get("SYSTEM_PULLREQUEST_SOURCEBRANCH"),
                target_branch=env.get("SYSTEM_PULLREQUEST_TARGETBRANCH"),
            ),
            build=CIBuildInfo(
                build_id=build_id,
                build_number=env.get("BUILD_BUILDNUMBER"),
                job_id=env.get("SYSTEM_JOBID"),
                job_name=env.get("SYSTEM_JOBDISPLAYNAME"),
                pipeline_id=env.get("SYSTEM_DEFINITIONID"),
                build_url=f"{collection_uri}{project}/_build/results?buildId={build_id}"
                if collection_uri and project and build_id
                else None,
            ),
            runner=runner,
            repository=env.get("BUILD_REPOSITORY_NAME"),
            server_url=collection_uri or None,
        )

    def _extract_bitbucket(self, provider: CIProvider) -> CIInfo:
        """Extract Bitbucket Pipelines metadata."""
        env = os.environ
        sha = env.get("BITBUCKET_COMMIT")
        pr_id = env.get("BITBUCKET_PR_ID")

        runner = self._detect_runner_capabilities()
        runner = CIRunnerInfo(
            runner_os=runner.runner_os,
            runner_arch=runner.runner_arch,
            cpu_cores=runner.cpu_cores,
            has_docker=runner.has_docker,
            has_gpu=runner.has_gpu,
            workspace=env.get("BITBUCKET_CLONE_DIR"),
        )

        return CIInfo(
            is_ci=True,
            provider=provider,
            git=CIGitInfo(
                branch=env.get("BITBUCKET_BRANCH"),
                commit_sha=sha,
                commit_short=sha[:7] if sha else None,
                tag=env.get("BITBUCKET_TAG"),
            ),
            pull_request=CIPullRequest(
                number=pr_id,
                source_branch=env.get("BITBUCKET_BRANCH") if pr_id else None,
                target_branch=env.get("BITBUCKET_PR_DESTINATION_BRANCH"),
            ),
            build=CIBuildInfo(
                build_id=env.get("BITBUCKET_BUILD_NUMBER"),
                build_number=env.get("BITBUCKET_BUILD_NUMBER"),
                pipeline_id=env.get("BITBUCKET_PIPELINE_UUID"),
            ),
            runner=runner,
            repository=env.get("BITBUCKET_REPO_FULL_NAME"),
        )

    def _extract_generic(self, provider: CIProvider) -> CIInfo:
        """Fallback extractor for unknown/generic CI."""
        runner = self._detect_runner_capabilities()
        return CIInfo(
            is_ci=True,
            provider=provider,
            runner=runner,
        )


# ---------------------------------------------------------------------------
# CI Build Hints
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CIBuildHints:
    """Build-system-agnostic hints for CI environments.

    All fields are advisory. Consumers decide how to map these to
    their specific build system (e.g., ``max_jobs`` -> ``--jobs=N`` in Cargo,
    ``-j N`` in Make, ``-parallel N`` in CMake).
    """

    # Parallelism
    max_jobs: int | None = None  # Recommended max parallel jobs (None = no cap)
    max_test_workers: int | None = None  # Recommended max test parallelism

    # Incremental builds
    incremental: bool = True  # Whether incremental builds are recommended

    # Output
    use_color: bool = False  # Whether color output is safe
    verbose: bool = False  # Whether verbose output is recommended
    ci_output: bool = False  # True = suppress progress bars, spinners, etc.

    # Environment variable recommendations (build-system-agnostic)
    env_hints: dict[str, str] = field(default_factory=dict)

    # Providers known to support ANSI color
    _COLOR_PROVIDERS: frozenset[str] = frozenset(
        {"github_actions", "gitlab_ci", "buildkite", "circleci"}
    )


class CIBuildAdvisor:
    """Produce build hints from a CIInfo detection result.

    Stateless: takes CIInfo, returns CIBuildHints. No I/O, no side effects.
    """

    # Cores threshold for "constrained" runner
    SMALL_RUNNER_CORES = 2
    MEDIUM_RUNNER_CORES = 4

    def __init__(self, ci: CIInfo) -> None:
        self._ci = ci

    def advise(self) -> CIBuildHints:
        """Compute build hints for the detected CI environment.

        Local (non-CI) environments get permissive defaults (incremental on,
        no parallelism cap, no special output settings).

        CI environments get:
        - Parallelism capped on small runners (<=2 cores -> 1 job, <=4 -> cores)
        - Incremental builds disabled (CI builds are clean builds)
        - Verbose output enabled
        - Color enabled for providers that support ANSI
        - CI output mode (suppress progress bars)
        """
        if not self._ci.is_ci:
            return CIBuildHints()

        max_jobs, max_test_workers = self._compute_parallelism()
        use_color = self._supports_color()
        env_hints = self._compute_env_hints(use_color)

        return CIBuildHints(
            max_jobs=max_jobs,
            max_test_workers=max_test_workers,
            incremental=False,
            use_color=use_color,
            verbose=True,
            ci_output=True,
            env_hints=env_hints,
        )

    def _compute_parallelism(self) -> tuple[int | None, int | None]:
        """Determine parallelism caps based on runner cores."""
        cores = self._ci.runner.cpu_cores
        if cores is None:
            return None, None

        if cores <= self.SMALL_RUNNER_CORES:
            return 1, 1
        if cores <= self.MEDIUM_RUNNER_CORES:
            return cores, cores

        # Large runners: no cap needed
        return None, None

    def _supports_color(self) -> bool:
        """Check if the CI provider supports ANSI color output."""
        if self._ci.provider is None:
            return False
        return self._ci.provider.name in CIBuildHints._COLOR_PROVIDERS

    def _compute_env_hints(self, use_color: bool) -> dict[str, str]:
        """Compute recommended environment variable overrides."""
        hints: dict[str, str] = {}

        if use_color:
            hints["FORCE_COLOR"] = "1"

        return hints
