"""Deterministic Phase 7 developer report synthesis from Phases 2–5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from devflow.map._ids import artifact_node_id, change_node_id, history_node_id, risk_node_id
from devflow.models.context import RelevanceReason, RepositoryContext
from devflow.models.history import ArtifactHistory, RepositoryHistory
from devflow.models.impact import EvidenceType, ImpactAnalysis, ImpactEvidence, ImpactFinding
from devflow.models.prioritization import Prioritization
from devflow.models.report import (
    DeveloperReport,
    ReportAction,
    ReportEvidence,
    ReportEvidenceGap,
    ReportFinding,
)
from devflow.models.risk import RiskAnalysis, RiskFinding, RiskSeverity


_SEVERITY_ORDER = {
    RiskSeverity.CRITICAL: 0,
    RiskSeverity.HIGH: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.LOW: 3,
}


def build_developer_report(
    context: RepositoryContext,
    impact: ImpactAnalysis,
    risk: RiskAnalysis,
    history: Optional[RepositoryHistory] = None,
) -> DeveloperReport:
    """Synthesize a developer report from structured upstream analysis outputs."""
    report = DeveloperReport(
        repository_url=context.repository_url,
        owner=context.owner,
        name=context.name,
        change_summary=context.change_summary,
        changed_files=_changed_files(context),
    )

    errors: list[str] = []
    if context.error:
        errors.append(f"Phase 2 context: {context.error}")
    if impact.error:
        errors.append(f"Phase 4 impact: {impact.error}")
    if risk.error:
        errors.append(f"Phase 5 risk: {risk.error}")
    if history and history.error:
        errors.append(f"Phase 3 history: {history.error}")

    if errors:
        report.error = "; ".join(errors)
        report.evidence_gaps.append(
            ReportEvidenceGap(
                description="Upstream analysis reported errors; report content may be incomplete.",
            )
        )

    impact_artifacts = {finding.affected_artifact for finding in impact.findings}
    findings: list[ReportFinding] = []

    findings.extend(_context_findings(context, impact_artifacts))
    findings.extend(_impact_findings(impact, impact_artifacts))
    findings.extend(_historical_findings(history, impact_artifacts))
    findings.extend(_risk_findings(risk))

    report.findings = findings
    report.next_actions = _next_actions(findings)
    report.evidence_gaps.extend(_evidence_gaps(context, impact, risk, history, impact_artifacts))
    return report


def serialize_developer_report(
    report: DeveloperReport,
    output_path: str | Path,
    *,
    prioritization: Optional[Prioritization] = None,
) -> Path:
    """Write the canonical JSON payload for the Phase 7 developer report.

    ``prioritization`` is optional and purely additive: report synthesis stays
    deterministic and offline, and the ranking (which may involve a watsonx
    call) is attached by the caller after the fact.
    """
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = report.to_dict()
    if prioritization is not None:
        document["prioritization"] = prioritization.to_dict()
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    target.write_text(payload, encoding="utf-8")
    return target


def write_frontend_report_payload(
    report: DeveloperReport,
    *,
    frontend_dir: Optional[str | Path] = None,
    prioritization: Optional[Prioritization] = None,
) -> Path:
    """Persist the report payload in the Vite frontend public directory."""
    repo_root = Path(frontend_dir) if frontend_dir else Path(__file__).resolve().parents[3]
    target = repo_root / "frontend" / "public" / "devflow-report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return serialize_developer_report(report, target, prioritization=prioritization)


def _changed_files(context: RepositoryContext) -> tuple[str, ...]:
    return tuple(
        sorted(
            artifact.path
            for artifact in context.artifacts
            if artifact.reason == RelevanceReason.CHANGED_FILE
        )
    )


def _context_findings(
    context: RepositoryContext,
    impact_artifacts: set[str],
) -> list[ReportFinding]:
    findings: list[ReportFinding] = []
    for artifact in sorted(context.artifacts, key=lambda item: item.path):
        evidence_type = _confidence_to_evidence_type(artifact.confidence)
        graph_id = artifact_node_id(artifact.path) if artifact.path in impact_artifacts else None
        findings.append(
            ReportFinding(
                id=f"context:{artifact.path}",
                category="context",
                title=artifact.path,
                description=artifact.evidence,
                affected_artifacts=(artifact.path,),
                evidence=(
                    ReportEvidence(
                        artifact=artifact.path,
                        description=artifact.evidence,
                        evidence_type=evidence_type,
                        confidence=artifact.confidence,
                    ),
                ),
                evidence_strength=artifact.confidence,
                is_inference=evidence_type == EvidenceType.INFERENCE.value,
                graph_node_id=graph_id,
            )
        )
    return findings


def _impact_findings(
    impact: ImpactAnalysis,
    impact_artifacts: set[str],
) -> list[ReportFinding]:
    findings: list[ReportFinding] = []
    for finding in impact.findings:
        graph_id = (
            artifact_node_id(finding.affected_artifact)
            if finding.affected_artifact in impact_artifacts
            else None
        )
        evidence = _impact_evidence_items(finding)
        primary_type = finding.primary_evidence_type().value
        findings.append(
            ReportFinding(
                id=f"impact:{finding.affected_artifact}:{finding.relationship.value}",
                category="impact",
                title=finding.affected_artifact,
                description=finding.potential_impact,
                affected_artifacts=(finding.affected_artifact,),
                relationship=finding.relationship.value,
                potential_impact=finding.potential_impact,
                evidence=evidence,
                evidence_strength=finding.evidence_strength.value,
                is_inference=primary_type == EvidenceType.INFERENCE.value,
                graph_node_id=graph_id,
            )
        )
    return findings


def _historical_findings(
    history: Optional[RepositoryHistory],
    impact_artifacts: set[str],
) -> list[ReportFinding]:
    if history is None:
        return []

    findings: list[ReportFinding] = []
    for artifact_path in sorted(history.artifact_histories):
        artifact_history = history.artifact_histories[artifact_path]
        if not artifact_history.commits and not artifact_history.note:
            continue

        description = _history_description(artifact_history)
        evidence = _historical_evidence_items(artifact_history)
        graph_id = history_node_id(artifact_path) if artifact_path in impact_artifacts else None
        findings.append(
            ReportFinding(
                id=f"history:{artifact_path}",
                category="historical",
                title=f"History: {artifact_path}",
                description=description,
                affected_artifacts=(artifact_path,),
                evidence=evidence,
                evidence_strength="confirmed" if artifact_history.commits else "possible",
                is_inference=not bool(artifact_history.commits),
                graph_node_id=graph_id,
            )
        )
    return findings


def _risk_findings(risk: RiskAnalysis) -> list[ReportFinding]:
    findings: list[ReportFinding] = []
    for index, risk_item in enumerate(risk.risks):
        evidence = _impact_evidence_items_from_risk(risk_item)
        findings.append(
            ReportFinding(
                id=f"risk:{index}:{risk_item.category.value}",
                category="risk",
                title=f"{risk_item.severity.value.upper()} {risk_item.category.value} risk",
                description=risk_item.explanation,
                affected_artifacts=risk_item.affected_artifacts,
                severity=risk_item.severity.value,
                evidence=evidence,
                evidence_strength=risk_item.evidence_strength.value,
                is_inference=risk_item.is_inference,
                recommendation=risk_item.recommended_action,
                graph_node_id=risk_node_id(index, risk_item.category.value),
            )
        )
    return findings


def _next_actions(findings: list[ReportFinding]) -> list[ReportAction]:
    risk_findings = [finding for finding in findings if finding.category == "risk" and finding.recommendation]
    risk_findings.sort(
        key=lambda finding: (
            _SEVERITY_ORDER.get(
                RiskSeverity((finding.severity or "low").lower()),
                99,
            ),
            finding.id,
        )
    )

    actions: list[ReportAction] = []
    for priority, finding in enumerate(risk_findings, start=1):
        actions.append(
            ReportAction(
                priority=priority,
                action=finding.recommendation or "",
                source_finding_id=finding.id,
                severity=finding.severity or "low",
                graph_node_id=finding.graph_node_id,
            )
        )
    return actions


def _evidence_gaps(
    context: RepositoryContext,
    impact: ImpactAnalysis,
    risk: RiskAnalysis,
    history: Optional[RepositoryHistory],
    impact_artifacts: set[str],
) -> list[ReportEvidenceGap]:
    gaps: list[ReportEvidenceGap] = []

    context_only = {
        artifact.path
        for artifact in context.artifacts
        if artifact.path not in impact_artifacts
    }
    for path in sorted(context_only):
        gaps.append(
            ReportEvidenceGap(
                description=(
                    "Artifact is relevant repository context but was not connected "
                    "to this change by impact analysis; it does not appear on the Change Impact Map."
                ),
                affected_artifact=path,
            )
        )

    if history:
        for artifact_path, artifact_history in sorted(history.artifact_histories.items()):
            if artifact_history.note:
                gaps.append(
                    ReportEvidenceGap(
                        description=artifact_history.note,
                        affected_artifact=artifact_path,
                    )
                )
            elif not artifact_history.commits:
                gaps.append(
                    ReportEvidenceGap(
                        description="No Git history was found for this artifact.",
                        affected_artifact=artifact_path,
                    )
                )

    for finding in impact.findings:
        if not finding.evidence:
            gaps.append(
                ReportEvidenceGap(
                    description="Impact finding has no supporting evidence recorded.",
                    affected_artifact=finding.affected_artifact,
                )
            )

    for risk_item in risk.risks:
        if not risk_item.evidence:
            gaps.append(
                ReportEvidenceGap(
                    description="Risk finding has no supporting evidence recorded.",
                    affected_artifact=risk_item.affected_artifacts[0] if risk_item.affected_artifacts else None,
                )
            )

    if not context.artifacts and not context.error:
        gaps.append(ReportEvidenceGap(description="No relevant repository context artifacts were identified."))

    if not impact.findings and not impact.error:
        gaps.append(ReportEvidenceGap(description="Impact analysis produced no findings for this change."))

    if not risk.risks and not risk.error and impact.findings:
        gaps.append(ReportEvidenceGap(description="Risk analysis produced no risk findings for this change."))

    return gaps


def _history_description(artifact_history: ArtifactHistory) -> str:
    if not artifact_history.commits:
        return artifact_history.note or "No historical commits were found for this artifact."

    commit_lines = []
    for commit in artifact_history.commits:
        parts = [commit.short_hash, commit.message]
        if commit.date_iso:
            parts.append(commit.date_iso)
        commit_lines.append(" — ".join(part for part in parts if part))
    return f"{len(artifact_history.commits)} relevant commit(s): " + "; ".join(commit_lines)


def _impact_evidence_items(finding: ImpactFinding) -> tuple[ReportEvidence, ...]:
    return tuple(_to_report_evidence(item, finding.evidence_strength.value) for item in finding.evidence)


def _impact_evidence_items_from_risk(risk_item: RiskFinding) -> tuple[ReportEvidence, ...]:
    return tuple(_to_report_evidence(item, risk_item.evidence_strength.value) for item in risk_item.evidence)


def _historical_evidence_items(artifact_history: ArtifactHistory) -> tuple[ReportEvidence, ...]:
    items: list[ReportEvidence] = []
    for evidence in artifact_history.evidence:
        items.append(_to_report_evidence(evidence, "confirmed"))
    for commit in artifact_history.commits:
        items.append(
            ReportEvidence(
                artifact=artifact_history.artifact_path,
                description=f"{commit.short_hash}: {commit.message}",
                evidence_type=EvidenceType.DIRECT_EVIDENCE.value,
                confidence="confirmed",
            )
        )
    return tuple(items)


def _to_report_evidence(evidence: Any, confidence: str) -> ReportEvidence:
    if isinstance(evidence, ImpactEvidence):
        return ReportEvidence(
            artifact=evidence.artifact,
            description=evidence.description,
            evidence_type=evidence.evidence_type.value,
            confidence=confidence,
        )

    artifact = str(getattr(evidence, "artifact_path", getattr(evidence, "artifact", "unknown")))
    description = str(getattr(evidence, "description", str(evidence)))
    evidence_type = getattr(evidence, "evidence_type", EvidenceType.DIRECT_EVIDENCE)
    if hasattr(evidence_type, "value"):
        evidence_type = evidence_type.value
    return ReportEvidence(
        artifact=artifact,
        description=description,
        evidence_type=str(evidence_type),
        confidence=confidence,
    )


def _confidence_to_evidence_type(confidence: str) -> str:
    normalized = (confidence or "possible").lower()
    if normalized == "confirmed":
        return EvidenceType.DIRECT_EVIDENCE.value
    if normalized == "likely":
        return EvidenceType.DERIVED_RELATIONSHIP.value
    return EvidenceType.INFERENCE.value
