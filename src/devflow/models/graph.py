"""Repository-agnostic graph model for DevFlow Phase 6."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class GraphNodeType(str, Enum):
    CHANGE = "change"
    SOURCE = "source"
    TEST = "test"
    DOCUMENTATION = "documentation"
    DEPENDENCY = "dependency"
    CONFIGURATION = "configuration"
    HISTORICAL = "historical"
    RISK = "risk"
    OTHER = "other"


class GraphRelationship(str, Enum):
    RELEVANT_TO = "relevant_to"
    MODIFIES = "modifies"
    IMPACTS = "impacts"
    TESTED_BY = "tested_by"
    DOCUMENTED_BY = "documented_by"
    DEPENDS_ON = "depends_on"
    CONFIGURED_BY = "configured_by"
    HISTORICALLY_CHANGED_WITH = "historically_changed_with"
    HAS_RISK = "has_risk"
    RISK_FOR = "risk_for"
    RELATED_TO = "related_to"


@dataclass(frozen=True)
class GraphEvidence:
    artifact: str
    description: str
    evidence_type: str
    confidence: str = "confirmed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "description": self.description,
            "evidence_type": self.evidence_type,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    node_type: GraphNodeType
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)
    risk_severity: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type.value,
            "description": self.description,
            "metadata": self.metadata,
            "risk_severity": self.risk_severity,
        }
        return payload


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relationship: str
    description: str
    confidence: str = "confirmed"
    evidence: tuple[GraphEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "description": self.description,
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass
class ChangeImpactMap:
    repository_url: str
    owner: str
    name: str
    change_summary: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    error: Optional[str] = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_url": self.repository_url,
            "owner": self.owner,
            "name": self.name,
            "change_summary": self.change_summary,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "error": self.error,
            "generated_at": self.generated_at,
        }
