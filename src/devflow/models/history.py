"""
Historical context models for DevFlow Phase 3.

These dataclasses represent structured, evidence-backed Git history context
produced for repository artifacts relevant to a developer change.

They are consumed by Phase 4 (Impact Analysis) and Phase 6 (Change Impact Map)
but carry no analysis themselves — only Git-derived evidence.

Every historical finding must be traceable to its Git evidence source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class HistoricalCommit:
    """
    A single Git commit identified as relevant to a repository artifact.

    All fields are extracted directly from Git output. Fields that were not
    available in the retrieved Git history are recorded as None.

    Attributes:
        hash:           Full commit hash (40-character SHA-1).
        short_hash:     Abbreviated commit hash (typically 7–12 characters).
        message:        The first line of the commit message (subject line).
        author:         Author name as recorded in git log, or None if unavailable.
        date_iso:       Commit date in ISO-8601 format (YYYY-MM-DD HH:MM:SS tz),
                        or None if unavailable.
        refs:           Raw references found in the commit message
                        (e.g. "#142"). These are recorded as-is; DevFlow does NOT
                        assert that they correspond to GitHub Issues or Pull Requests
                        unless external evidence confirms it.
    """

    hash: str
    short_hash: str
    message: str
    author: Optional[str]
    date_iso: Optional[str]
    refs: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalEvidence:
    """
    The evidence connecting a commit to a repository artifact.

    Attributes:
        artifact_path:      Repository-relative path of the artifact.
        commit_hash:        Full hash of the associated commit.
        description:        Human-readable description of the evidence
                            (e.g. "Git commit abc123 modified src/auth/session.py").
        relevance_reason:   Why this commit is considered relevant to the artifact.
        evidence_type:      "direct_modification" | "message_reference"
    """

    artifact_path: str
    commit_hash: str
    description: str
    relevance_reason: str
    evidence_type: str  # "direct_modification" | "message_reference"


@dataclass(frozen=True)
class ArtifactHistory:
    """
    The collected Git history for a single repository artifact.

    Attributes:
        artifact_path:  Repository-relative path of the artifact.
        commits:        List of relevant commits (most-recent first).
        evidence:       Evidence items connecting each commit to this artifact.
        note:           Optional note if history is limited or absent.
    """

    artifact_path: str
    commits: tuple[HistoricalCommit, ...]
    evidence: tuple[HistoricalEvidence, ...]
    note: Optional[str] = None

    def has_history(self) -> bool:
        """Return True if at least one commit was found for this artifact."""
        return len(self.commits) > 0


@dataclass
class RepositoryHistory:
    """
    Structured Git history context for a repository, scoped to the relevant
    artifacts identified by Phase 2.

    Consumed by Phase 4 (Impact Analysis) and Phase 6 (Change Impact Map).

    Attributes:
        repository_url:     Original repository URL.
        owner:              Repository owner.
        name:               Repository name.
        change_summary:     Developer-supplied change description.
        artifact_histories: History per relevant artifact, keyed by path.
        total_commits_found: Total distinct commit hashes discovered across
                             all artifacts.
        error:              Set if history extraction failed; histories may be
                            partial or empty in that case.
    """

    repository_url: str
    owner: str
    name: str
    change_summary: str
    artifact_histories: dict[str, ArtifactHistory] = field(default_factory=dict)
    total_commits_found: int = 0
    error: Optional[str] = None

    def artifacts_with_history(self) -> list[ArtifactHistory]:
        """Return artifact histories that have at least one commit."""
        return [h for h in self.artifact_histories.values() if h.has_history()]

    def artifacts_without_history(self) -> list[ArtifactHistory]:
        """Return artifact histories for which no commits were found."""
        return [h for h in self.artifact_histories.values() if not h.has_history()]

    def all_commits(self) -> list[HistoricalCommit]:
        """Return a deduplicated list of all commits across all artifacts."""
        seen: dict[str, HistoricalCommit] = {}
        for hist in self.artifact_histories.values():
            for commit in hist.commits:
                if commit.hash not in seen:
                    seen[commit.hash] = commit
        return list(seen.values())
