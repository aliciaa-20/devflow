"""Structured, repository-wide graph models for DevFlow.

This module is intentionally independent from the Change Impact Map models.
It defines only JSON-safe data contracts; it does not retrieve repositories,
build relationships, write payload files, or integrate with the frontend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional


class RepositoryNodeType(str, Enum):
    REPOSITORY = "repository"
    DIRECTORY = "directory"
    SOURCE_FILE = "source_file"
    TEST_FILE = "test_file"
    DOCUMENTATION_FILE = "documentation_file"
    CONFIGURATION_FILE = "configuration_file"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    EXTERNAL_DEPENDENCY = "external_dependency"
    ENTRY_POINT = "entry_point"
    GENERATED_FILE = "generated_file"
    OTHER_FILE = "other_file"

    # Compatibility aliases for the existing untracked prototype. New code
    # should use the explicit *_FILE and EXTERNAL_DEPENDENCY names above.
    SOURCE = SOURCE_FILE
    TEST = TEST_FILE
    DOCUMENTATION = DOCUMENTATION_FILE
    CONFIGURATION = CONFIGURATION_FILE
    DEPENDENCY = EXTERNAL_DEPENDENCY


class RepositoryRelationshipType(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    IMPORTED_BY = "imported_by"
    DEPENDS_ON = "depends_on"
    DECLARES_DEPENDENCY = "declares_dependency"
    TESTED_BY = "tested_by"
    CONFIGURED_BY = "configured_by"
    DOCUMENTED_BY = "documented_by"
    ENTRY_POINT_FOR = "entry_point_for"
    REFERENCES = "references"


class RepositoryEvidenceType(str, Enum):
    DIRECT_FILESYSTEM = "direct_filesystem"
    DIRECT_STATIC_IMPORT = "direct_static_import"
    MANIFEST_DECLARATION = "manifest_declaration"
    DERIVED_RELATIONSHIP = "derived_relationship"
    LIKELY_RELATIONSHIP = "likely_relationship"


class RepositoryConfidence(str, Enum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"


def repository_node_id(name: str) -> str:
    return f"repository:{name}"


def directory_node_id(path: str) -> str:
    return f"directory:{path.strip('/')}"


def file_node_id(node_type: RepositoryNodeType, path: str) -> str:
    """Return a stable namespaced ID for a repository file node."""
    return f"{node_type.value}:{path.strip('/')}"


def external_dependency_node_id(name: str) -> str:
    return f"{RepositoryNodeType.EXTERNAL_DEPENDENCY.value}:{name}"


def _json_safe(value: Any) -> Any:
    """Validate and normalize metadata into JSON-compatible values."""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


@dataclass(frozen=True)
class RepositoryGraphEvidence:
    artifact: str
    description: str
    evidence_type: RepositoryEvidenceType = RepositoryEvidenceType.DIRECT_FILESYSTEM
    confidence: RepositoryConfidence = RepositoryConfidence.CONFIRMED

    def __post_init__(self) -> None:
        """Normalize the prototype's evidence labels into the explicit contract."""
        legacy_types = {
            "repository_evidence": RepositoryEvidenceType.DIRECT_FILESYSTEM,
            "static_analysis": RepositoryEvidenceType.DIRECT_STATIC_IMPORT,
            "name_similarity": RepositoryEvidenceType.DERIVED_RELATIONSHIP,
        }
        evidence_type = legacy_types.get(self.evidence_type, self.evidence_type)
        if not isinstance(evidence_type, RepositoryEvidenceType):
            evidence_type = RepositoryEvidenceType(evidence_type)
        confidence = self.confidence
        if not isinstance(confidence, RepositoryConfidence):
            confidence = RepositoryConfidence(confidence)
        object.__setattr__(self, "evidence_type", evidence_type)
        object.__setattr__(self, "confidence", confidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "description": self.description,
            "evidence_type": self.evidence_type.value,
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepositoryGraphEvidence":
        return cls(
            artifact=str(payload["artifact"]),
            description=str(payload["description"]),
            evidence_type=RepositoryEvidenceType(payload.get("evidence_type", "direct_filesystem")),
            confidence=RepositoryConfidence(payload.get("confidence", "confirmed")),
        )


@dataclass(frozen=True)
class RepositoryGraphNode:
    id: str
    label: str
    node_type: RepositoryNodeType
    description: str
    path: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[RepositoryGraphEvidence, ...] = ()
    confidence: RepositoryConfidence = RepositoryConfidence.CONFIRMED

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type.value,
            "path": self.path,
            "description": self.description,
            "metadata": _json_safe(self.metadata),
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepositoryGraphNode":
        return cls(
            id=str(payload["id"]),
            label=str(payload["label"]),
            node_type=RepositoryNodeType(payload["node_type"]),
            path=payload.get("path"),
            description=str(payload["description"]),
            metadata=dict(payload.get("metadata", {})),
            evidence=tuple(RepositoryGraphEvidence.from_dict(item) for item in payload.get("evidence", ())),
            confidence=RepositoryConfidence(payload.get("confidence", "confirmed")),
        )


@dataclass(frozen=True)
class RepositoryGraphEdge:
    source: str
    target: str
    relationship: RepositoryRelationshipType
    description: str
    evidence: tuple[RepositoryGraphEvidence, ...] = ()
    confidence: RepositoryConfidence = RepositoryConfidence.CONFIRMED
    relationship_strength: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship.value,
            "description": self.description,
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence.value,
            "relationship_strength": self.relationship_strength,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepositoryGraphEdge":
        return cls(
            source=str(payload["source"]),
            target=str(payload["target"]),
            relationship=RepositoryRelationshipType(payload["relationship"]),
            description=str(payload["description"]),
            evidence=tuple(RepositoryGraphEvidence.from_dict(item) for item in payload.get("evidence", ())),
            confidence=RepositoryConfidence(payload.get("confidence", "confirmed")),
            relationship_strength=payload.get("relationship_strength"),
        )


@dataclass
class RepositoryKnowledgeGraph:
    repository_url: str
    owner: str
    name: str
    default_branch: Optional[str] = None
    nodes: list[RepositoryGraphNode] = field(default_factory=list)
    edges: list[RepositoryGraphEdge] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    analysis_limits: Optional[dict[str, Any]] = None
    truncation: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic, JSON-safe representation of this graph."""
        return {
            "repository_url": self.repository_url,
            "owner": self.owner,
            "name": self.name,
            "default_branch": self.default_branch,
            "nodes": [node.to_dict() for node in sorted(self.nodes, key=lambda node: node.id)],
            "edges": [
                edge.to_dict()
                for edge in sorted(
                    self.edges,
                    key=lambda edge: (edge.relationship.value, edge.source, edge.target),
                )
            ],
            "summary": _json_safe(self.summary),
            "analysis_limits": _json_safe(self.analysis_limits) if self.analysis_limits is not None else None,
            "truncation": _json_safe(self.truncation) if self.truncation is not None else None,
            "error": self.error,
            "generated_at": self.generated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepositoryKnowledgeGraph":
        return cls(
            repository_url=str(payload["repository_url"]),
            owner=str(payload["owner"]),
            name=str(payload["name"]),
            default_branch=payload.get("default_branch"),
            nodes=[RepositoryGraphNode.from_dict(item) for item in payload.get("nodes", ())],
            edges=[RepositoryGraphEdge.from_dict(item) for item in payload.get("edges", ())],
            summary=dict(payload.get("summary", {})),
            analysis_limits=dict(payload["analysis_limits"]) if payload.get("analysis_limits") is not None else None,
            truncation=dict(payload["truncation"]) if payload.get("truncation") is not None else None,
            error=payload.get("error"),
            generated_at=str(payload.get("generated_at", "")),
        )

    @classmethod
    def from_json(cls, payload: str) -> "RepositoryKnowledgeGraph":
        return cls.from_dict(json.loads(payload))
