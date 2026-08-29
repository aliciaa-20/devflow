"""Structured developer report models for DevFlow Phase 7."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class ReportEvidence:
    """A single evidence item preserved from upstream analysis."""

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
class ReportFinding:
    """A traceable report finding with optional graph linkage."""

    id: str
    category: str
    title: str
    description: str
    affected_artifacts: tuple[str, ...] = ()
    relationship: Optional[str] = None
    potential_impact: Optional[str] = None
    severity: Optional[str] = None
    evidence: tuple[ReportEvidence, ...] = ()
    evidence_strength: Optional[str] = None
    is_inference: bool = False
    recommendation: Optional[str] = None
    graph_node_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "affected_artifacts": list(self.affected_artifacts),
            "relationship": self.relationship,
            "potential_impact": self.potential_impact,
            "severity": self.severity,
            "evidence": [item.to_dict() for item in self.evidence],
            "evidence_strength": self.evidence_strength,
            "is_inference": self.is_inference,
            "recommendation": self.recommendation,
            "graph_node_id": self.graph_node_id,
        }


@dataclass(frozen=True)
class ReportAction:
    """A prioritized next action derived from risk recommendations."""

    priority: int
    action: str
    source_finding_id: str
    severity: str
    graph_node_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority": self.priority,
            "action": self.action,
            "source_finding_id": self.source_finding_id,
            "severity": self.severity,
            "graph_node_id": self.graph_node_id,
        }


@dataclass(frozen=True)
class ReportEvidenceGap:
    """Explicit record that evidence was unavailable or incomplete."""

    description: str
    affected_artifact: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "affected_artifact": self.affected_artifact,
        }


@dataclass
class DeveloperReport:
    """Phase 7 developer-facing report synthesized from Phases 2–5."""

    repository_url: str
    owner: str
    name: str
    change_summary: str
    changed_files: tuple[str, ...] = field(default_factory=tuple)
    findings: list[ReportFinding] = field(default_factory=list)
    next_actions: list[ReportAction] = field(default_factory=list)
    evidence_gaps: list[ReportEvidenceGap] = field(default_factory=list)
    error: Optional[str] = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> dict[str, Any]:
        context_findings = [f for f in self.findings if f.category == "context"]
        impact_findings = [f for f in self.findings if f.category == "impact"]
        historical_findings = [f for f in self.findings if f.category == "historical"]
        risk_findings = [f for f in self.findings if f.category == "risk"]

        severities = [f.severity for f in risk_findings if f.severity]
        highest_risk = _highest_severity(severities) if severities else None

        return {
            "repository_url": self.repository_url,
            "owner": self.owner,
            "name": self.name,
            "change_summary": self.change_summary,
            "changed_files": list(self.changed_files),
            "error": self.error,
            "generated_at": self.generated_at,
            "sections": {
                "change": {
                    "summary": self.change_summary,
                    "changed_files": list(self.changed_files),
                },
                "context": {
                    "artifact_count": len(context_findings),
                    "findings": [finding.to_dict() for finding in context_findings],
                },
                "impact": {
                    "finding_count": len(impact_findings),
                    "findings": [finding.to_dict() for finding in impact_findings],
                },
                "history": {
                    "finding_count": len(historical_findings),
                    "findings": [finding.to_dict() for finding in historical_findings],
                },
                "risk": {
                    "finding_count": len(risk_findings),
                    "highest_severity": highest_risk,
                    "findings": [finding.to_dict() for finding in risk_findings],
                },
            },
            "findings": [finding.to_dict() for finding in self.findings],
            "next_actions": [action.to_dict() for action in self.next_actions],
            "evidence_gaps": [gap.to_dict() for gap in self.evidence_gaps],
        }


def _highest_severity(severities: list[str]) -> str:
    order = ["critical", "high", "medium", "low"]
    best = "low"
    best_rank = len(order)
    for severity in severities:
        normalized = (severity or "low").lower()
        if normalized not in order:
            continue
        rank = order.index(normalized)
        if rank < best_rank:
            best_rank = rank
            best = normalized
    return best
