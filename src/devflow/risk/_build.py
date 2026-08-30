"""Deterministic Phase 5 risk analysis built only from earlier-phase evidence."""

from __future__ import annotations

from typing import Optional

from devflow.graph_index import build_graph_index
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
    index = build_graph_index(context.repository_graph)
    subjects = _subject_sources(impact, artifacts, index)
    # Downstream helpers only test membership, so they keep taking a mapping
    # of path -> the impact finding that put the path under review.
    changed_sources = {path: finding for path, (finding, _origin) in subjects.items()}

    risks: list[RiskFinding] = []
    for path, (finding, origin) in subjects.items():
        dependents = index.transitive_dependents(path) if index.available else ()
        risks.append(_code_risk(path, finding, origin, dependents))
        related_tests = _tests_for_source(path, impact.findings)
        if related_tests:
            risks.append(_regression_risk(path, finding, related_tests))
        else:
            risks.append(_test_gap_risk(path, finding, dependents))

    risks.extend(_changed_dependency_risks(impact.findings, artifacts))
    risks.extend(_historical_risks(changed_sources, impact.findings, history))
    risks.extend(_security_risks(changed_sources, impact.findings))
    analysis.risks = _deduplicate_and_sort(risks)
    return analysis


# A source file under review because the developer named it, versus one the
# repository's own import graph connected to the change.  Both are legitimate
# risk subjects; they carry different evidence strength.
_ORIGIN_DECLARED = "declared"
_ORIGIN_STRUCTURAL = "structural"

# Dependent counts at which exposure stops being a footnote.  Derived from
# real import edges, so these are counts of facts, not scores.
_ELEVATED_DEPENDENTS = 3
_HIGH_DEPENDENTS = 10


def _subject_sources(
    impact: ImpactAnalysis,
    artifacts: dict[str, object],
    index,
) -> dict[str, tuple[ImpactFinding, str]]:
    """Select the source files whose change exposure should be assessed.

    Historically this required a MODIFIES relationship, which only exists for
    files the developer explicitly listed.  A description-only run therefore
    produced no subjects and no risks at all -- the common case for a developer
    exploring an unfamiliar repository.

    Sources are now admitted on either basis:

      * declared   -- a MODIFIES finding (the developer named the file)
      * structural -- the file is a relevant source that the Repository
                      Knowledge Graph actually contains, so its import
                      relationships are real repository evidence

    Structural subjects require the graph.  Without it the behavior is
    unchanged, so no risk is ever invented from a filename alone.
    """
    subjects: dict[str, tuple[ImpactFinding, str]] = {}

    for finding in impact.findings:
        path = finding.affected_artifact
        artifact = artifacts.get(path)
        if finding.relationship != RelationshipType.MODIFIES:
            continue
        if artifact is None or artifact.kind != ArtifactKind.SOURCE:
            continue
        subjects[path] = (finding, _ORIGIN_DECLARED)

    if not index.available:
        return subjects

    for finding in impact.findings:
        path = finding.affected_artifact
        if path in subjects:
            continue
        artifact = artifacts.get(path)
        if artifact is None or artifact.kind != ArtifactKind.SOURCE:
            continue
        if not index.has_file(path):
            continue
        if finding.relationship not in (
            RelationshipType.IMPACTS,
            RelationshipType.IMPORTS,
        ):
            continue
        subjects[path] = (finding, _ORIGIN_STRUCTURAL)

    return subjects


def _dependent_evidence(path: str, dependents: tuple[str, ...]) -> tuple[ImpactEvidence, ...]:
    if not dependents:
        return ()
    shown = ", ".join(dependents[:5])
    suffix = "" if len(dependents) <= 5 else f", and {len(dependents) - 5} more"
    return (
        ImpactEvidence(
            artifact=path,
            description=(
                f"{len(dependents)} file(s) reach '{path}' through static import "
                f"edges parsed from repository source: {shown}{suffix} "
                "(DIRECT_EVIDENCE: repository import graph)."
            ),
            evidence_type=EvidenceType.DIRECT_EVIDENCE,
        ),
    )


def _code_risk(
    path: str,
    finding: ImpactFinding,
    origin: str,
    dependents: tuple[str, ...],
) -> RiskFinding:
    """Exposure of a source file under review, scaled by its real blast radius."""
    count = len(dependents)
    if count >= _HIGH_DEPENDENTS:
        severity = RiskSeverity.HIGH
    elif count >= _ELEVATED_DEPENDENTS:
        severity = RiskSeverity.MEDIUM
    else:
        severity = RiskSeverity.LOW

    if origin == _ORIGIN_DECLARED:
        basis = "is explicitly included in the requested source-code change"
        strength = EvidenceStrength.CONFIRMED
    else:
        basis = (
            "was identified as relevant to the requested change and is present "
            "in the repository's import graph"
        )
        strength = EvidenceStrength.LIKELY

    if count:
        exposure = (
            f" {count} file(s) depend on it through real import edges, so a "
            "behavioral change here is not locally contained."
        )
    else:
        exposure = (
            " No other file imports it in the analyzed import graph, so its "
            "exposure appears locally contained."
        )

    return RiskFinding(
        severity=severity,
        category=RiskCategory.CODE,
        explanation=(
            f"'{path}' {basis}.{exposure} "
            "Any behavioral consequence requires review; no defect is established."
        ),
        affected_artifacts=(path,),
        evidence=finding.evidence + _dependent_evidence(path, dependents),
        recommended_action=(
            "Review the changed code path and its importing callers before merging."
        ),
        evidence_strength=strength,
        assessment_type=EvidenceType.INFERENCE,
    )


def _tests_for_source(path: str, findings: list[ImpactFinding]) -> list[ImpactFinding]:
    """Find TESTED_BY findings covering ``path``.

    Two evidence routes qualify, and both must be recognized or a source with
    real graph-derived test coverage would be reported as a test gap:

      * name-stem association (DERIVED_RELATIONSHIP, Phase 4 rule 3)
      * repository graph test association (DIRECT_EVIDENCE, Phase 4 rule 8)
    """
    stem_marker = f"source file '{path}'"
    matches: list[ImpactFinding] = []
    for finding in findings:
        if finding.relationship != RelationshipType.TESTED_BY:
            continue
        evidence_type = finding.primary_evidence_type()
        if evidence_type == EvidenceType.DERIVED_RELATIONSHIP and any(
            stem_marker in evidence.description for evidence in finding.evidence
        ):
            matches.append(finding)
        elif evidence_type == EvidenceType.DIRECT_EVIDENCE and any(
            _mentions_graph_test_association(evidence.description, path)
            for evidence in finding.evidence
        ):
            matches.append(finding)
    return matches


def _mentions_graph_test_association(description: str, path: str) -> bool:
    """Whether a graph TESTED_BY evidence description names ``path`` as the source."""
    normalized = " ".join(description.split())
    return f"'{path}' is tested by" in normalized


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


def _test_gap_risk(
    path: str,
    changed: ImpactFinding,
    dependents: tuple[str, ...] = (),
) -> RiskFinding:
    """An uncovered source file, escalated by how many files depend on it.

    An untested file that nothing imports is a local gap.  An untested file
    with a wide, import-proven dependent set is the highest-value finding
    DevFlow can surface deterministically.
    """
    gap_evidence = ImpactEvidence(
        artifact=path,
        description=(
            f"No Phase 4 TESTED_BY finding was available for source '{path}', "
            "by either name-stem association or repository graph test "
            "association. This is a scoped evidence gap, not proof that the "
            "repository has no tests."
        ),
        evidence_type=EvidenceType.DERIVED_RELATIONSHIP,
    )
    count = len(dependents)
    if count >= _HIGH_DEPENDENTS:
        severity = RiskSeverity.HIGH
    elif count >= _ELEVATED_DEPENDENTS:
        severity = RiskSeverity.MEDIUM
    else:
        severity = RiskSeverity.LOW if count == 0 else RiskSeverity.MEDIUM

    exposure = (
        f" {count} file(s) depend on it through real import edges, so an "
        "untested regression here would not stay local."
        if count
        else ""
    )
    return RiskFinding(
        severity=severity,
        category=RiskCategory.TEST_GAP,
        explanation=(
            f"No structurally associated test was found in the available impact "
            f"analysis for '{path}'.{exposure} Test coverage may need manual "
            "confirmation."
        ),
        affected_artifacts=(path,),
        evidence=changed.evidence + (gap_evidence,) + _dependent_evidence(path, dependents),
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
