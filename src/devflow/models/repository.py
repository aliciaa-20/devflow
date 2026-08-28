"""
Repository input model for DevFlow.

Accepts a public GitHub repository URL, validates it, and extracts
the owner and repository name for use by downstream pipeline stages.

No repository cloning or API calls are performed here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Matches:
#   https://github.com/owner/repo
#   https://github.com/owner/repo.git
#   https://github.com/owner/repo/
# Owner and repo names follow GitHub naming rules: alphanumeric, hyphens, dots,
# underscores; between 1 and 100 characters each.
_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9\-\.]{0,98}[A-Za-z0-9]|[A-Za-z0-9]?))/"
    r"(?P<repo>[A-Za-z0-9_\.\-]{1,100}?)"
    r"(?:\.git)?/?$"
)


class RepositoryInputError(ValueError):
    """Raised when a repository URL fails validation."""


@dataclass(frozen=True)
class RepositoryInput:
    """
    Normalized representation of a public GitHub repository supplied by the developer.

    Attributes:
        url:    The original, cleaned URL as supplied.
        owner:  Repository owner / organisation extracted from the URL.
        name:   Repository name extracted from the URL.
    """

    url: str
    owner: str
    name: str

    @classmethod
    def from_url(cls, raw_url: str) -> "RepositoryInput":
        """
        Parse and validate a public GitHub repository URL.

        Args:
            raw_url: URL string as supplied by the developer.

        Returns:
            A validated and normalized RepositoryInput instance.

        Raises:
            RepositoryInputError: If the URL is blank or not a recognised
                                  public GitHub repository URL.
        """
        url = raw_url.strip() if raw_url else ""
        if not url:
            raise RepositoryInputError("Repository URL must not be empty.")

        match = _GITHUB_URL_RE.match(url)
        if not match:
            raise RepositoryInputError(
                f"Invalid GitHub repository URL: {url!r}. "
                "Expected format: https://github.com/<owner>/<repo>"
            )

        return cls(
            url=url.rstrip("/"),
            owner=match.group("owner"),
            name=match.group("repo").removesuffix(".git"),
        )
