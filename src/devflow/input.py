"""
DevFlow Phase 1 — Repository + Change Input.

Provides a single entry point, accept_input(), that receives a GitHub
repository URL and a change description and returns both as validated,
normalized internal representations.

No cloning, no API calls, no analysis is performed here.
"""

from __future__ import annotations

from typing import Optional

from devflow.models.change import ChangeRequest
from devflow.models.repository import RepositoryInput


def accept_input(
    repository_url: str,
    change_description: str,
    changed_files: Optional[list[str]] = None,
) -> tuple[RepositoryInput, ChangeRequest]:
    """
    Accept and validate the two primary DevFlow inputs.

    Args:
        repository_url:      Public GitHub repository URL.
        change_description:  Plain-text description of the proposed change.
        changed_files:       Optional list of file paths known to be affected.

    Returns:
        A (RepositoryInput, ChangeRequest) tuple, both fully validated and
        normalized, ready for downstream pipeline stages.

    Raises:
        RepositoryInputError: If the repository URL is invalid.
        ChangeRequestError:   If the change description is blank.
    """
    repository = RepositoryInput.from_url(repository_url)
    change = ChangeRequest.from_inputs(change_description, changed_files)
    return repository, change
