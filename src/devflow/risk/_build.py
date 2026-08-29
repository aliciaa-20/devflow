"""Deterministic Phase 5 risk analysis built only from earlier-phase evidence."""

from __future__ import annotations

from typing import Optional

from devflow.models.context import ArtifactKind, RepositoryContext
from devflow.models.history import RepositoryHistory
from devflow.models.impact import (
    EvidenceStrength,
    EvidenceType,
    ImpactAnalysis,
    ImpactEvidence,
    ImpactFinding,
    RelationshipType,
)
from devflow.models.risk import RiskAnalysis, RiskCategory, RiskFinding, RiskSeverity


def build_risk_analysis(
    impact: ImpactAnalysis,
    context: RepositoryContext,
    history: Optional[RepositoryHistory] = None,
) -> RiskAnalysis:
    """Produce only risks whose prerequisites are explicit structured evidence.

    ``history`` is accepted to preserve the Phase 3 input boundary; historical
    risks require its real per-artifact commit records as well as Phase 4's
    historical finding.  Risk conclusions describe potential exposure and are
    therefore marked as derived or inference even when their evidence is direct.
    """
    analysis = RiskAnalysis(
        repository_url=impact.repository_url,
        owner=impact.owner,
        name=impact.name,
        change_summary=impact.change_summary,
    )
    if context.error:
        analysis.error = f"Skipped: Phase 2 context had an error: {context.error}"
        return analysis
    if impact.error:
        analysis.error = f"Skipped: Phase 4 impact analysis had an error: {impact.error}"
        return analysis
    if not impact.findings:
        analysis.error = "No impact findings available; risk analysis cannot proceed."
        return analysis

    artifacts = {artifact.path: artifact for artifact in context.artifacts}
    changed_sources = {
        finding.affected_artifact: finding
        for finding in impact.findings
        if finding.relationship == RelationshipType.MODIFIES
        and artifacts.get(finding.affected_artifact, None)
        and artifacts[finding.affected_artifact].kind == ArtifactKind.SOURCE
    }
    risks: list[RiskFinding] = []
    for path, finding in changed_sources.items():
        risks.append(_code_risk(path, finding))
        related_tests = _tests_for_source(path, impact.findings)
        if related_tests:
            risks.append(_regression_risk(path, finding, related_tests))
        else:
            risks.append(_test_gap_risk(path, finding))

    risks.extend(_changed_dependency_risks(impact.findings, artifacts))
    risks.extend(_historical_risks(changed_sources, impact.findings, history))
    risks.extend(_security_risks(changed_sources, impact.findings))
    analysis.risks = _deduplicate_and_sort(risks)
    return analysis


def _code_risk(path: str, finding: ImpactFinding) -> RiskFinding:
    return RiskFinding(
        severity=RiskSeverity.LOW,
        category=RiskCategory.CODE,
        explanation=(
            f"'{path}' is explicitly included in the requested source-code change. "
            "Any behavioral consequence requires review; no defect is established."
        ),
        affected_artifacts=(path,),
        evidence=finding.evidence,
        recommended_action="Review the changed code path and its direct callers before merging.",
        evidence_strength=EvidenceStrength.CONFIRMED,
        assessment_type=EvidenceType.INFERENCE,
    )


def _tests_for_source(path: str, findings: list[ImpactFinding]) -> list[ImpactFinding]:
    marker = f"source file '{path}'"
    return [
        finding for finding in findings
        if finding.relationship == RelationshipType.TESTED_BY
        and finding.primary_evidence_type() == EvidenceType.DERIVED_RELATIONSHIP
        and any(marker in evidence.description for evidence in finding.evidence)
    ]


def _regression_risk(path: str, changed: ImpactFinding, tests: list[ImpactFinding]) -> RiskFinding:
    evidence = changed.evidence + tuple(ev for test in tests for ev in test.evidence)
    test_paths = tuple(test.affected_artifact for test in tests)
    return RiskFinding(
        severity=RiskSeverity.MEDIUM,
        category=RiskCategory.REGRESSION,
        explanation=(
            f"'{path}' is changing and {', '.join(test_paths)} is structurally associated "
            "with it. The association is derived from filenames, so regression exposure is inferred."
        ),
        affected_artifacts=(path, *test_paths),
        evidence=evidence,
        recommended_action="Run the associated tests and add coverage for changed behavior if needed.",
        evidence_strength=EvidenceStrength.LIKELY,
        assessment_type=EvidenceType.DERIVED_RELATIONSHIP,
    )


def _test_gap_risk(path: str, changed: ImpactFinding) -> RiskFinding:
    gap_evidence = ImpactEvidence(
        artifact=path,
        description=(
            f"No Phase 4 TESTED_BY finding with a derived structural relationship "
            f"was available for changed source '{path}'. This is a scoped evidence gap, "
            "not proof that the repository has no tests."
        ),
        evidence_type=EvidenceType.DERIVED_RELATIONSHIP,
    )
    return RiskFinding(
        severity=RiskSeverity.MEDIUM,
        category=RiskCategory.TEST_GAP,
        explanation=(
            f"No structurally associated test was found in the available impact analysis for '{path}'. "
            "Test coverage may need manual confirmation."
        ),
        affected_artifacts=(path,),
        evidence=changed.evidence + (gap_evidence,),
        recommended_action="Identify and run relevant tests; add a focused test if changed behavior lacks coverage.",
        evidence_strength=EvidenceStrength.LIKELY,
        assessment_type=EvidenceType.DERIVED_RELATIONSHIP,
    )


def _changed_dependency_risks(
    findings: list[ImpactFinding], artifacts: dict[str, object]
) -> list[RiskFinding]:
    risks = []
    for finding in findings:
        artifact = artifacts.get(finding.affected_artifact)
        if (
            finding.relationship == RelationshipType.DEPENDS_ON
            and finding.evidence_strength == EvidenceStrength.CONFIRMED
            and artifact is not None
            and getattr(artifact, "kind") == ArtifactKind.DEPENDENCY
        ):
            risks.append(RiskFinding(
                severity=RiskSeverity.HIGH,
                category=RiskCategory.DEPENDENCY,
                explanation=(
                    f"Dependency manifest '{finding.affected_artifact}' is explicitly included in the change. "
                    "Its dependency resolution effect must be reviewed; no vulnerable package is claimed."
                ),
                affected_artifacts=(finding.affected_artifact,),
                evidence=finding.evidence,
                recommended_action="Review the dependency diff, lockfile changes, and compatibility of affected consumers.",
                evidence_strength=EvidenceStrength.CONFIRMED,
                assessment_type=EvidenceType.INFERENCE,
            ))
    return risks


def _historical_risks(
    changed_sources: dict[str, ImpactFinding], findings: list[ImpactFinding], history: Optional[RepositoryHistory]
) -> list[RiskFinding]:
    if history is None or history.error:
        return []
    risks = []
    for finding in findings:
        if finding.relationship != RelationshipType.HISTORICALLY_CHANGED_WITH:
            continue
        path = finding.affected_artifact
        artifact_history = history.artifact_histories.get(path)
        if path not in changed_sources or artifact_history is None or len(artifact_history.commits) < 2:
            continue
        risks.append(RiskFinding(
            severity=RiskSeverity.MEDIUM,
            category=RiskCategory.HISTORICAL,
            explanation=(
                f"'{path}' has {len(artifact_history.commits)} recorded commits and is explicitly changing. "
                "Repeated historical modification can indicate an area worth closer review; it does not establish a past defect."
            ),
            affected_artifacts=(path,),
            evidence=finding.evidence,
            recommended_action="Review the cited commits for constraints and re-run behavior affected by the change.",
            evidence_strength=EvidenceStrength.CONFIRMED,
            assessment_type=EvidenceType.DERIVED_RELATIONSHIP,
        ))
    return risks


_SECURITY_CONTROL_TERMS = (
    "security control", "authorization check", "authentication check",
    "permission check", "access control", "credential validation",
)


def _security_risks(changed_sources: dict[str, ImpactFinding], findings: list[ImpactFinding]) -> list[RiskFinding]:
    """Require direct evidence describing a control; paths/names alone never qualify."""
    risks = []
    for finding in findings:
        path = finding.affected_artifact
        if path not in changed_sources:
            continue
        evidence = tuple(
            item for item in finding.evidence
            if item.evidence_type == EvidenceType.DIRECT_EVIDENCE
            and any(term in item.description.lower() for term in _SECURITY_CONTROL_TERMS)
        )
        if evidence:
            risks.append(RiskFinding(
                severity=RiskSeverity.HIGH,
                category=RiskCategory.SECURITY,
                explanation=(
                    f"Direct repository evidence identifies a security control in changed artifact '{path}'. "
                    "The risk is the inferred possibility of weakening that control, not a claimed vulnerability."
                ),
                affected_artifacts=(path,),
                evidence=evidence,
                recommended_action="Review the control's intended policy and add or run tests for allowed and denied cases.",
                evidence_strength=EvidenceStrength.CONFIRMED,
                assessment_type=EvidenceType.INFERENCE,
            ))
    return risks


def _deduplicate_and_sort(risks: list[RiskFinding]) -> list[RiskFinding]:
    severity_order = {RiskSeverity.CRITICAL: 0, RiskSeverity.HIGH: 1, RiskSeverity.MEDIUM: 2, RiskSeverity.LOW: 3}
    unique: dict[tuple[RiskCategory, tuple[str, ...]], RiskFinding] = {}
    for risk in risks:
        unique.setdefault((risk.category, risk.affected_artifacts), risk)
    return sorted(unique.values(), key=lambda risk: (severity_order[risk.severity], risk.category.value, risk.affected_artifacts))
