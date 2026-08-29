"""Structured, evidence-backed risk models for DevFlow Phase 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from devflow.models.impact import EvidenceStrength, EvidenceType, ImpactEvidence


class RiskCategory(str, Enum):
    CODE = "code"
    REGRESSION = "regression"
    TEST_GAP = "test_gap"
    SECURITY = "security"
    DEPENDENCY = "dependency"
    HISTORICAL = "historical"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RiskFinding:
    """A risk derived from Phase 2--4 evidence, never a claimed defect."""

    severity: RiskSeverity
    category: RiskCategory
    explanation: str
    affected_artifacts: tuple[str, ...]
    evidence: tuple[ImpactEvidence, ...]
    recommended_action: str
    evidence_strength: EvidenceStrength
    assessment_type: EvidenceType

    @property
    def is_inference(self) -> bool:
        """Whether the risk conclusion, rather than its evidence, is inferred."""
        return self.assessment_type == EvidenceType.INFERENCE


@dataclass
class RiskAnalysis:
    """Phase 5 output, ordered from highest to lowest evidence-based severity."""

    repository_url: str
    owner: str
    name: str
    change_summary: str
    risks: list[RiskFinding] = field(default_factory=list)
    error: Optional[str] = None

    def risks_by_category(self, category: RiskCategory) -> list[RiskFinding]:
        return [risk for risk in self.risks if risk.category == category]

