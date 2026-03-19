"""Tests for CI/CD provider detection."""

import os

import pytest

from sniff_cli.ci import (
    CIBuildInfo,
    CIDetector,
    CIGitInfo,
    CIInfo,
    CIPullRequest,
    CIProvider,
    CIRunnerInfo,
)


@pytest.fixture
def detector():
    return CIDetector()


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all CI-related env vars so detection starts clean."""
    ci_vars = [
        "CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL", "CIRCLECI",
        "BUILDKITE", "TRAVIS", "TF_BUILD", "AZURE_PIPELINES",
        "BITBUCKET_PIPELINE_UUID", "TEAMCITY_VERSION", "CODEBUILD_BUILD_ID",
        "DRONE", "WOODPECKER_CI", "HEROKU_TEST_RUN_ID",
    ]
    for var in ci_vars:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestCIDetectorNotCI:
    """Tests when NOT running in CI."""

    def test_not_ci_returns_false(self, detector, clean_env):
        info = detector.detect()
        assert not info.is_ci
        assert info.provider is None

    def test_not_ci_defaults(self, detector, clean_env):
        info = detector.detect()
        assert not info.is_pr_build
        assert not info.is_tag_build
        assert info.provider_name is None


class TestCIDetectorGenericCI:
    """Tests for generic CI=true detection."""

    def test_generic_ci_true(self, detector, clean_env):
        clean_env.setenv("CI", "true")
        info = detector.detect()
        assert info.is_ci
        assert info.provider is not None
        assert info.provider.name == "unknown"

    def test_generic_ci_1(self, detector, clean_env):
        clean_env.setenv("CI", "1")
        info = detector.detect()
        assert info.is_ci

    def test_generic_ci_yes(self, detector, clean_env):
        clean_env.setenv("CI", "yes")
        info = detector.detect()
        assert info.is_ci

    def test_generic_ci_false_string(self, detector, clean_env):
        clean_env.setenv("CI", "false")
        info = detector.detect()
        assert not info.is_ci


class TestGitHubActions:
    """Tests for GitHub Actions detection."""

    @pytest.fixture
    def gh_env(self, clean_env):
        """Set up minimal GitHub Actions environment."""
        clean_env.setenv("GITHUB_ACTIONS", "true")
        clean_env.setenv("CI", "true")
        return clean_env

    def test_provider_detected(self, detector, gh_env):
        info = detector.detect()
        assert info.is_ci
        assert info.provider_name == "github_actions"
        assert info.provider.display_name == "GitHub Actions"

    def test_push_event(self, detector, gh_env):
        gh_env.setenv("GITHUB_REF", "refs/heads/main")
        gh_env.setenv("GITHUB_SHA", "abc1234567890def")
        gh_env.setenv("GITHUB_EVENT_NAME", "push")
        gh_env.setenv("GITHUB_REPOSITORY", "owner/repo")

        info = detector.detect()
        assert info.git.branch == "main"
        assert info.git.commit_sha == "abc1234567890def"
        assert info.git.commit_short == "abc1234"
        assert info.git.tag is None
        assert not info.is_pr_build
        assert not info.is_tag_build
        assert info.event_name == "push"
        assert info.repository == "owner/repo"

    def test_tag_event(self, detector, gh_env):
        gh_env.setenv("GITHUB_REF", "refs/tags/v1.2.3")
        gh_env.setenv("GITHUB_SHA", "deadbeef1234567")

        info = detector.detect()
        assert info.git.tag == "v1.2.3"
        assert info.is_tag_build
        assert info.git.branch is None

    def test_pull_request_event(self, detector, gh_env):
        gh_env.setenv("GITHUB_REF", "refs/pull/42/merge")
        gh_env.setenv("GITHUB_SHA", "abcdef1234567")
        gh_env.setenv("GITHUB_HEAD_REF", "feature/my-branch")
        gh_env.setenv("GITHUB_BASE_REF", "main")
        gh_env.setenv("GITHUB_EVENT_NAME", "pull_request")
        gh_env.setenv("GITHUB_REPOSITORY", "owner/repo")
        gh_env.setenv("GITHUB_SERVER_URL", "https://github.com")

        info = detector.detect()
        assert info.is_pr_build
        assert info.pull_request.number == "42"
        assert info.pull_request.source_branch == "feature/my-branch"
        assert info.pull_request.target_branch == "main"
        assert info.pull_request.url == "https://github.com/owner/repo/pull/42"
        assert info.git.branch == "feature/my-branch"

    def test_build_info(self, detector, gh_env):
        gh_env.setenv("GITHUB_RUN_ID", "12345")
        gh_env.setenv("GITHUB_RUN_NUMBER", "7")
        gh_env.setenv("GITHUB_JOB", "test")
        gh_env.setenv("GITHUB_WORKFLOW", "CI")
        gh_env.setenv("GITHUB_REPOSITORY", "owner/repo")
        gh_env.setenv("GITHUB_SERVER_URL", "https://github.com")

        info = detector.detect()
        assert info.build.build_id == "12345"
        assert info.build.build_number == "7"
        assert info.build.job_name == "test"
        assert info.build.pipeline_id == "CI"
        assert info.build.build_url == "https://github.com/owner/repo/actions/runs/12345"

    def test_runner_info(self, detector, gh_env):
        gh_env.setenv("RUNNER_NAME", "GitHub Actions 2")
        gh_env.setenv("RUNNER_OS", "Linux")
        gh_env.setenv("RUNNER_ARCH", "X64")
        gh_env.setenv("GITHUB_WORKSPACE", "/home/runner/work/repo/repo")

        info = detector.detect()
        assert info.runner.runner_name == "GitHub Actions 2"
        assert info.runner.runner_os == "Linux"
        assert info.runner.runner_arch == "X64"
        assert info.runner.workspace == "/home/runner/work/repo/repo"
        assert info.runner.cpu_cores is not None


class TestGitLabCI:
    """Tests for GitLab CI detection."""

    @pytest.fixture
    def gl_env(self, clean_env):
        clean_env.setenv("GITLAB_CI", "true")
        clean_env.setenv("CI", "true")
        return clean_env

    def test_provider_detected(self, detector, gl_env):
        info = detector.detect()
        assert info.provider_name == "gitlab_ci"
        assert info.provider.display_name == "GitLab CI"

    def test_branch_build(self, detector, gl_env):
        gl_env.setenv("CI_COMMIT_BRANCH", "develop")
        gl_env.setenv("CI_COMMIT_SHA", "abc123def456")
        gl_env.setenv("CI_COMMIT_SHORT_SHA", "abc123de")
        gl_env.setenv("CI_DEFAULT_BRANCH", "main")

        info = detector.detect()
        assert info.git.branch == "develop"
        assert info.git.commit_sha == "abc123def456"
        assert info.git.commit_short == "abc123de"
        assert info.git.default_branch == "main"

    def test_merge_request(self, detector, gl_env):
        gl_env.setenv("CI_MERGE_REQUEST_IID", "99")
        gl_env.setenv("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "feature/x")
        gl_env.setenv("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "main")
        gl_env.setenv("CI_PROJECT_URL", "https://gitlab.com/group/repo")

        info = detector.detect()
        assert info.is_pr_build
        assert info.pull_request.number == "99"
        assert info.pull_request.source_branch == "feature/x"
        assert info.pull_request.target_branch == "main"
        assert info.pull_request.url == "https://gitlab.com/group/repo/-/merge_requests/99"

    def test_tag_build(self, detector, gl_env):
        gl_env.setenv("CI_COMMIT_TAG", "v2.0.0")

        info = detector.detect()
        assert info.is_tag_build
        assert info.git.tag == "v2.0.0"

    def test_pipeline_info(self, detector, gl_env):
        gl_env.setenv("CI_PIPELINE_ID", "1001")
        gl_env.setenv("CI_PIPELINE_IID", "42")
        gl_env.setenv("CI_JOB_ID", "5555")
        gl_env.setenv("CI_JOB_NAME", "test:unit")
        gl_env.setenv("CI_JOB_URL", "https://gitlab.com/group/repo/-/jobs/5555")
        gl_env.setenv("CI_PIPELINE_SOURCE", "merge_request_event")
        gl_env.setenv("CI_PROJECT_PATH", "group/repo")
        gl_env.setenv("CI_SERVER_URL", "https://gitlab.com")

        info = detector.detect()
        assert info.build.pipeline_id == "1001"
        assert info.build.build_number == "42"
        assert info.build.job_id == "5555"
        assert info.build.job_name == "test:unit"
        assert info.build.build_url == "https://gitlab.com/group/repo/-/jobs/5555"
        assert info.event_name == "merge_request_event"
        assert info.repository == "group/repo"
        assert info.server_url == "https://gitlab.com"


class TestJenkins:
    """Tests for Jenkins detection."""

    @pytest.fixture
    def jenkins_env(self, clean_env):
        clean_env.setenv("JENKINS_URL", "https://jenkins.example.com/")
        return clean_env

    def test_provider_detected(self, detector, jenkins_env):
        info = detector.detect()
        assert info.provider_name == "jenkins"

    def test_build_metadata(self, detector, jenkins_env):
        jenkins_env.setenv("GIT_BRANCH", "origin/main")
        jenkins_env.setenv("GIT_COMMIT", "aabbccdd11223344")
        jenkins_env.setenv("BUILD_ID", "100")
        jenkins_env.setenv("BUILD_NUMBER", "100")
        jenkins_env.setenv("BUILD_URL", "https://jenkins.example.com/job/test/100/")
        jenkins_env.setenv("JOB_NAME", "my-project/main")
        jenkins_env.setenv("NODE_NAME", "linux-agent-1")
        jenkins_env.setenv("WORKSPACE", "/var/jenkins/workspace/my-project")

        info = detector.detect()
        assert info.git.branch == "origin/main"
        assert info.git.commit_sha == "aabbccdd11223344"
        assert info.build.build_number == "100"
        assert info.build.build_url == "https://jenkins.example.com/job/test/100/"
        assert info.runner.runner_name == "linux-agent-1"
        assert info.runner.workspace == "/var/jenkins/workspace/my-project"

    def test_jenkins_pr(self, detector, jenkins_env):
        jenkins_env.setenv("CHANGE_ID", "15")
        jenkins_env.setenv("CHANGE_BRANCH", "feature/login")
        jenkins_env.setenv("CHANGE_TARGET", "main")
        jenkins_env.setenv("CHANGE_URL", "https://github.com/org/repo/pull/15")

        info = detector.detect()
        assert info.is_pr_build
        assert info.pull_request.number == "15"
        assert info.pull_request.source_branch == "feature/login"
        assert info.pull_request.target_branch == "main"


class TestCircleCI:
    """Tests for CircleCI detection."""

    @pytest.fixture
    def circle_env(self, clean_env):
        clean_env.setenv("CIRCLECI", "true")
        clean_env.setenv("CI", "true")
        return clean_env

    def test_provider_detected(self, detector, circle_env):
        info = detector.detect()
        assert info.provider_name == "circleci"

    def test_build_metadata(self, detector, circle_env):
        circle_env.setenv("CIRCLE_BRANCH", "develop")
        circle_env.setenv("CIRCLE_SHA1", "deadbeef12345678")
        circle_env.setenv("CIRCLE_BUILD_NUM", "42")
        circle_env.setenv("CIRCLE_JOB", "test")
        circle_env.setenv("CIRCLE_PIPELINE_ID", "pipe-001")
        circle_env.setenv("CIRCLE_BUILD_URL", "https://circleci.com/build/42")
        circle_env.setenv("CIRCLE_PROJECT_USERNAME", "owner")
        circle_env.setenv("CIRCLE_PROJECT_REPONAME", "repo")

        info = detector.detect()
        assert info.git.branch == "develop"
        assert info.git.commit_sha == "deadbeef12345678"
        assert info.build.build_number == "42"
        assert info.build.job_name == "test"
        assert info.repository == "owner/repo"

    def test_circle_pr(self, detector, circle_env):
        circle_env.setenv("CIRCLE_PR_NUMBER", "88")
        circle_env.setenv("CIRCLE_PULL_REQUEST", "https://github.com/org/repo/pull/88")

        info = detector.detect()
        assert info.is_pr_build
        assert info.pull_request.number == "88"
        assert info.pull_request.url == "https://github.com/org/repo/pull/88"

    def test_circle_tag(self, detector, circle_env):
        circle_env.setenv("CIRCLE_TAG", "v3.0.0")

        info = detector.detect()
        assert info.is_tag_build
        assert info.git.tag == "v3.0.0"


class TestAzurePipelines:
    """Tests for Azure Pipelines detection."""

    @pytest.fixture
    def azure_env(self, clean_env):
        clean_env.setenv("TF_BUILD", "True")
        return clean_env

    def test_provider_detected(self, detector, azure_env):
        info = detector.detect()
        assert info.provider_name == "azure_pipelines"

    def test_branch_build(self, detector, azure_env):
        azure_env.setenv("BUILD_SOURCEBRANCH", "refs/heads/main")
        azure_env.setenv("BUILD_SOURCEVERSION", "abcdef1234567890")
        azure_env.setenv("BUILD_SOURCEBRANCHNAME", "main")

        info = detector.detect()
        assert info.git.branch == "main"
        assert info.git.commit_sha == "abcdef1234567890"

    def test_tag_build(self, detector, azure_env):
        azure_env.setenv("BUILD_SOURCEBRANCH", "refs/tags/v1.0.0")

        info = detector.detect()
        assert info.git.tag == "v1.0.0"
        assert info.is_tag_build

    def test_pr_build(self, detector, azure_env):
        azure_env.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "77")
        azure_env.setenv("SYSTEM_PULLREQUEST_SOURCEBRANCH", "feature/x")
        azure_env.setenv("SYSTEM_PULLREQUEST_TARGETBRANCH", "main")

        info = detector.detect()
        assert info.is_pr_build
        assert info.pull_request.number == "77"


class TestBitbucket:
    """Tests for Bitbucket Pipelines detection."""

    @pytest.fixture
    def bb_env(self, clean_env):
        clean_env.setenv("BITBUCKET_PIPELINE_UUID", "{uuid-123}")
        return clean_env

    def test_provider_detected(self, detector, bb_env):
        info = detector.detect()
        assert info.provider_name == "bitbucket"

    def test_branch_build(self, detector, bb_env):
        bb_env.setenv("BITBUCKET_BRANCH", "develop")
        bb_env.setenv("BITBUCKET_COMMIT", "1234abcd5678efgh")
        bb_env.setenv("BITBUCKET_REPO_FULL_NAME", "team/repo")

        info = detector.detect()
        assert info.git.branch == "develop"
        assert info.git.commit_sha == "1234abcd5678efgh"
        assert info.repository == "team/repo"

    def test_pr_build(self, detector, bb_env):
        bb_env.setenv("BITBUCKET_PR_ID", "55")
        bb_env.setenv("BITBUCKET_BRANCH", "feature/y")
        bb_env.setenv("BITBUCKET_PR_DESTINATION_BRANCH", "main")

        info = detector.detect()
        assert info.is_pr_build
        assert info.pull_request.number == "55"
        assert info.pull_request.source_branch == "feature/y"
        assert info.pull_request.target_branch == "main"


class TestCIInfoProperties:
    """Test CIInfo dataclass properties."""

    def test_is_pr_build(self):
        info = CIInfo(
            is_ci=True,
            pull_request=CIPullRequest(number="42"),
        )
        assert info.is_pr_build

    def test_not_pr_build(self):
        info = CIInfo(is_ci=True)
        assert not info.is_pr_build

    def test_is_tag_build(self):
        info = CIInfo(
            is_ci=True,
            git=CIGitInfo(tag="v1.0.0"),
        )
        assert info.is_tag_build

    def test_not_tag_build(self):
        info = CIInfo(is_ci=True)
        assert not info.is_tag_build

    def test_provider_name_present(self):
        info = CIInfo(
            is_ci=True,
            provider=CIProvider(name="github_actions", display_name="GitHub Actions"),
        )
        assert info.provider_name == "github_actions"

    def test_provider_name_absent(self):
        info = CIInfo(is_ci=False)
        assert info.provider_name is None


class TestRunnerCapabilities:
    """Tests for runner capability detection."""

    def test_cpu_cores_detected(self, detector, clean_env):
        clean_env.setenv("GITHUB_ACTIONS", "true")
        info = detector.detect()
        assert info.runner.cpu_cores is not None
        assert info.runner.cpu_cores > 0

    def test_gpu_detection_via_env(self, detector, clean_env, monkeypatch):
        clean_env.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
        info = detector.detect()
        assert info.runner.has_gpu

    def test_gpu_detection_via_rocm_env(self, detector, clean_env, monkeypatch):
        clean_env.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("ROCR_VISIBLE_DEVICES", "0")
        info = detector.detect()
        assert info.runner.has_gpu


class TestProviderPrecedence:
    """Test that specific providers take precedence over generic CI."""

    def test_github_over_generic(self, detector, clean_env):
        clean_env.setenv("CI", "true")
        clean_env.setenv("GITHUB_ACTIONS", "true")
        info = detector.detect()
        assert info.provider_name == "github_actions"

    def test_gitlab_over_generic(self, detector, clean_env):
        clean_env.setenv("CI", "true")
        clean_env.setenv("GITLAB_CI", "true")
        info = detector.detect()
        assert info.provider_name == "gitlab_ci"
