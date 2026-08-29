"""Deterministic tests for DevFlow Phase 7: Developer Report."""

from __future__ import annotations

import json
from unittest.mock import patch

from devflow.__main__ import _analyze_repository
from devflow.map import build_change_impact_map
from devflow.models.context import ArtifactKind, ContextArtifact, RelevanceReason, RepositoryContext
from devflow.models.history import ArtifactHistory, HistoricalCommit, RepositoryHistory
from devflow.models.impact import (
    EvidenceStrength,
    EvidenceType,
    ImpactAnalysis,
    ImpactEvidence,
    ImpactFinding,
    RelationshipType,
)
from devflow.models.report import DeveloperReport
from devflow.models.risk import RiskAnalysis, RiskCategory, RiskFinding, RiskSeverity
from devflow.report import build_developer_report, serialize_developer_report, write_frontend_report_payload


def _context() -> RepositoryContext:
    artifacts = [
        ContextArtifact(
            "src/auth/session.py",
            ArtifactKind.SOURCE,
            RelevanceReason.CHANGED_FILE,
            "path appears in changed_files",
            "confirmed",
        ),
        ContextArtifact(
            "tests/test_session.py",
            ArtifactKind.TEST,
            RelevanceReason.TEST_FOR_CHANGED,
            "test name overlaps changed source",
            "likely",
        ),
        ContextArtifact(
            "README.md",
            ArtifactKind.DOCUMENTATION,
            RelevanceReason.DOCUMENTATION,
            "doc reference matches change topic",
            "possible",
        ),
    ]
    return RepositoryContext(
        repository_url="https://github.com/example/repo",
        owner="example",
        name="repo",
        change_summary="Refactor authentication session handling.",
        artifacts=artifacts,
        all_files=[a.path for a in artifacts],
        entry_points=[],
    )


def _impact() -> ImpactAnalysis:
    findings = [
        ImpactFinding(
            affected_artifact="src/auth/session.py",
            relationship=RelationshipType.MODIFIES,
            potential_impact="This file directly handles auth session behavior.",
            evidence=(
                ImpactEvidence(
                    artifact="src/auth/session.py",
                    description="path appears in changed_files",
                    evidence_type=EvidenceType.DIRECT_EVIDENCE,
                ),
            ),
            evidence_strength=EvidenceStrength.CONFIRMED,
            finding_type="source",
        ),
        ImpactFinding(
            affected_artifact="tests/test_session.py",
            relationship=RelationshipType.TESTED_BY,
            potential_impact="This test is structurally associated with the source change.",
            evidence=(
                ImpactEvidence(
                    artifact="tests/test_session.py",
                    description="test path overlaps source name stem",
                    evidence_type=EvidenceType.DERIVED_RELATIONSHIP,
                ),
            ),
            evidence_strength=EvidenceStrength.LIKELY,
            finding_type="test",
        ),
    ]
    return ImpactAnalysis(
        repository_url="https://github.com/example/repo",
        owner="example",
        name="repo",
        change_summary="Refactor authentication session handling.",
        findings=findings,
    )


def _risk() -> RiskAnalysis:
    return RiskAnalysis(
        repository_url="https://github.com/example/repo",
        owner="example",
        name="repo",
        change_summary="Refactor authentication session handling.",
        risks=[
            RiskFinding(
                severity=RiskSeverity.HIGH,
                category=RiskCategory.SECURITY,
                explanation="Changed auth session code may affect authorization checks.",
                affected_artifacts=("src/auth/session.py",),
                evidence=(
                    ImpactEvidence(
                        artifact="src/auth/session.py",
                        description="authorization check enforces the session policy",
                        evidence_type=EvidenceType.DIRECT_EVIDENCE,
                    ),
                ),
                recommended_action="Review the auth policy and add attack-path tests.",
                evidence_strength=EvidenceStrength.CONFIRMED,
                assessment_type=EvidenceType.INFERENCE,
            ),
            RiskFinding(
                severity=RiskSeverity.LOW,
                category=RiskCategory.CODE,
                explanation="Source file is part of the requested change.",
                affected_artifacts=("src/auth/session.py",),
                evidence=(
                    ImpactEvidence(
                        artifact="src/auth/session.py",
                        description="path appears in changed_files",
                        evidence_type=EvidenceType.DIRECT_EVIDENCE,
                    ),
                ),
                recommended_action="Review the behavioral impact of the change.",
                evidence_strength=EvidenceStrength.CONFIRMED,
                assessment_type=EvidenceType.DERIVED_RELATIONSHIP,
            ),
        ],
    )


def _history() -> RepositoryHistory:
    commit = HistoricalCommit(
        hash="a" * 40,
        short_hash="a" * 7,
        message="Refactor session handling",
        author="Dev",
        date_iso="2024-01-01 00:00:00 +0000",
        refs=(),
    )
    return RepositoryHistory(
        repository_url="https://github.com/example/repo",
        owner="example",
        name="repo",
        change_summary="Refactor authentication session handling.",
        artifact_histories={
            "src/auth/session.py": ArtifactHistory(
                artifact_path="src/auth/session.py",
                commits=(commit,),
                evidence=(),
            )
        },
        total_commits_found=1,
    )


def _report() -> DeveloperReport:
    return build_developer_report(_context(), _impact(), _risk(), _history())


def test_report_sections_are_complete():
    report = _report()
    payload = report.to_dict()

    assert payload["sections"]["change"]["summary"] == "Refactor authentication session handling."
    assert payload["sections"]["context"]["artifact_count"] == 3
    assert payload["sections"]["impact"]["finding_count"] == 2
    assert payload["sections"]["history"]["finding_count"] == 1
    assert payload["sections"]["risk"]["finding_count"] == 2
    assert payload["sections"]["risk"]["highest_severity"] == "high"


def test_report_preserves_evidence():
    report = _report()
    impact_finding = next(f for f in report.findings if f.id == "impact:src/auth/session.py:modifies")
    risk_finding = next(f for f in report.findings if f.id == "risk:0:security")

    assert impact_finding.evidence[0].description == "path appears in changed_files"
    assert impact_finding.evidence[0].evidence_type == "DIRECT_EVIDENCE"
    assert impact_finding.evidence_strength == "confirmed"
    assert risk_finding.evidence[0].description == "authorization check enforces the session policy"


def test_report_labels_inference():
    report = _report()
    risk_finding = next(f for f in report.findings if f.id == "risk:0:security")
    context_doc = next(f for f in report.findings if f.id == "context:README.md")

    assert risk_finding.is_inference is True
    assert context_doc.is_inference is True


def test_report_finding_ids_are_stable():
    first = _report()
    second = _report()

    assert [finding.id for finding in first.findings] == [finding.id for finding in second.findings]
    assert "impact:src/auth/session.py:modifies" in {finding.id for finding in first.findings}
    assert "risk:0:security" in {finding.id for finding in first.findings}


def test_report_graph_node_linking_matches_change_impact_map():
    context = _context()
    impact = _impact()
    risk = _risk()
    history = _history()
    report = build_developer_report(context, impact, risk, history)
    graph = build_change_impact_map(context, impact, risk, history)
    graph_ids = {node.id for node in graph.nodes}

    linked = [finding for finding in report.findings if finding.graph_node_id]
    assert linked
    for finding in linked:
        assert finding.graph_node_id in graph_ids

    risk_finding = next(f for f in report.findings if f.id == "risk:0:security")
    assert risk_finding.graph_node_id == "risk:0:security"

    readme_context = next(f for f in report.findings if f.id == "context:README.md")
    assert readme_context.graph_node_id is None


def test_report_preserves_full_history_details():
    report = _report()
    history_finding = next(f for f in report.findings if f.id == "history:src/auth/session.py")

    assert "Refactor session handling" in history_finding.description
    assert any("Refactor session handling" in item.description for item in history_finding.evidence)


def test_report_includes_context_artifacts_not_on_change_impact_map():
    report = _report()
    readme = next(f for f in report.findings if f.id == "context:README.md")

    assert readme.graph_node_id is None
    assert any(gap.affected_artifact == "README.md" for gap in report.evidence_gaps)


def test_report_next_actions_prioritized_by_severity():
    report = _report()

    assert len(report.next_actions) == 2
    assert report.next_actions[0].severity == "high"
    assert report.next_actions[0].priority == 1
    assert report.next_actions[1].severity == "low"
    assert report.next_actions[0].source_finding_id == "risk:0:security"


def test_report_surfaces_upstream_errors():
    context = RepositoryContext(
        repository_url="https://github.com/example/repo",
        owner="example",
        name="repo",
        change_summary="Broken change.",
        error="Repository retrieval failed",
    )
    impact = ImpactAnalysis(
        repository_url=context.repository_url,
        owner=context.owner,
        name=context.name,
        change_summary=context.change_summary,
        error="No artifacts to analyze",
    )
    risk = RiskAnalysis(
        repository_url=context.repository_url,
        owner=context.owner,
        name=context.name,
        change_summary=context.change_summary,
        error="No impact findings available",
    )

    report = build_developer_report(context, impact, risk)

    assert report.error is not None
    assert "Phase 2 context" in report.error
    assert "Phase 4 impact" in report.error
    assert "Phase 5 risk" in report.error
    assert any("Upstream analysis reported errors" in gap.description for gap in report.evidence_gaps)


def test_report_json_serialization_round_trip(tmp_path):
    report = _report()
    output = serialize_developer_report(report, tmp_path / "devflow-report.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["repository_url"] == "https://github.com/example/repo"
    assert payload["changed_files"] == ["src/auth/session.py"]
    assert payload["findings"]
    assert payload["next_actions"]
    assert payload["sections"]["risk"]["highest_severity"] == "high"


def test_write_frontend_report_payload_writes_public_json(tmp_path):
    report = _report()
    output = write_frontend_report_payload(report, frontend_dir=tmp_path)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert output.name == "devflow-report.json"
    assert payload["change_summary"] == "Refactor authentication session handling."


def test_pipeline_integration_writes_graph_and_report():
    with patch("devflow.__main__.build_context") as mock_context, \
         patch("devflow.__main__.build_historical_context") as mock_history, \
         patch("devflow.__main__.build_impact_analysis") as mock_impact, \
         patch("devflow.__main__.build_risk_analysis") as mock_risk, \
         patch("devflow.__main__.write_frontend_graph_payload") as mock_graph_write, \
         patch("devflow.__main__.write_frontend_report_payload") as mock_report_write, \
         patch("devflow.__main__.accept_input") as mock_accept:
        context = _context()
        impact = _impact()
        risk = _risk()
        history = _history()
        mock_accept.return_value = (object(), object())
        mock_context.return_value = context
        mock_history.return_value = history
        mock_impact.return_value = impact
        mock_risk.return_value = risk

        graph, report = _analyze_repository(
            "https://github.com/example/repo",
            "Refactor authentication session handling.",
        )

        assert graph.repository_url == context.repository_url
        assert report.change_summary == context.change_summary
        mock_graph_write.assert_called_once()
        mock_report_write.assert_called_once()
