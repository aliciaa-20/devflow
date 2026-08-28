"""
Deterministic tests for Phase 1: Repository + Change Input.

Covers:
- RepositoryInput: valid URLs, invalid URLs, owner/name extraction
- ChangeRequest: valid descriptions, blank descriptions, changed_files handling
- accept_input(): combined entry point, error propagation
"""

import pytest

from devflow.input import accept_input
from devflow.models.change import ChangeRequest, ChangeRequestError
from devflow.models.repository import RepositoryInput, RepositoryInputError


# ---------------------------------------------------------------------------
# RepositoryInput.from_url — valid cases
# ---------------------------------------------------------------------------


class TestRepositoryInputValid:
    def test_basic_url(self):
        r = RepositoryInput.from_url("https://github.com/owner/repo")
        assert r.owner == "owner"
        assert r.name == "repo"
        assert r.url == "https://github.com/owner/repo"

    def test_url_with_git_suffix(self):
        r = RepositoryInput.from_url("https://github.com/owner/repo.git")
        assert r.owner == "owner"
        assert r.name == "repo"

    def test_url_with_trailing_slash(self):
        r = RepositoryInput.from_url("https://github.com/owner/repo/")
        assert r.owner == "owner"
        assert r.name == "repo"
        # Trailing slash is stripped from stored URL
        assert not r.url.endswith("/")

    def test_url_with_leading_whitespace(self):
        r = RepositoryInput.from_url("  https://github.com/owner/repo  ")
        assert r.owner == "owner"
        assert r.name == "repo"

    def test_hyphenated_owner_and_repo(self):
        r = RepositoryInput.from_url("https://github.com/my-org/my-repo")
        assert r.owner == "my-org"
        assert r.name == "my-repo"

    def test_numeric_components(self):
        r = RepositoryInput.from_url("https://github.com/org123/repo456")
        assert r.owner == "org123"
        assert r.name == "repo456"

    def test_dotted_repo_name(self):
        r = RepositoryInput.from_url("https://github.com/owner/my.project")
        assert r.name == "my.project"

    def test_underscore_repo_name(self):
        r = RepositoryInput.from_url("https://github.com/owner/my_project")
        assert r.name == "my_project"

    def test_frozen_dataclass(self):
        r = RepositoryInput.from_url("https://github.com/owner/repo")
        with pytest.raises(Exception):  # frozen=True raises FrozenInstanceError
            r.owner = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RepositoryInput.from_url — invalid cases
# ---------------------------------------------------------------------------


class TestRepositoryInputInvalid:
    def test_empty_string(self):
        with pytest.raises(RepositoryInputError, match="must not be empty"):
            RepositoryInput.from_url("")

    def test_whitespace_only(self):
        with pytest.raises(RepositoryInputError, match="must not be empty"):
            RepositoryInput.from_url("   ")

    def test_not_github_domain(self):
        with pytest.raises(RepositoryInputError, match="Invalid GitHub repository URL"):
            RepositoryInput.from_url("https://gitlab.com/owner/repo")

    def test_http_not_https(self):
        with pytest.raises(RepositoryInputError, match="Invalid GitHub repository URL"):
            RepositoryInput.from_url("http://github.com/owner/repo")

    def test_missing_repo_segment(self):
        with pytest.raises(RepositoryInputError, match="Invalid GitHub repository URL"):
            RepositoryInput.from_url("https://github.com/owner")

    def test_missing_owner_and_repo(self):
        with pytest.raises(RepositoryInputError, match="Invalid GitHub repository URL"):
            RepositoryInput.from_url("https://github.com/")

    def test_plain_domain(self):
        with pytest.raises(RepositoryInputError, match="Invalid GitHub repository URL"):
            RepositoryInput.from_url("https://github.com")

    def test_arbitrary_string(self):
        with pytest.raises(RepositoryInputError, match="Invalid GitHub repository URL"):
            RepositoryInput.from_url("not-a-url")

    def test_ssh_url(self):
        with pytest.raises(RepositoryInputError, match="Invalid GitHub repository URL"):
            RepositoryInput.from_url("git@github.com:owner/repo.git")

    def test_extra_path_segments(self):
        # URLs with extra path segments (e.g. issue or PR URLs) are not repository roots
        with pytest.raises(RepositoryInputError, match="Invalid GitHub repository URL"):
            RepositoryInput.from_url("https://github.com/owner/repo/issues/1")


# ---------------------------------------------------------------------------
# ChangeRequest.from_inputs — valid cases
# ---------------------------------------------------------------------------


class TestChangeRequestValid:
    def test_description_only(self):
        cr = ChangeRequest.from_inputs("Refactor authentication session handling.")
        assert cr.description == "Refactor authentication session handling."
        assert cr.changed_files == ()

    def test_description_with_whitespace_stripped(self):
        cr = ChangeRequest.from_inputs("  some change  ")
        assert cr.description == "some change"

    def test_with_changed_files(self):
        cr = ChangeRequest.from_inputs(
            "Add rate limiting.",
            ["src/api/routes.py", "tests/test_routes.py"],
        )
        assert "src/api/routes.py" in cr.changed_files
        assert "tests/test_routes.py" in cr.changed_files
        assert len(cr.changed_files) == 2

    def test_empty_changed_files_list(self):
        cr = ChangeRequest.from_inputs("Some change.", [])
        assert cr.changed_files == ()

    def test_changed_files_strips_whitespace(self):
        cr = ChangeRequest.from_inputs("Some change.", ["  src/foo.py  ", " src/bar.py"])
        assert "src/foo.py" in cr.changed_files
        assert "src/bar.py" in cr.changed_files

    def test_changed_files_skips_blank_entries(self):
        cr = ChangeRequest.from_inputs("Some change.", ["src/foo.py", "   ", ""])
        assert len(cr.changed_files) == 1
        assert "src/foo.py" in cr.changed_files

    def test_frozen_dataclass(self):
        cr = ChangeRequest.from_inputs("Some change.")
        with pytest.raises(Exception):
            cr.description = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ChangeRequest.from_inputs — invalid cases
# ---------------------------------------------------------------------------


class TestChangeRequestInvalid:
    def test_empty_description(self):
        with pytest.raises(ChangeRequestError, match="must not be empty"):
            ChangeRequest.from_inputs("")

    def test_whitespace_only_description(self):
        with pytest.raises(ChangeRequestError, match="must not be empty"):
            ChangeRequest.from_inputs("   ")


# ---------------------------------------------------------------------------
# accept_input() — combined entry point
# ---------------------------------------------------------------------------


class TestAcceptInput:
    def test_returns_tuple(self):
        repo, change = accept_input(
            "https://github.com/example/project",
            "Refactor authentication session handling.",
        )
        assert isinstance(repo, RepositoryInput)
        assert isinstance(change, ChangeRequest)

    def test_correct_normalized_values(self):
        repo, change = accept_input(
            "https://github.com/example/project",
            "Refactor authentication session handling.",
            ["src/auth.py"],
        )
        assert repo.owner == "example"
        assert repo.name == "project"
        assert change.description == "Refactor authentication session handling."
        assert "src/auth.py" in change.changed_files

    def test_invalid_url_raises_repository_error(self):
        with pytest.raises(RepositoryInputError):
            accept_input("not-a-url", "Some change")

    def test_empty_description_raises_change_error(self):
        with pytest.raises(ChangeRequestError):
            accept_input("https://github.com/owner/repo", "")

    def test_no_changed_files_defaults_to_empty(self):
        _, change = accept_input(
            "https://github.com/owner/repo",
            "Add caching layer.",
        )
        assert change.changed_files == ()
