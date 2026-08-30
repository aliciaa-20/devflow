"""
Repository context models for DevFlow Phase 2.

These dataclasses represent the structured, evidence-backed output of the
Context Reconstruction phase. They are consumed by future phases (Impact
Analysis, Change Impact Map, etc.) but carry no analysis themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from devflow.models.repository_graph import RepositoryKnowledgeGraph


class ArtifactKind(str, Enum):
    """Broad classification of a repository artifact."""

    SOURCE = "source"
    TEST = "test"
    DOCUMENTATION = "documentation"
    DEPENDENCY = "dependency"
    CONFIGURATION = "configuration"
    OTHER = "other"


class RelevanceReason(str, Enum):
    """The reason an artifact was considered relevant to the change."""

    CHANGED_FILE = "changed_file"       # Explicitly listed in change request
    KEYWORD_MATCH = "keyword_match"     # Description keyword found in path/content snippet
    TEST_FOR_CHANGED = "test_for_changed"  # Test whose name overlaps a changed file
    DEPENDENCY_MANIFEST = "dependency_manifest"  # Project dependency file (always relevant)
    CONFIGURATION = "configuration"     # Project configuration file (always relevant)
    DOCUMENTATION = "documentation"     # Project documentation (always relevant)
    ENTRY_POINT = "entry_point"         # Identified as an application entry point


@dataclass(frozen=True)
class ContextArtifact:
    """
    A single repository artifact identified as relevant to the developer change.

    Attributes:
        path:       Path relative to the repository root.
        kind:       Broad artifact classification.
        reason:     Why this artifact was considered relevant.
        evidence:   Short human-readable description of the evidence that
                    established relevance (e.g. "path appears in changed_files",
                    "keyword 'auth' found in path").
        confidence: Qualitative confidence label: "confirmed", "likely", "possible".
    """

    path: str
    kind: ArtifactKind
    reason: RelevanceReason
    evidence: str
    confidence: str = "confirmed"


@dataclass
class RepositoryContext:
    """
    Structured repository context produced by the Context Reconstruction phase.

    Consumed by Phase 3 (Historical Context) and Phase 4 (Impact Analysis).

    Attributes:
        repository_url:   Original repository URL.
        owner:            Repository owner extracted from URL.
        name:             Repository name extracted from URL.
        change_summary:   Developer-supplied change description.
        artifacts:        Relevant artifacts with reasons and evidence.
        all_files:        Full list of file paths found in the repository
                          (relative to repo root), for downstream use.
        entry_points:     Files identified as likely application entry points.
        retrieval_path:   Local path where the repository was inspected
                          (may be None if cleaned up).
        repository_graph: Repository Knowledge Graph built from the same clone,
                          carrying the real static import and test-association
                          edges.  Optional: a graph failure never blocks
                          context reconstruction, so downstream phases must
                          treat this as best-effort structural evidence.
        error:            Set if retrieval or inspection failed; other fields
                          may be empty in that case.
    """

    repository_url: str
    owner: str
    name: str
    change_summary: str
    artifacts: list[ContextArtifact] = field(default_factory=list)
    all_files: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    retrieval_path: Optional[str] = None
    repository_graph: Optional[RepositoryKnowledgeGraph] = None
    error: Optional[str] = None

    def relevant_sources(self) -> list[ContextArtifact]:
        return [a for a in self.artifacts if a.kind == ArtifactKind.SOURCE]

    def relevant_tests(self) -> list[ContextArtifact]:
        return [a for a in self.artifacts if a.kind == ArtifactKind.TEST]

    def relevant_docs(self) -> list[ContextArtifact]:
        return [a for a in self.artifacts if a.kind == ArtifactKind.DOCUMENTATION]

    def relevant_dependencies(self) -> list[ContextArtifact]:
        return [a for a in self.artifacts if a.kind == ArtifactKind.DEPENDENCY]

    def relevant_configs(self) -> list[ContextArtifact]:
        return [a for a in self.artifacts if a.kind == ArtifactKind.CONFIGURATION]
