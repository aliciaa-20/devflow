"""
Impact analysis models for DevFlow Phase 4.

These dataclasses represent the structured, evidence-backed output of the
Impact Analysis phase. They are consumed by Phase 5 (Risk Analysis) and
Phase 6 (Change Impact Map) but carry no risk scoring themselves.

Every ImpactFinding must be traceable to its supporting evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EvidenceType(str, Enum):
    """
    Distinguishes how an impact finding is supported.

    DIRECT_EVIDENCE   — the supporting artifact is explicitly present in the
                        repository and directly establishes the relationship
                        (e.g. a changed file path, an import statement, a test
                        file that names the affected component, a dependency
                        manifest entry).

    DERIVED_RELATIONSHIP — the relationship is deterministically inferred from
                        structural evidence without requiring content inspection
                        (e.g. a test file whose name mirrors a source file name,
                        a dependency present in a manifest).

    INFERENCE         — the relationship is plausible given available evidence
                        but cannot be confirmed from repository content alone.
                        Must be clearly marked as such.
    """

    DIRECT_EVIDENCE = "DIRECT_EVIDENCE"
    DERIVED_RELATIONSHIP = "DERIVED_RELATIONSHIP"
    INFERENCE = "INFERENCE"


class RelationshipType(str, Enum):
    """Structured relationship types between a change and a repository artifact."""

    MODIFIES = "modifies"
    IMPORTS = "imports"
    DEPENDS_ON = "depends_on"
    TESTED_BY = "tested_by"
    DOCUMENTED_BY = "documented_by"
    CONFIGURED_BY = "configured_by"
    IMPACTS = "impacts"
    HISTORICALLY_CHANGED_WITH = "historically_changed_with"
    RELATED_TO = "related_to"


class EvidenceStrength(str, Enum):
    """
    Qualitative confidence label for an impact finding.

    CONFIRMED  — relationship is directly established by repository evidence.
    LIKELY     — relationship is strongly suggested by structural signals.
    POSSIBLE   — relationship is plausible but weakly supported.
    """

    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"


@dataclass(frozen=True)
class ImpactEvidence:
    """
    A single piece of supporting evidence for an impact finding.

    Attributes:
        artifact:       Repository-relative path or identifier of the evidence
                        artifact (e.g. a file path, a manifest entry).
        description:    Human-readable description of what this evidence shows.
        evidence_type:  How the evidence was established (direct / derived /
                        inference).
    """

    artifact: str
    description: str
    evidence_type: EvidenceType


@dataclass(frozen=True)
class ImpactFinding:
    """
    A single impact finding produced by Phase 4.

    Every finding identifies:
      - the affected artifact
      - the relationship type connecting the change to that artifact
      - a description of the potential impact
      - one or more supporting evidence items
      - the overall evidence strength / confidence

    Attributes:
        affected_artifact:  Repository-relative path of the artifact affected
                            by the change.
        relationship:       Structured relationship type.
        potential_impact:   Human-readable description of why this matters.
        evidence:           Tuple of evidence items supporting this finding.
        evidence_strength:  Overall confidence label.
        finding_type:       Broad category: "source", "test", "documentation",
                            "dependency", "configuration", "historical".
    """

    affected_artifact: str
    relationship: RelationshipType
    potential_impact: str
    evidence: tuple[ImpactEvidence, ...]
    evidence_strength: EvidenceStrength
    finding_type: str

    def primary_evidence_type(self) -> EvidenceType:
        """Return the weakest evidence type present (for conservative reporting)."""
        if not self.evidence:
            return EvidenceType.INFERENCE
        priority = {
            EvidenceType.DIRECT_EVIDENCE: 0,
            EvidenceType.DERIVED_RELATIONSHIP: 1,
            EvidenceType.INFERENCE: 2,
        }
        return max(self.evidence, key=lambda e: priority[e.evidence_type]).evidence_type


@dataclass
class ImpactAnalysis:
    """
    Structured impact analysis produced by Phase 4.

    Consumed by Phase 5 (Risk Analysis) and Phase 6 (Change Impact Map).

    Attributes:
        repository_url:     Original repository URL.
        owner:              Repository owner.
        name:               Repository name.
        change_summary:     Developer-supplied change description.
        findings:           All impact findings, ordered by evidence strength
                            (confirmed first).
        error:              Set if analysis failed; findings may be partial.
    """

    repository_url: str
    owner: str
    name: str
    change_summary: str
    findings: list[ImpactFinding] = field(default_factory=list)
    error: Optional[str] = None

    # ------------------------------------------------------------------
    # Convenience accessors (for downstream consumers)
    # ------------------------------------------------------------------

    def findings_by_type(self, finding_type: str) -> list[ImpactFinding]:
        """Return findings of a specific type."""
        return [f for f in self.findings if f.finding_type == finding_type]

    def source_findings(self) -> list[ImpactFinding]:
        return self.findings_by_type("source")

    def test_findings(self) -> list[ImpactFinding]:
        return self.findings_by_type("test")

    def documentation_findings(self) -> list[ImpactFinding]:
        return self.findings_by_type("documentation")

    def dependency_findings(self) -> list[ImpactFinding]:
        return self.findings_by_type("dependency")

    def configuration_findings(self) -> list[ImpactFinding]:
        return self.findings_by_type("configuration")

    def historical_findings(self) -> list[ImpactFinding]:
        return self.findings_by_type("historical")

    def confirmed_findings(self) -> list[ImpactFinding]:
        return [f for f in self.findings if f.evidence_strength == EvidenceStrength.CONFIRMED]
