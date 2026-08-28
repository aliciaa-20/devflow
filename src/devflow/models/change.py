"""
Change request model for DevFlow.

Accepts a developer change description and an optional list of changed files.
No analysis is performed here; this is purely a structured input container.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class ChangeRequestError(ValueError):
    """Raised when a change request fails validation."""


@dataclass(frozen=True)
class ChangeRequest:
    """
    Normalized representation of a developer's proposed change.

    Attributes:
        description:    Plain-text description of the change the developer
                        wants to review or implement.
        changed_files:  Optional list of file paths the developer knows are
                        affected. May be empty; downstream stages must not
                        assume this list is exhaustive.
    """

    description: str
    changed_files: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_inputs(
        cls,
        description: str,
        changed_files: Optional[list[str]] = None,
    ) -> "ChangeRequest":
        """
        Validate and normalise change request inputs.

        Args:
            description:   Developer-supplied change description.
            changed_files: Optional list of file paths known to be affected.

        Returns:
            A validated ChangeRequest instance.

        Raises:
            ChangeRequestError: If the description is blank.
        """
        desc = description.strip() if description else ""
        if not desc:
            raise ChangeRequestError("Change description must not be empty.")

        files: tuple[str, ...] = tuple()
        if changed_files is not None:
            stripped = [f.strip() for f in changed_files if f.strip()]
            files = tuple(stripped)

        return cls(description=desc, changed_files=files)
