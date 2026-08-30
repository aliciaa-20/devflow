"""Structured resolution models for DevFlow Phase 8 (Bob Resolution).

Phase 8 is human-in-the-loop: there is no programmatic Bob SDK anywhere in
this codebase, so investigation and file edits happen outside src/devflow --
performed by a developer running Bob's `resolver` custom mode in their own
environment against their own local checkout. DevFlow's role here is the two
human-approval gates, deterministic ingestion of Bob's structured markdown
output, and running the one thing it can verify for real: the actual test
command and a real `git diff`, rather than trusting a claimed outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional


class ApprovalDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ResolutionStatus(str, Enum):
    REQUESTED = "requested"
    INVESTIGATION_APPROVED = "investigation_approved"
    REJECTED_BEFORE_INVESTIGATION = "rejected_before_investigation"
    FIX_PROPOSED = "fix_proposed"
    FIX_APPROVED = "fix_approved"
    REJECTED_BEFORE_APPLY = "rejected_before_apply"
    VALIDATED = "validated"


class FinalStatus(str, Enum):
    """Mirrors .bob/custom_modes.yaml's resolver-mode output vocabulary exactly."""

    RESOLVED = "RESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    NOT_RESOLVED = "NOT_RESOLVED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class ResolutionIngestError(ValueError):
    """Raised when Bob's raw output does not match the expected structure.

    Never guess at missing sections -- an unparsable investigation or result
    report must fail loudly rather than silently producing partial data.
    """


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ApprovalGate:
    """A single human-approval decision at one of the two Phase 8 gates."""

    gate: str  # "investigate" | "apply_fix"
    decision: ApprovalDecision
    decided_by: str
    decided_at: str = field(default_factory=_utc_now)
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "decision": self.decision.value,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ApprovalGate":
        return cls(
            gate=str(payload["gate"]),
            decision=ApprovalDecision(payload["decision"]),
            decided_by=str(payload["decided_by"]),
            decided_at=str(payload.get("decided_at", "")),
            note=payload.get("note"),
        )


@dataclass(frozen=True)
class ProposedFix:
    """Ingested verbatim from Bob resolver mode's "Propose the Fix" output."""

    summary: str
    root_cause: str
    files_to_modify: tuple[str, ...]
    tests_to_add_or_update: tuple[str, ...]
    validation_plan: str
    raw_bob_output_path: str
    proposed_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "root_cause": self.root_cause,
            "files_to_modify": list(self.files_to_modify),
            "tests_to_add_or_update": list(self.tests_to_add_or_update),
            "validation_plan": self.validation_plan,
            "raw_bob_output_path": self.raw_bob_output_path,
            "proposed_at": self.proposed_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProposedFix":
        return cls(
            summary=str(payload["summary"]),
            root_cause=str(payload["root_cause"]),
            files_to_modify=tuple(payload.get("files_to_modify", ())),
            tests_to_add_or_update=tuple(payload.get("tests_to_add_or_update", ())),
            validation_plan=str(payload["validation_plan"]),
            raw_bob_output_path=str(payload["raw_bob_output_path"]),
            proposed_at=str(payload.get("proposed_at", "")),
        )


@dataclass(frozen=True)
class TestExecutionRecord:
    """Only ever built from an actually-executed subprocess -- never claimed."""

    command: str
    passed: bool
    exit_code: int
    output_excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "output_excerpt": self.output_excerpt,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TestExecutionRecord":
        return cls(
            command=str(payload["command"]),
            passed=bool(payload["passed"]),
            exit_code=int(payload["exit_code"]),
            output_excerpt=str(payload["output_excerpt"]),
        )


@dataclass(frozen=True)
class ResolutionOutcome:
    """The final, DevFlow-verified record of a resolution attempt."""

    modified_files: tuple[str, ...]
    change_rationale: str
    tests_added_or_updated: tuple[str, ...]
    tests_executed: tuple[TestExecutionRecord, ...]
    final_status: FinalStatus
    remaining_risks: tuple[str, ...]
    raw_bob_output_path: str
    # What Bob's own closing report claimed, preserved even when DevFlow's
    # executed tests forced a different final_status. Keeping both makes the
    # disagreement inspectable instead of silently overwritten -- the point of
    # DevFlow owning validation is that it can contradict the agent.
    bob_claimed_status: Optional[FinalStatus] = None
    completed_at: str = field(default_factory=_utc_now)

    @property
    def contradicted_bob(self) -> bool:
        """Whether DevFlow's verified result differs from Bob's claim."""
        return (
            self.bob_claimed_status is not None
            and self.bob_claimed_status != self.final_status
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "modified_files": list(self.modified_files),
            "change_rationale": self.change_rationale,
            "tests_added_or_updated": list(self.tests_added_or_updated),
            "tests_executed": [item.to_dict() for item in self.tests_executed],
            "final_status": self.final_status.value,
            "bob_claimed_status": (
                self.bob_claimed_status.value if self.bob_claimed_status else None
            ),
            "contradicted_bob": self.contradicted_bob,
            "remaining_risks": list(self.remaining_risks),
            "raw_bob_output_path": self.raw_bob_output_path,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResolutionOutcome":
        return cls(
            modified_files=tuple(payload.get("modified_files", ())),
            change_rationale=str(payload["change_rationale"]),
            tests_added_or_updated=tuple(payload.get("tests_added_or_updated", ())),
            tests_executed=tuple(
                TestExecutionRecord.from_dict(item) for item in payload.get("tests_executed", ())
            ),
            final_status=FinalStatus(payload["final_status"]),
            bob_claimed_status=(
                FinalStatus(payload["bob_claimed_status"])
                if payload.get("bob_claimed_status")
                else None
            ),
            remaining_risks=tuple(payload.get("remaining_risks", ())),
            raw_bob_output_path=str(payload["raw_bob_output_path"]),
            completed_at=str(payload.get("completed_at", "")),
        )


@dataclass
class ResolutionRequest:
    """The full, evolving state of one finding's resolution session.

    This whole object is the bob_sessions/<id>/state.json payload -- the
    single source of truth for a resolution's current status.
    """

    id: str
    repository_url: str
    owner: str
    name: str
    change_summary: str
    finding_id: str
    finding_snapshot: dict[str, Any]
    graph_node_id: Optional[str] = None
    status: ResolutionStatus = ResolutionStatus.REQUESTED
    created_at: str = field(default_factory=_utc_now)
    investigate_gate: Optional[ApprovalGate] = None
    proposed_fix: Optional[ProposedFix] = None
    apply_gate: Optional[ApprovalGate] = None
    outcome: Optional[ResolutionOutcome] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repository_url": self.repository_url,
            "owner": self.owner,
            "name": self.name,
            "change_summary": self.change_summary,
            "finding_id": self.finding_id,
            "finding_snapshot": self.finding_snapshot,
            "graph_node_id": self.graph_node_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "investigate_gate": self.investigate_gate.to_dict() if self.investigate_gate else None,
            "proposed_fix": self.proposed_fix.to_dict() if self.proposed_fix else None,
            "apply_gate": self.apply_gate.to_dict() if self.apply_gate else None,
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResolutionRequest":
        return cls(
            id=str(payload["id"]),
            repository_url=str(payload["repository_url"]),
            owner=str(payload["owner"]),
            name=str(payload["name"]),
            change_summary=str(payload["change_summary"]),
            finding_id=str(payload["finding_id"]),
            finding_snapshot=dict(payload["finding_snapshot"]),
            graph_node_id=payload.get("graph_node_id"),
            status=ResolutionStatus(payload.get("status", ResolutionStatus.REQUESTED.value)),
            created_at=str(payload.get("created_at", "")),
            investigate_gate=(
                ApprovalGate.from_dict(payload["investigate_gate"])
                if payload.get("investigate_gate")
                else None
            ),
            proposed_fix=(
                ProposedFix.from_dict(payload["proposed_fix"])
                if payload.get("proposed_fix")
                else None
            ),
            apply_gate=(
                ApprovalGate.from_dict(payload["apply_gate"]) if payload.get("apply_gate") else None
            ),
            outcome=(
                ResolutionOutcome.from_dict(payload["outcome"]) if payload.get("outcome") else None
            ),
            error=payload.get("error"),
        )
