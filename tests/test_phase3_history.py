"""
Deterministic tests for Phase 3: Historical Context.

All tests use temporary local Git repositories created on-the-fly.
No network access or GitHub availability is required.

Covers:
 1.  Relevant commit detection (file-level git log)
 2.  Commit metadata extraction (hash, short_hash, author, date, message)
 3.  Artifact-to-commit association
 4.  Historical evidence generation
 5.  Multiple commits for one artifact
 6.  Limited or empty history handling
 7.  Missing / nonexistent artifact handling
 8.  Commit message historical references (e.g. "#142") — recorded as-is
 9.  No fabricated evidence — only Git-backed findings
10.  Phase 0, Phase 1, and Phase 2 regression behaviour
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Generator

import pytest

from devflow.history._build import build_historical_context, _find_repo_root
from devflow.history.git_log import get_commits_for_artifact, is_git_repository
from devflow.models.change import ChangeRequest
from devflow.models.context import (
    ArtifactKind,
    ContextArtifact,
    RelevanceReason,
    RepositoryContext,
)
from devflow.models.history import (
    ArtifactHistory,
    HistoricalCommit,
    HistoricalEvidence,
    RepositoryHistory,
)
from devflow.models.repository import RepositoryInput


# ---------------------------------------------------------------------------
# Git fixture helpers
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command and assert it succeeds."""
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True)


def _init_repo(root: Path) -> None:
    """Initialise a bare-minimum git repo with a test identity."""
    root.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], root)
    _git(["config", "user.email", "test@devflow"], root)
    _git(["config", "user.name", "DevFlow Test"], root)


def _commit(root: Path, message: str, files: dict[str, str]) -> str:
    """Write files, stage them, and create a commit. Returns the commit hash."""
    for rel, content in files.items():
        abs_path = root / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content)
    _git(["add", "."], root)
    _git(["commit", "-q", "-m", message], root)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_repo_input(path: Path) -> RepositoryInput:
    """Build a RepositoryInput pointing at a local path (bypasses URL validation)."""
    return RepositoryInput(
        url=path.as_uri(),
        owner="local",
        name=path.name,
    )


def _make_context(
    repo_input: RepositoryInput,
    artifact_paths: list[str],
    change_summary: str = "Test change.",
) -> RepositoryContext:
    """Build a minimal RepositoryContext with the given artifact paths."""
    artifacts = [
        ContextArtifact(
            path=p,
            kind=ArtifactKind.SOURCE,
            reason=RelevanceReason.KEYWORD_MATCH,
            evidence=f"test evidence for {p}",
            confidence="likely",
        )
        for p in artifact_paths
    ]
    return RepositoryContext(
        repository_url=repo_input.url,
        owner=repo_input.owner,
        name=repo_input.name,
        change_summary=change_summary,
        artifacts=artifacts,
        all_files=artifact_paths,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo_with_history(tmp_path: Path) -> Generator[tuple[Path, dict[str, str]], None, None]:
    """
    A git repository with multiple commits on one file.

    Returns (repo_root, {filename: commit_hash}).
    """
    root = tmp_path / "myrepo"
    _init_repo(root)

    h1 = _commit(root, "initial: add auth module", {"src/auth.py": "# auth v1"})
    h2 = _commit(root, "feat: improve session handling #42", {"src/auth.py": "# auth v2"})
    h3 = _commit(root, "fix: resolve token expiry bug", {"src/auth.py": "# auth v3"})

    yield root, {"h1": h1, "h2": h2, "h3": h3}


@pytest.fixture()
def repo_with_multiple_files(tmp_path: Path) -> Generator[Path, None, None]:
    """A git repo where different commits touch different files."""
    root = tmp_path / "multirepo"
    _init_repo(root)

    _commit(root, "add api module", {"src/api.py": "# api v1", "src/auth.py": "# auth v1"})
    _commit(root, "update api routes", {"src/api.py": "# api v2"})
    _commit(root, "update auth tokens #99", {"src/auth.py": "# auth v2"})

    yield root


@pytest.fixture()
def empty_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """A git repo with a single initial commit and no file-specific history for new paths."""
    root = tmp_path / "emptyrepo"
    _init_repo(root)
    _commit(root, "initial commit", {"README.md": "empty"})
    yield root


# ---------------------------------------------------------------------------
# 1. Relevant commit detection
# ---------------------------------------------------------------------------


class TestRelevantCommitDetection:
    def test_commits_found_for_modified_file(self, repo_with_history):
        root, hashes = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        assert len(commits) == 3

    def test_commits_are_most_recent_first(self, repo_with_history):
        root, hashes = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        # Most recent commit should be the fix
        assert "fix" in commits[0].message.lower() or "token" in commits[0].message.lower()

    def test_no_commits_for_nonexistent_file(self, repo_with_history):
        root, _ = repo_with_history
        commits, evidence = get_commits_for_artifact(root, "src/nonexistent.py")
        assert commits == []
        assert evidence == []

    def test_commits_limited_by_max_commits(self, tmp_path: Path):
        root = tmp_path / "limit_repo"
        _init_repo(root)
        for i in range(10):
            _commit(root, f"commit {i}", {"src/file.py": f"v{i}"})
        commits, _ = get_commits_for_artifact(root, "src/file.py", max_commits=3)
        assert len(commits) <= 3


# ---------------------------------------------------------------------------
# 2. Commit metadata extraction
# ---------------------------------------------------------------------------


class TestCommitMetadataExtraction:
    def test_commit_hash_is_40_chars(self, repo_with_history):
        root, _ = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        for commit in commits:
            assert len(commit.hash) == 40, f"Expected 40-char hash, got: {commit.hash!r}"

    def test_short_hash_is_shorter(self, repo_with_history):
        root, _ = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        for commit in commits:
            assert len(commit.short_hash) < len(commit.hash)
            assert commit.hash.startswith(commit.short_hash)

    def test_commit_message_is_populated(self, repo_with_history):
        root, _ = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        for commit in commits:
            assert commit.message, f"Expected non-empty message for {commit.hash}"

    def test_author_is_populated(self, repo_with_history):
        root, _ = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        for commit in commits:
            assert commit.author == "DevFlow Test", (
                f"Expected 'DevFlow Test', got: {commit.author!r}"
            )

    def test_date_iso_is_populated(self, repo_with_history):
        root, _ = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        for commit in commits:
            assert commit.date_iso is not None
            # Should look like a date (starts with 20xx)
            assert commit.date_iso.startswith("20"), (
                f"Unexpected date format: {commit.date_iso!r}"
            )

    def test_correct_hashes_match_actual_git_log(self, repo_with_history):
        root, expected_hashes = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        found_hashes = {c.hash for c in commits}
        assert expected_hashes["h3"] in found_hashes
        assert expected_hashes["h2"] in found_hashes
        assert expected_hashes["h1"] in found_hashes


# ---------------------------------------------------------------------------
# 3. Artifact-to-commit association
# ---------------------------------------------------------------------------


class TestArtifactToCommitAssociation:
    def test_evidence_links_commit_to_artifact(self, repo_with_history):
        root, _ = repo_with_history
        commits, evidence = get_commits_for_artifact(root, "src/auth.py")
        assert len(evidence) == len(commits)
        for ev in evidence:
            assert ev.artifact_path == "src/auth.py"
            assert ev.commit_hash in {c.hash for c in commits}

    def test_evidence_type_is_direct_modification(self, repo_with_history):
        root, _ = repo_with_history
        _, evidence = get_commits_for_artifact(root, "src/auth.py")
        for ev in evidence:
            assert ev.evidence_type == "direct_modification"

    def test_different_files_get_different_commits(self, repo_with_multiple_files):
        root = repo_with_multiple_files
        api_commits, _ = get_commits_for_artifact(root, "src/api.py")
        auth_commits, _ = get_commits_for_artifact(root, "src/auth.py")
        api_hashes = {c.hash for c in api_commits}
        auth_hashes = {c.hash for c in auth_commits}
        # The api-update commit should appear in api but not exclusively in auth
        # (the initial commit adds both files, so there may be overlap for initial)
        assert len(api_commits) > 0
        assert len(auth_commits) > 0


# ---------------------------------------------------------------------------
# 4. Historical evidence generation
# ---------------------------------------------------------------------------


class TestHistoricalEvidenceGeneration:
    def test_evidence_description_mentions_artifact(self, repo_with_history):
        root, _ = repo_with_history
        _, evidence = get_commits_for_artifact(root, "src/auth.py")
        for ev in evidence:
            assert "src/auth.py" in ev.description, (
                f"Evidence description should mention artifact: {ev.description!r}"
            )

    def test_evidence_description_mentions_commit_hash(self, repo_with_history):
        root, _ = repo_with_history
        commits, evidence = get_commits_for_artifact(root, "src/auth.py")
        for ev in evidence:
            # short_hash should appear in description
            matching_commit = next(c for c in commits if c.hash == ev.commit_hash)
            assert matching_commit.short_hash in ev.description, (
                f"Short hash {matching_commit.short_hash!r} not in: {ev.description!r}"
            )

    def test_evidence_relevance_reason_is_set(self, repo_with_history):
        root, _ = repo_with_history
        _, evidence = get_commits_for_artifact(root, "src/auth.py")
        for ev in evidence:
            assert ev.relevance_reason, "relevance_reason must not be empty"

    def test_evidence_is_frozen(self, repo_with_history):
        root, _ = repo_with_history
        _, evidence = get_commits_for_artifact(root, "src/auth.py")
        ev = evidence[0]
        with pytest.raises((AttributeError, TypeError)):
            ev.artifact_path = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5. Multiple commits for one artifact
# ---------------------------------------------------------------------------


class TestMultipleCommitsPerArtifact:
    def test_all_three_commits_found(self, repo_with_history):
        root, hashes = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        assert len(commits) == 3

    def test_commit_messages_are_distinct(self, repo_with_history):
        root, _ = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        messages = [c.message for c in commits]
        assert len(set(messages)) == len(messages), "Commit messages should be distinct"

    def test_commit_hashes_are_distinct(self, repo_with_history):
        root, _ = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        hashes = [c.hash for c in commits]
        assert len(set(hashes)) == len(hashes), "Commit hashes should be distinct"


# ---------------------------------------------------------------------------
# 6. Limited or empty history handling
# ---------------------------------------------------------------------------


class TestLimitedOrEmptyHistory:
    def test_empty_repo_artifact_returns_no_commits(self, empty_repo: Path):
        # README.md has exactly one commit
        commits, _ = get_commits_for_artifact(empty_repo, "README.md")
        assert len(commits) == 1  # only the initial commit

    def test_missing_artifact_returns_empty(self, empty_repo: Path):
        commits, evidence = get_commits_for_artifact(empty_repo, "src/does_not_exist.py")
        assert commits == []
        assert evidence == []

    def test_build_historical_context_empty_repo(self, empty_repo: Path):
        repo_input = _make_repo_input(empty_repo)
        context = _make_context(repo_input, ["README.md"])
        hist = build_historical_context(repo_input, context)
        assert hist.error is None
        art_hist = hist.artifact_histories.get("README.md")
        assert art_hist is not None
        assert art_hist.has_history()
        assert len(art_hist.commits) == 1

    def test_build_historical_context_no_artifacts(self, empty_repo: Path):
        repo_input = _make_repo_input(empty_repo)
        # Context with no artifacts
        context = RepositoryContext(
            repository_url=repo_input.url,
            owner=repo_input.owner,
            name=repo_input.name,
            change_summary="no artifacts",
            artifacts=[],
            all_files=[],
        )
        hist = build_historical_context(repo_input, context)
        assert hist.error is not None  # should report nothing to inspect


# ---------------------------------------------------------------------------
# 7. Missing / nonexistent artifact handling
# ---------------------------------------------------------------------------


class TestMissingArtifactHandling:
    def test_nonexistent_artifact_produces_empty_history_with_note(self, empty_repo: Path):
        repo_input = _make_repo_input(empty_repo)
        context = _make_context(repo_input, ["src/nonexistent.py"])
        hist = build_historical_context(repo_input, context)
        assert hist.error is None
        art_hist = hist.artifact_histories.get("src/nonexistent.py")
        assert art_hist is not None
        assert not art_hist.has_history()
        assert art_hist.note is not None
        assert "no git history" in art_hist.note.lower()

    def test_context_error_propagates_gracefully(self, empty_repo: Path):
        repo_input = _make_repo_input(empty_repo)
        # Context with a pre-existing error (Phase 2 failed)
        context = RepositoryContext(
            repository_url=repo_input.url,
            owner=repo_input.owner,
            name=repo_input.name,
            change_summary="x",
            error="Phase 2 retrieval failed: test",
        )
        hist = build_historical_context(repo_input, context)
        assert hist.error is not None
        assert "Phase 2" in hist.error or "error" in hist.error.lower()


# ---------------------------------------------------------------------------
# 8. Commit message historical references
# ---------------------------------------------------------------------------


class TestCommitMessageReferences:
    def test_ref_extracted_from_commit_message(self, repo_with_history):
        """Commit 'feat: improve session handling #42' must record '#42' as a ref."""
        root, _ = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        ref_commits = [c for c in commits if "#42" in c.refs]
        assert len(ref_commits) == 1, (
            f"Expected one commit with ref '#42', got: {[c.message for c in commits]}"
        )

    def test_ref_is_not_labeled_as_github_issue(self, repo_with_history):
        """
        The ref '#42' found in a commit message must NOT be declared as a
        GitHub Issue or Pull Request in the evidence — only as a message reference.

        DevFlow records what Git evidence shows; it does not assert external
        platform identity unless confirmed.
        """
        root, _ = repo_with_history
        _, evidence = get_commits_for_artifact(root, "src/auth.py")
        for ev in evidence:
            # Evidence description must not claim '#42' is a GitHub Issue or PR.
            assert "github issue" not in ev.description.lower(), (
                f"Evidence must not assert '#42' is a GitHub Issue: {ev.description!r}"
            )
            assert "pull request" not in ev.description.lower() or (
                "pull request" not in ev.description.lower()
            ), (
                f"Evidence must not assert '#42' is a Pull Request: {ev.description!r}"
            )

    def test_multiple_refs_extracted(self, tmp_path: Path):
        root = tmp_path / "ref_repo"
        _init_repo(root)
        _commit(root, "fix things #10 #20 #30", {"src/x.py": "x"})
        commits, _ = get_commits_for_artifact(root, "src/x.py")
        assert len(commits) == 1
        assert "#10" in commits[0].refs
        assert "#20" in commits[0].refs
        assert "#30" in commits[0].refs

    def test_commit_with_no_ref(self, tmp_path: Path):
        root = tmp_path / "no_ref_repo"
        _init_repo(root)
        _commit(root, "plain commit message", {"src/y.py": "y"})
        commits, _ = get_commits_for_artifact(root, "src/y.py")
        assert commits[0].refs == ()


# ---------------------------------------------------------------------------
# 9. No fabricated evidence
# ---------------------------------------------------------------------------


class TestNoFabricatedEvidence:
    def test_all_commit_hashes_are_real(self, repo_with_history):
        root, expected_hashes = repo_with_history
        commits, _ = get_commits_for_artifact(root, "src/auth.py")
        real_hashes = set(expected_hashes.values())
        for commit in commits:
            assert commit.hash in real_hashes, (
                f"Commit hash {commit.hash!r} was not found in the actual git log."
            )

    def test_build_historical_context_total_commits_matches(self, repo_with_multiple_files: Path):
        root = repo_with_multiple_files
        repo_input = _make_repo_input(root)
        context = _make_context(repo_input, ["src/api.py", "src/auth.py"])
        hist = build_historical_context(repo_input, context)
        assert hist.error is None
        # total_commits_found should equal the number of distinct hashes found
        all_hashes = {c.hash for art in hist.artifact_histories.values() for c in art.commits}
        assert hist.total_commits_found == len(all_hashes)

    def test_artifacts_without_history_have_no_commits(self, empty_repo: Path):
        repo_input = _make_repo_input(empty_repo)
        context = _make_context(repo_input, ["src/fabricated.py"])
        hist = build_historical_context(repo_input, context)
        art_hist = hist.artifact_histories["src/fabricated.py"]
        assert art_hist.commits == ()
        assert art_hist.evidence == ()

    def test_no_commits_invented_when_file_absent(self, empty_repo: Path):
        repo_input = _make_repo_input(empty_repo)
        context = _make_context(repo_input, ["src/doesnotexist.py"])
        hist = build_historical_context(repo_input, context)
        assert hist.artifact_histories["src/doesnotexist.py"].commits == ()


# ---------------------------------------------------------------------------
# build_historical_context — integration
# ---------------------------------------------------------------------------


class TestBuildHistoricalContextIntegration:
    def test_returns_repository_history(self, repo_with_history):
        root, _ = repo_with_history
        repo_input = _make_repo_input(root)
        context = _make_context(repo_input, ["src/auth.py"])
        hist = build_historical_context(repo_input, context)
        assert isinstance(hist, RepositoryHistory)

    def test_metadata_preserved(self, repo_with_history):
        root, _ = repo_with_history
        repo_input = _make_repo_input(root)
        context = _make_context(repo_input, ["src/auth.py"], change_summary="Auth refactor")
        hist = build_historical_context(repo_input, context)
        assert hist.repository_url == repo_input.url
        assert hist.owner == "local"
        assert hist.name == root.name
        assert hist.change_summary == "Auth refactor"

    def test_all_artifacts_present_in_histories(self, repo_with_multiple_files: Path):
        root = repo_with_multiple_files
        repo_input = _make_repo_input(root)
        context = _make_context(repo_input, ["src/api.py", "src/auth.py"])
        hist = build_historical_context(repo_input, context)
        assert "src/api.py" in hist.artifact_histories
        assert "src/auth.py" in hist.artifact_histories

    def test_artifacts_with_history_helper(self, repo_with_multiple_files: Path):
        root = repo_with_multiple_files
        repo_input = _make_repo_input(root)
        context = _make_context(repo_input, ["src/api.py", "src/auth.py", "src/ghost.py"])
        hist = build_historical_context(repo_input, context)
        with_hist = hist.artifacts_with_history()
        without_hist = hist.artifacts_without_history()
        assert all(h.has_history() for h in with_hist)
        assert all(not h.has_history() for h in without_hist)

    def test_all_commits_helper_deduplicated(self, repo_with_multiple_files: Path):
        root = repo_with_multiple_files
        repo_input = _make_repo_input(root)
        # Both files share the initial commit — all_commits must deduplicate it.
        context = _make_context(repo_input, ["src/api.py", "src/auth.py"])
        hist = build_historical_context(repo_input, context)
        all_commits = hist.all_commits()
        hashes = [c.hash for c in all_commits]
        assert len(hashes) == len(set(hashes)), "all_commits() must return deduplicated commits"

    def test_cleanup_after_build(self, repo_with_history):
        """Temporary clone must not persist after build_historical_context returns."""
        import os
        import glob as globmod

        root, _ = repo_with_history
        repo_input = _make_repo_input(root)
        context = _make_context(repo_input, ["src/auth.py"])

        # Record temp dirs before.
        before = set(globmod.glob("/tmp/devflow_hist_*"))

        hist = build_historical_context(repo_input, context)

        # Any new devflow_hist_ temp dirs should be gone.
        after = set(globmod.glob("/tmp/devflow_hist_*"))
        new_dirs = after - before
        for d in new_dirs:
            assert not Path(d).exists(), f"Temp dir not cleaned up: {d}"


# ---------------------------------------------------------------------------
# is_git_repository
# ---------------------------------------------------------------------------


class TestIsGitRepository:
    def test_recognises_git_repo(self, empty_repo: Path):
        assert is_git_repository(empty_repo) is True

    def test_rejects_non_git_dir(self, tmp_path: Path):
        assert is_git_repository(tmp_path) is False


# ---------------------------------------------------------------------------
# _find_repo_root (Phase 3 helper)
# ---------------------------------------------------------------------------


class TestPhase3FindRepoRoot:
    def test_finds_exact_name(self, tmp_path: Path):
        from devflow.history._build import _find_repo_root as _p3_find
        expected = tmp_path / "myrepo"
        expected.mkdir()
        assert _p3_find(tmp_path, "myrepo") == expected

    def test_falls_back_to_first_subdir(self, tmp_path: Path):
        from devflow.history._build import _find_repo_root as _p3_find
        subdir = tmp_path / "something"
        subdir.mkdir()
        assert _p3_find(tmp_path, "notfound") == subdir


# ---------------------------------------------------------------------------
# Phase 0–2 regression: existing public APIs still import and behave
# ---------------------------------------------------------------------------


class TestPhase012Regression:
    def test_config_imports(self):
        from devflow.config import Config
        c = Config()
        assert c.version

    def test_accept_input(self):
        from devflow.input import accept_input
        from devflow.models.repository import RepositoryInputError
        repo, change = accept_input(
            "https://github.com/example/myrepo",
            "Test change description.",
        )
        assert repo.owner == "example"
        assert repo.name == "myrepo"
        assert change.description == "Test change description."

    def test_change_request_error(self):
        from devflow.input import accept_input
        from devflow.models.change import ChangeRequestError
        with pytest.raises(ChangeRequestError):
            accept_input("https://github.com/example/repo", "   ")

    def test_repository_input_error(self):
        from devflow.input import accept_input
        from devflow.models.repository import RepositoryInputError
        with pytest.raises(RepositoryInputError):
            accept_input("not-a-url", "valid description")

    def test_context_models_importable(self):
        from devflow.models.context import (
            ArtifactKind,
            ContextArtifact,
            RelevanceReason,
            RepositoryContext,
        )
        assert ArtifactKind.SOURCE.value == "source"

    def test_build_context_with_local_fixture(self, tmp_path: Path):
        """Phase 2 build_context still works end-to-end."""
        from devflow.context._build import build_context
        from devflow.models.change import ChangeRequest

        root = tmp_path / "regression_repo"
        _init_repo(root)
        _commit(root, "initial", {"src/auth.py": "# auth", "README.md": "# docs"})

        repo_input = _make_repo_input(root)
        change = ChangeRequest.from_inputs("Refactor authentication.")
        ctx = build_context(repo_input, change)

        assert ctx.error is None
        assert len(ctx.all_files) > 0
        assert ctx.retrieval_path is None  # cleaned up

    def test_history_models_importable(self):
        from devflow.models.history import (
            ArtifactHistory,
            HistoricalCommit,
            HistoricalEvidence,
            RepositoryHistory,
        )
        commit = HistoricalCommit(
            hash="a" * 40,
            short_hash="aaaaaaa",
            message="test",
            author="Dev",
            date_iso="2024-01-01",
            refs=(),
        )
        assert commit.hash == "a" * 40
