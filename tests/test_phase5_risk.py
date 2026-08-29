"""Deterministic Phase 5 tests using only structured earlier-phase outputs."""

from devflow.models.context import ArtifactKind, ContextArtifact, RelevanceReason, RepositoryContext
from devflow.models.history import ArtifactHistory, HistoricalCommit, RepositoryHistory
from devflow.models.impact import (
    EvidenceStrength, EvidenceType, ImpactAnalysis, ImpactEvidence, ImpactFinding, RelationshipType,
)
from devflow.models.risk import RiskAnalysis, RiskCategory, RiskSeverity
from devflow.risk import build_risk_analysis


def _context(*artifacts: ContextArtifact) -> RepositoryContext:
    return RepositoryContext("https://github.com/example/repo", "example", "repo", "Change behavior.", list(artifacts), [a.path for a in artifacts])


def _artifact(path: str, kind: ArtifactKind) -> ContextArtifact:
    return ContextArtifact(path, kind, RelevanceReason.CHANGED_FILE, "path appears in changed_files")


def _evidence(path: str, description: str = "changed_files input") -> ImpactEvidence:
    return ImpactEvidence(path, description, EvidenceType.DIRECT_EVIDENCE)


def _impact(*findings: ImpactFinding) -> ImpactAnalysis:
    return ImpactAnalysis("https://github.com/example/repo", "example", "repo", "Change behavior.", list(findings))


def _changed(path: str) -> ImpactFinding:
    return ImpactFinding(path, RelationshipType.MODIFIES, "directly modified", (_evidence(path),), EvidenceStrength.CONFIRMED, "source")


def _test_for(source: str, test: str) -> ImpactFinding:
    evidence = ImpactEvidence(test, f"Test file '{test}' name-stem matches source file '{source}'", EvidenceType.DERIVED_RELATIONSHIP)
    return ImpactFinding(test, RelationshipType.TESTED_BY, "test association", (evidence,), EvidenceStrength.LIKELY, "test")


def _history(path: str, count: int) -> RepositoryHistory:
    commits = tuple(HistoricalCommit(chr(97 + i) * 40, chr(97 + i) * 7, "maintenance", "Dev", None, ()) for i in range(count))
    artifact_history = ArtifactHistory(path, commits, ())
    return RepositoryHistory("https://github.com/example/repo", "example", "repo", "Change behavior.", {path: artifact_history}, count)


def test_risk_model_creation_and_metadata_preservation():
    ctx = _context(_artifact("lib/engine.rs", ArtifactKind.SOURCE))
    result = build_risk_analysis(_impact(_changed("lib/engine.rs")), ctx)
    assert isinstance(result, RiskAnalysis)
    assert result.repository_url == ctx.repository_url
    assert result.risks[0].affected_artifacts


def test_severity_is_explainable_from_rule_evidence():
    ctx = _context(_artifact("deps.lock", ArtifactKind.DEPENDENCY))
    dep = ImpactFinding("deps.lock", RelationshipType.DEPENDS_ON, "manifest", (_evidence("deps.lock"),), EvidenceStrength.CONFIRMED, "dependency")
    risk = build_risk_analysis(_impact(dep), ctx).risks[0]
    assert risk.category == RiskCategory.DEPENDENCY
    assert risk.severity == RiskSeverity.HIGH


def test_test_gap_when_changed_source_has_no_structural_test_relationship():
    ctx = _context(_artifact("core/worker.go", ArtifactKind.SOURCE))
    risks = build_risk_analysis(_impact(_changed("core/worker.go")), ctx).risks
    gap = next(risk for risk in risks if risk.category == RiskCategory.TEST_GAP)
    assert gap.assessment_type == EvidenceType.DERIVED_RELATIONSHIP
    assert "not proof" in gap.evidence[-1].description


def test_regression_risk_uses_derived_test_relationship():
    ctx = _context(_artifact("lib/parser.ts", ArtifactKind.SOURCE))
    risks = build_risk_analysis(_impact(_changed("lib/parser.ts"), _test_for("lib/parser.ts", "spec/parser.spec.ts")), ctx).risks
    regression = next(risk for risk in risks if risk.category == RiskCategory.REGRESSION)
    assert regression.severity == RiskSeverity.MEDIUM
    assert "spec/parser.spec.ts" in regression.affected_artifacts


def test_dependency_risk_requires_changed_manifest_not_manifest_existence():
    ctx = _context(ContextArtifact("package.json", ArtifactKind.DEPENDENCY, RelevanceReason.DEPENDENCY_MANIFEST, "present"))
    possible = ImpactFinding("package.json", RelationshipType.DEPENDS_ON, "manifest", (_evidence("package.json"),), EvidenceStrength.POSSIBLE, "dependency")
    assert not build_risk_analysis(_impact(possible), ctx).risks


def test_historical_risk_requires_repeated_real_history():
    ctx = _context(_artifact("src/cache.py", ArtifactKind.SOURCE))
    historical = ImpactFinding("src/cache.py", RelationshipType.HISTORICALLY_CHANGED_WITH, "history", (_evidence("src/cache.py", "Git commit abc modified src/cache.py"),), EvidenceStrength.CONFIRMED, "historical")
    risks = build_risk_analysis(_impact(_changed("src/cache.py"), historical), ctx, _history("src/cache.py", 2)).risks
    assert any(risk.category == RiskCategory.HISTORICAL for risk in risks)


def test_single_historical_commit_does_not_create_historical_risk():
    ctx = _context(_artifact("src/cache.py", ArtifactKind.SOURCE))
    historical = ImpactFinding("src/cache.py", RelationshipType.HISTORICALLY_CHANGED_WITH, "history", (_evidence("src/cache.py"),), EvidenceStrength.CONFIRMED, "historical")
    risks = build_risk_analysis(_impact(_changed("src/cache.py"), historical), ctx, _history("src/cache.py", 1)).risks
    assert not any(risk.category == RiskCategory.HISTORICAL for risk in risks)


def test_security_risk_requires_direct_control_evidence_not_path_name():
    ctx = _context(_artifact("auth/password.py", ArtifactKind.SOURCE))
    assert not any(r.category == RiskCategory.SECURITY for r in build_risk_analysis(_impact(_changed("auth/password.py")), ctx).risks)
    control = ImpactFinding("auth/password.py", RelationshipType.IMPACTS, "control", (_evidence("auth/password.py", "authorization check enforces an administrator policy"),), EvidenceStrength.CONFIRMED, "source")
    risks = build_risk_analysis(_impact(_changed("auth/password.py"), control), ctx).risks
    assert next(r for r in risks if r.category == RiskCategory.SECURITY).is_inference


def test_evidence_is_preserved_and_inference_is_explicit():
    ctx = _context(_artifact("module/file.py", ArtifactKind.SOURCE))
    source_evidence = _evidence("module/file.py", "developer listed the file")
    result = build_risk_analysis(_impact(ImpactFinding("module/file.py", RelationshipType.MODIFIES, "changed", (source_evidence,), EvidenceStrength.CONFIRMED, "source")), ctx)
    code = next(r for r in result.risks if r.category == RiskCategory.CODE)
    assert source_evidence in code.evidence and code.is_inference


def test_no_speculative_risks_for_docs_configs_or_unrelated_source_findings():
    ctx = _context(
        ContextArtifact("README.md", ArtifactKind.DOCUMENTATION, RelevanceReason.DOCUMENTATION, "present"),
        ContextArtifact("settings.yml", ArtifactKind.CONFIGURATION, RelevanceReason.CONFIGURATION, "present"),
    )
    findings = _impact(
        ImpactFinding("README.md", RelationshipType.DOCUMENTED_BY, "doc", (_evidence("README.md"),), EvidenceStrength.POSSIBLE, "documentation"),
        ImpactFinding("settings.yml", RelationshipType.CONFIGURED_BY, "config", (_evidence("settings.yml"),), EvidenceStrength.POSSIBLE, "configuration"),
    )
    assert build_risk_analysis(findings, ctx).risks == []


def test_empty_or_failed_impact_is_reported_without_risks():
    ctx = _context(_artifact("src/a.py", ArtifactKind.SOURCE))
    result = build_risk_analysis(_impact(), ctx)
    assert result.error and not result.risks


def test_repository_agnostic_and_duplicate_risks_prevented():
    for path in ("app/main.java", "pkg/run.go", "lib/value.rb"):
        ctx = _context(_artifact(path, ArtifactKind.SOURCE))
        result = build_risk_analysis(_impact(_changed(path), _changed(path)), ctx)
        keys = [(risk.category, risk.affected_artifacts) for risk in result.risks]
        assert len(keys) == len(set(keys))


def test_every_risk_has_a_recommendation():
    ctx = _context(_artifact("src/a.py", ArtifactKind.SOURCE))
    assert all(risk.recommended_action for risk in build_risk_analysis(_impact(_changed("src/a.py")), ctx).risks)
