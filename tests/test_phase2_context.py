"""
Deterministic tests for Phase 2: Repository Context Reconstruction.

All tests use temporary local git repositories created on-the-fly.
No network access or GitHub availability is required.

Covers:
- RepositoryRetrievalError for invalid / inaccessible repositories
- RetrievedRepository cleanup
- walk_repository: structure discovery, skip dirs
- classify_file: all ArtifactKind categories
- is_entry_point
- select_relevant_artifacts: changed files, always-relevant kinds,
  keyword matching, test overlap, deduplication
- build_context: end-to-end with local fixture repo (using file:// URL + git clone)
- build_context: graceful handling of bad URL
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from devflow.context._build import build_context, _find_repo_root
from devflow.context.inspector import classify_file, is_entry_point, walk_repository
from devflow.context.relevance import select_relevant_artifacts, _extract_keywords, _path_keywords
from devflow.context.retriever import RetrievedRepository, RepositoryRetrievalError
from devflow.input import accept_input
from devflow.models.change import ChangeRequest
from devflow.models.context import ArtifactKind, RelevanceReason, RepositoryContext
from devflow.models.repository import RepositoryInput


# ---------------------------------------------------------------------------
# Fixtures: temporary git repository helpers
# ---------------------------------------------------------------------------


def _init_local_git_repo(root: Path, files: dict[str, str]) -> Path:
    """
    Create a minimal local bare-like git repository with the given files.

    Args:
        root:  Directory that will become the repo root.
        files: Mapping of relative path → file content.

    Returns:
        The repo root path.
    """
    root.mkdir(parents=True, exist_ok=True)

    # Write all files.
    for rel_path, content in files.items():
        abs_path = root / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content)

    # Initialise git and commit.
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@devflow"],
        cwd=root, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "DevFlow Test"],
        cwd=root, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=root, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial commit"],
        cwd=root, check=True, capture_output=True,
    )
    return root


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """A minimal local git repo with typical project structure."""
    files = {
        "README.md": "# My Project\nSome documentation.",
        "pyproject.toml": "[project]\nname = 'myproject'",
        ".gitignore": "*.pyc\n__pycache__/",
        "src/myproject/__main__.py": "def main(): pass",
        "src/myproject/auth/session.py": "class SessionManager: pass",
        "src/myproject/auth/tokens.py": "def generate_token(): pass",
        "src/myproject/api/routes.py": "def get_routes(): pass",
        "tests/__init__.py": "",
        "tests/test_session.py": "def test_session(): pass",
        "tests/test_tokens.py": "def test_tokens(): pass",
        "docs/architecture.md": "# Architecture",
        "requirements.txt": "flask>=3.0",
    }
    repo_root = tmp_path / "myproject"
    yield _init_local_git_repo(repo_root, files)


@pytest.fixture()
def tmp_empty_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """A git repo with no source files (just a README)."""
    files = {"README.md": "empty project"}
    repo_root = tmp_path / "empty"
    yield _init_local_git_repo(repo_root, files)


# ---------------------------------------------------------------------------
# classify_file
# ---------------------------------------------------------------------------


class TestClassifyFile:
    def test_python_source(self):
        assert classify_file("src/auth/session.py") == ArtifactKind.SOURCE

    def test_typescript_source(self):
        assert classify_file("src/components/Button.tsx") == ArtifactKind.SOURCE

    def test_go_source(self):
        assert classify_file("cmd/main.go") == ArtifactKind.SOURCE

    def test_test_by_directory(self):
        assert classify_file("tests/test_session.py") == ArtifactKind.TEST

    def test_test_by_prefix(self):
        assert classify_file("src/test_session.py") == ArtifactKind.TEST

    def test_test_by_suffix(self):
        assert classify_file("src/session_test.go") == ArtifactKind.TEST

    def test_spec_directory(self):
        assert classify_file("spec/models/user_spec.rb") == ArtifactKind.TEST

    def test_jest_test(self):
        assert classify_file("src/components/Button.test.tsx") == ArtifactKind.TEST

    def test_markdown_doc(self):
        assert classify_file("README.md") == ArtifactKind.DOCUMENTATION

    def test_rst_doc(self):
        assert classify_file("docs/api.rst") == ArtifactKind.DOCUMENTATION

    def test_changelog_doc(self):
        assert classify_file("CHANGELOG.md") == ArtifactKind.DOCUMENTATION

    def test_docs_directory(self):
        assert classify_file("docs/guide.html") == ArtifactKind.DOCUMENTATION

    def test_pyproject_dependency(self):
        assert classify_file("pyproject.toml") == ArtifactKind.DEPENDENCY

    def test_requirements_dependency(self):
        assert classify_file("requirements.txt") == ArtifactKind.DEPENDENCY

    def test_package_json_dependency(self):
        assert classify_file("package.json") == ArtifactKind.DEPENDENCY

    def test_cargo_toml_dependency(self):
        assert classify_file("Cargo.toml") == ArtifactKind.DEPENDENCY

    def test_gitignore_config(self):
        assert classify_file(".gitignore") == ArtifactKind.CONFIGURATION

    def test_dockerfile_config(self):
        assert classify_file("Dockerfile") == ArtifactKind.CONFIGURATION

    def test_yaml_config(self):
        assert classify_file("config/app.yml") == ArtifactKind.CONFIGURATION

    def test_unknown_binary(self):
        assert classify_file("assets/logo.png") == ArtifactKind.OTHER

    def test_nested_test_dir(self):
        assert classify_file("backend/tests/unit/test_auth.py") == ArtifactKind.TEST


# ---------------------------------------------------------------------------
# is_entry_point
# ---------------------------------------------------------------------------


class TestIsEntryPoint:
    def test_main_py(self):
        assert is_entry_point("src/pkg/__main__.py") is True

    def test_app_py(self):
        assert is_entry_point("app.py") is True

    def test_index_js(self):
        assert is_entry_point("src/index.js") is True

    def test_regular_module(self):
        assert is_entry_point("src/auth/session.py") is False

    def test_manage_py_django(self):
        assert is_entry_point("manage.py") is True


# ---------------------------------------------------------------------------
# walk_repository
# ---------------------------------------------------------------------------


class TestWalkRepository:
    def test_finds_source_files(self, tmp_repo: Path):
        files, _ = walk_repository(tmp_repo)
        assert any("session.py" in f for f in files)
        assert any("routes.py" in f for f in files)

    def test_finds_test_files(self, tmp_repo: Path):
        files, _ = walk_repository(tmp_repo)
        assert any("test_session.py" in f for f in files)

    def test_skips_git_dir(self, tmp_repo: Path):
        files, _ = walk_repository(tmp_repo)
        # Ensure no file is inside the .git directory (path component check).
        # Note: .gitignore is a legitimate file and will be included.
        assert not any(
            part == ".git"
            for f in files
            for part in f.replace("\\", "/").split("/")[:-1]  # directory parts only
        )

    def test_skips_pycache(self, tmp_path: Path):
        # Add a __pycache__ dir manually and ensure it's skipped.
        pycache = tmp_path / "src" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "foo.pyc").write_bytes(b"")
        (tmp_path / "src" / "main.py").parent.mkdir(exist_ok=True)
        (tmp_path / "src" / "main.py").write_text("pass")
        files, _ = walk_repository(tmp_path)
        assert not any("__pycache__" in f for f in files)
        assert any("main.py" in f for f in files)

    def test_entry_points_identified(self, tmp_repo: Path):
        _, entry_points = walk_repository(tmp_repo)
        assert any("__main__.py" in ep for ep in entry_points)

    def test_returns_relative_paths(self, tmp_repo: Path):
        files, _ = walk_repository(tmp_repo)
        for f in files:
            assert not Path(f).is_absolute(), f"Expected relative path, got: {f}"

    def test_empty_repo(self, tmp_empty_repo: Path):
        files, entry_points = walk_repository(tmp_empty_repo)
        assert "README.md" in files
        assert entry_points == []

    def test_forward_slashes(self, tmp_repo: Path):
        files, _ = walk_repository(tmp_repo)
        for f in files:
            assert "\\" not in f, f"Backslash found in path: {f}"


# ---------------------------------------------------------------------------
# _extract_keywords and _path_keywords
# ---------------------------------------------------------------------------


class TestKeywordExtraction:
    def test_extracts_meaningful_tokens(self):
        kws = _extract_keywords("Refactor authentication session handling.")
        assert "authentication" in kws
        assert "session" in kws
        assert "refactor" in kws

    def test_filters_stopwords(self):
        kws = _extract_keywords("Add rate limiting to the public API endpoints.")
        assert "the" not in kws
        assert "limiting" in kws
        assert "endpoints" in kws

    def test_path_keywords_splits_on_separator(self):
        kws = _path_keywords("src/auth/session.py")
        assert "auth" in kws
        assert "session" in kws

    def test_path_keywords_camel_not_split(self):
        # CamelCase is not split — stays as single token.
        kws = _path_keywords("src/AuthService.ts")
        assert "authservice" in kws


# ---------------------------------------------------------------------------
# select_relevant_artifacts
# ---------------------------------------------------------------------------


class TestSelectRelevantArtifacts:
    def _make_change(self, description: str, changed_files=None):
        return ChangeRequest.from_inputs(description, changed_files)

    def test_changed_file_always_selected(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change(
            "Update session handling.",
            ["src/myproject/auth/session.py"],
        )
        artifacts = select_relevant_artifacts(all_files, change)
        paths = [a.path for a in artifacts]
        assert "src/myproject/auth/session.py" in paths

    def test_changed_file_reason(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change(
            "Update session handling.",
            ["src/myproject/auth/session.py"],
        )
        artifacts = select_relevant_artifacts(all_files, change)
        by_path = {a.path: a for a in artifacts}
        art = by_path.get("src/myproject/auth/session.py")
        assert art is not None
        assert art.reason == RelevanceReason.CHANGED_FILE
        assert art.confidence == "confirmed"

    def test_dependency_manifest_always_selected(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change("Unrelated change.")
        artifacts = select_relevant_artifacts(all_files, change)
        paths = [a.path for a in artifacts]
        assert "pyproject.toml" in paths
        assert "requirements.txt" in paths

    def test_documentation_always_selected(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change("Some change.")
        artifacts = select_relevant_artifacts(all_files, change)
        paths = [a.path for a in artifacts]
        assert "README.md" in paths

    def test_configuration_always_selected(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change("Some change.")
        artifacts = select_relevant_artifacts(all_files, change)
        paths = [a.path for a in artifacts]
        assert ".gitignore" in paths

    def test_keyword_match_selects_relevant_source(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change("Refactor authentication session token generation.")
        artifacts = select_relevant_artifacts(all_files, change)
        paths = [a.path for a in artifacts]
        # session.py and tokens.py should match keywords
        assert any("session" in p for p in paths)

    def test_test_for_changed_selects_test_file(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change(
            "Update session logic.",
            ["src/myproject/auth/session.py"],
        )
        artifacts = select_relevant_artifacts(all_files, change)
        paths = [a.path for a in artifacts]
        assert any("test_session" in p for p in paths)

    def test_test_for_changed_reason(self, tmp_path: Path):
        # Build a repo where the changed file name is distinct enough from
        # the description keywords that the test can only be found via
        # TEST_FOR_CHANGED (stem overlap), not keyword match.
        files = {
            "README.md": "# Project",
            "src/pkg/zeta.py": "class Zeta: pass",
            "tests/test_zeta.py": "def test_zeta(): pass",
        }
        repo_root = tmp_path / "zetarepo"
        _init_local_git_repo(repo_root, files)

        all_files, _ = walk_repository(repo_root)
        # Description has no token overlapping with "zeta".
        change = self._make_change(
            "Improve database connection pooling.",
            ["src/pkg/zeta.py"],
        )
        artifacts = select_relevant_artifacts(all_files, change)
        test_art = next(
            (a for a in artifacts if "test_zeta" in a.path and a.reason == RelevanceReason.TEST_FOR_CHANGED),
            None,
        )
        assert test_art is not None, (
            "Expected a TEST_FOR_CHANGED artifact for test_zeta.py. "
            f"Got: {[(a.path, a.reason) for a in artifacts if 'zeta' in a.path]}"
        )
        assert test_art.kind == ArtifactKind.TEST
        assert test_art.confidence == "likely"

    def test_no_duplicate_paths(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change(
            "Refactor session authentication.",
            ["src/myproject/auth/session.py"],
        )
        artifacts = select_relevant_artifacts(all_files, change)
        paths = [a.path for a in artifacts]
        assert len(paths) == len(set(paths))

    def test_artifacts_sorted_by_path(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change("Some change.")
        artifacts = select_relevant_artifacts(all_files, change)
        paths = [a.path for a in artifacts]
        assert paths == sorted(paths)

    def test_empty_repo_returns_only_docs(self, tmp_empty_repo: Path):
        all_files, _ = walk_repository(tmp_empty_repo)
        change = self._make_change("Some change.")
        artifacts = select_relevant_artifacts(all_files, change)
        assert len(artifacts) == 1
        assert artifacts[0].path == "README.md"
        assert artifacts[0].kind == ArtifactKind.DOCUMENTATION

    def test_artifact_has_evidence_string(self, tmp_repo: Path):
        all_files, _ = walk_repository(tmp_repo)
        change = self._make_change("Add session timeout.")
        artifacts = select_relevant_artifacts(all_files, change)
        for art in artifacts:
            assert art.evidence, f"Artifact {art.path} has no evidence string"


# ---------------------------------------------------------------------------
# RepositoryRetrievalError handling
# ---------------------------------------------------------------------------


class TestRepositoryRetrievalError:
    def test_nonexistent_repo_raises_error(self):
        """A non-existent GitHub URL should raise RepositoryRetrievalError."""
        with pytest.raises(RepositoryRetrievalError):
            RetrievedRepository.clone(
                url="https://github.com/devflow-does-not-exist-zzzz/no-such-repo",
                owner="devflow-does-not-exist-zzzz",
                name="no-such-repo",
                timeout=30,
            )

    def test_invalid_url_string_raises_error(self):
        """An unparseable URL should fail at git clone level."""
        with pytest.raises(RepositoryRetrievalError):
            RetrievedRepository.clone(
                url="not-a-real-url",
                owner="x",
                name="y",
                timeout=10,
            )


# ---------------------------------------------------------------------------
# RetrievedRepository cleanup
# ---------------------------------------------------------------------------


class TestRetrievedRepositoryCleanup:
    def test_context_manager_cleans_up(self, tmp_repo: Path):
        """Using as a context manager must remove the temp directory."""
        # Simulate a "clone" by pointing at our fixture as the tmpdir.
        # We need a real RetrievedRepository — use a local file:// clone.
        parent = tempfile.mkdtemp(prefix="devflow_test_")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", "-q", str(tmp_repo), str(Path(parent) / "myproject")],
                capture_output=True,
            )
            if result.returncode != 0:
                pytest.skip("git clone unavailable in this environment")

            rr = RetrievedRepository(
                url=str(tmp_repo),
                owner="test",
                name="myproject",
                local_path=Path(parent),
            )
            assert rr.is_available
            with rr:
                local_path = rr.path
            # After context manager exits, temp dir should be gone.
            assert not local_path.exists()
        finally:
            shutil.rmtree(parent, ignore_errors=True)

    def test_cleanup_idempotent(self, tmp_repo: Path):
        """Calling cleanup() twice must not raise an error."""
        parent = tempfile.mkdtemp(prefix="devflow_test_")
        try:
            rr = RetrievedRepository(
                url=str(tmp_repo),
                owner="test",
                name="myproject",
                local_path=Path(parent),
            )
            rr.cleanup()
            rr.cleanup()  # Should not raise.
        finally:
            shutil.rmtree(parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# build_context — end-to-end with local fixture
# ---------------------------------------------------------------------------


class TestBuildContextLocalFixture:
    def _local_url(self, repo_path: Path) -> str:
        """Return a file:// URL for a local git repo."""
        return repo_path.as_uri()

    def _local_repo_input(self, repo_path: Path) -> RepositoryInput:
        # Build a RepositoryInput manually (bypassing URL regex validation
        # since file:// URLs won't pass the GitHub validator).
        return RepositoryInput(
            url=self._local_url(repo_path),
            owner="local",
            name=repo_path.name,
        )

    def test_build_context_returns_repository_context(self, tmp_repo: Path):
        repo_input = self._local_repo_input(tmp_repo)
        change = ChangeRequest.from_inputs("Refactor session authentication.")
        ctx = build_context(repo_input, change)
        assert isinstance(ctx, RepositoryContext)

    def test_build_context_no_error_for_valid_repo(self, tmp_repo: Path):
        repo_input = self._local_repo_input(tmp_repo)
        change = ChangeRequest.from_inputs("Refactor session handling.")
        ctx = build_context(repo_input, change)
        assert ctx.error is None, f"Unexpected error: {ctx.error}"

    def test_build_context_all_files_non_empty(self, tmp_repo: Path):
        repo_input = self._local_repo_input(tmp_repo)
        change = ChangeRequest.from_inputs("Add session timeout.")
        ctx = build_context(repo_input, change)
        assert len(ctx.all_files) > 0

    def test_build_context_artifacts_non_empty(self, tmp_repo: Path):
        repo_input = self._local_repo_input(tmp_repo)
        change = ChangeRequest.from_inputs("Refactor session handling.")
        ctx = build_context(repo_input, change)
        assert len(ctx.artifacts) > 0

    def test_build_context_retrieval_path_is_none_after_cleanup(self, tmp_repo: Path):
        """retrieval_path must be None — the temp dir is cleaned up inside build_context."""
        repo_input = self._local_repo_input(tmp_repo)
        change = ChangeRequest.from_inputs("Refactor session handling.")
        ctx = build_context(repo_input, change)
        assert ctx.retrieval_path is None

    def test_build_context_entry_points_detected(self, tmp_repo: Path):
        repo_input = self._local_repo_input(tmp_repo)
        change = ChangeRequest.from_inputs("Update main entrypoint.")
        ctx = build_context(repo_input, change)
        assert any("__main__.py" in ep for ep in ctx.entry_points)

    def test_build_context_metadata_preserved(self, tmp_repo: Path):
        repo_input = self._local_repo_input(tmp_repo)
        change = ChangeRequest.from_inputs("Some change.")
        ctx = build_context(repo_input, change)
        assert ctx.repository_url == repo_input.url
        assert ctx.owner == "local"
        assert ctx.name == "myproject"
        assert ctx.change_summary == "Some change."

    def test_build_context_helper_methods(self, tmp_repo: Path):
        repo_input = self._local_repo_input(tmp_repo)
        change = ChangeRequest.from_inputs("Refactor session authentication.")
        ctx = build_context(repo_input, change)
        # Helper methods return subsets of artifacts
        all_artifact_paths = {a.path for a in ctx.artifacts}
        for a in ctx.relevant_sources():
            assert a.path in all_artifact_paths
        for a in ctx.relevant_tests():
            assert a.path in all_artifact_paths


# ---------------------------------------------------------------------------
# build_context — invalid / inaccessible repository
# ---------------------------------------------------------------------------


class TestBuildContextFailures:
    def test_nonexistent_repo_returns_error_context(self):
        """build_context must not raise; it returns a RepositoryContext with error set."""
        repo_input = RepositoryInput(
            url="https://github.com/devflow-no-exist-zzz/no-such-repo-zzz",
            owner="devflow-no-exist-zzz",
            name="no-such-repo-zzz",
        )
        change = ChangeRequest.from_inputs("Some change.")
        ctx = build_context(repo_input, change, clone_timeout=30)
        assert ctx.error is not None
        assert "no-such-repo-zzz" in ctx.error or "Failed" in ctx.error or "clone" in ctx.error.lower()

    def test_failed_context_has_empty_artifacts(self):
        repo_input = RepositoryInput(
            url="https://github.com/devflow-no-exist-zzz/no-such-repo-zzz",
            owner="devflow-no-exist-zzz",
            name="no-such-repo-zzz",
        )
        change = ChangeRequest.from_inputs("Some change.")
        ctx = build_context(repo_input, change, clone_timeout=30)
        assert ctx.artifacts == []
        assert ctx.all_files == []


# ---------------------------------------------------------------------------
# _find_repo_root
# ---------------------------------------------------------------------------


class TestFindRepoRoot:
    def test_finds_exact_name(self, tmp_path: Path):
        expected = tmp_path / "myrepo"
        expected.mkdir()
        result = _find_repo_root(tmp_path, "myrepo")
        assert result == expected

    def test_finds_without_git_suffix(self, tmp_path: Path):
        (tmp_path / "myrepo").mkdir()
        result = _find_repo_root(tmp_path, "myrepo.git")
        assert result == tmp_path / "myrepo"

    def test_falls_back_to_first_subdir(self, tmp_path: Path):
        subdir = tmp_path / "something_else"
        subdir.mkdir()
        result = _find_repo_root(tmp_path, "notfound")
        assert result == subdir

    def test_falls_back_to_tmpdir_when_no_subdirs(self, tmp_path: Path):
        result = _find_repo_root(tmp_path, "notfound")
        assert result == tmp_path
