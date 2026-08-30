"""Models for evidence-backed finding prioritization.

Prioritization is the one place in DevFlow where a language model influences
output.  Its authority is deliberately narrow: it may reorder findings DevFlow
already produced and explain why, and nothing else.  It cannot introduce a
finding, remove one, change a severity, or state a repository fact.

``PrioritizationSource`` records which path produced a result so the report and
the CLI can always tell the developer whether they are looking at model
judgment or deterministic ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class PrioritizationSource(str, Enum):
    """How a ranking was produced."""

    WATSONX = "watsonx"           # IBM watsonx.ai / Granite judgment
    DETERMINISTIC = "deterministic"  # DevFlow's own severity/evidence ordering


@dataclass(frozen=True)
class RankedFinding:
    """One finding in priority order.

    Attributes:
        finding_id: Must match a finding DevFlow produced. Never invented.
        rank:       1-based position; 1 is investigate-first.
        rationale:  Short justification. For watsonx rankings this is model
                    text and is labelled as interpretation, not observed fact.
        severity:   Carried through from the deterministic finding.
        title:      Carried through from the deterministic finding.
        source:     Which path assigned this position.
    """

    finding_id: str
    rank: int
    rationale: str
    severity: Optional[str] = None
    title: Optional[str] = None
    source: PrioritizationSource = PrioritizationSource.DETERMINISTIC

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rank": self.rank,
            "rationale": self.rationale,
            "severity": self.severity,
            "title": self.title,
            "source": self.source.value,
        }


@dataclass
class Prioritization:
    """The full ranked finding list plus provenance.

    ``discarded_finding_ids`` records identifiers the model returned that do
    not exist in DevFlow's own findings.  Keeping this visible is deliberate:
    it is the audit trail proving the repository, not the model, has the final
    say over what is real.
    """

    source: PrioritizationSource
    rankings: list[RankedFinding] = field(default_factory=list)
    model_id: Optional[str] = None
    discarded_finding_ids: list[str] = field(default_factory=list)
    appended_finding_ids: list[str] = field(default_factory=list)
    from_cache: bool = False
    error: Optional[str] = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    @property
    def used_watsonx(self) -> bool:
        return self.source == PrioritizationSource.WATSONX

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "model_id": self.model_id,
            "rankings": [item.to_dict() for item in self.rankings],
            "discarded_finding_ids": list(self.discarded_finding_ids),
            "appended_finding_ids": list(self.appended_finding_ids),
            "from_cache": self.from_cache,
            "error": self.error,
            "generated_at": self.generated_at,
        }


class WatsonxError(RuntimeError):
    """Raised inside the watsonx client; never propagates past the judge."""
