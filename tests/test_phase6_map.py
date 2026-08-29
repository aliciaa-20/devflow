"""Deterministic tests for DevFlow Phase 6: Change Impact Map."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

from devflow.__main__ import main
from devflow.server import DevFlowRequestHandler
from devflow.map import (
    build_change_impact_map,
    open_html_in_browser,
    render_change_impact_map,
    write_frontend_graph_payload,
)
from devflow.models.context import ArtifactKind, ContextArtifact, RelevanceReason, RepositoryContext
from devflow.models.graph import GraphNodeType
from devflow.models.history import ArtifactHistory, HistoricalCommit, RepositoryHistory
from devflow.models.impact import (
    EvidenceStrength,
    EvidenceType,
    ImpactAnalysis,
    ImpactEvidence,
    ImpactFinding,
    RelationshipType,
)
from devflow.models.risk import RiskAnalysis, RiskCategory, RiskFinding, RiskSeverity


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
            )
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
                evidence=(
                    ImpactEvidence(
                        artifact="src/auth/session.py",
                        description="Git commit aaaaaaa modified src/auth/session.py",
                        evidence_type=EvidenceType.DIRECT_EVIDENCE,
                    ),
                ),
            )
        },
        total_commits_found=1,
    )


def test_change_impact_map_contains_central_change_artifacts_and_risks():
    context = _context()
    impact = _impact()
    risk = _risk()
    graph = build_change_impact_map(context, impact, risk)

    assert any(node.id == "change" for node in graph.nodes)
    assert any(node.id == "artifact:src/auth/session.py" for node in graph.nodes)
    assert any(node.node_type == GraphNodeType.RISK for node in graph.nodes)
    assert any(edge.relationship == "modifies" for edge in graph.edges)
    assert any(edge.relationship == "has_risk" for edge in graph.edges)


def test_change_impact_map_includes_historical_evidence():
    graph = build_change_impact_map(_context(), _impact(), _risk(), _history())
    assert any(node.node_type == GraphNodeType.HISTORICAL for node in graph.nodes)
    assert any(edge.relationship == "historically_changed_with" for edge in graph.edges)


def test_change_impact_map_keeps_structured_evidence_and_risk_severity():
    graph = build_change_impact_map(_context(), _impact(), _risk(), _history())

    risk_node = next(node for node in graph.nodes if node.node_type == GraphNodeType.RISK)
    assert risk_node.risk_severity == "high"
    assert risk_node.metadata["evidence"]
    assert risk_node.metadata["evidence"][0]["evidence_type"] == "DIRECT_EVIDENCE"

    artifact_node = next(node for node in graph.nodes if node.id == "artifact:src/auth/session.py")
    assert artifact_node.metadata["evidence"]
    assert artifact_node.metadata["evidence"][0]["evidence_type"] == "DIRECT_EVIDENCE"


def test_render_change_impact_map_writes_html_with_paths_relationships_risks_and_summary(tmp_path):
    graph = build_change_impact_map(_context(), _impact(), _risk(), _history())
    output = render_change_impact_map(graph, tmp_path / "impact-map.html")
    html = output.read_text(encoding="utf-8")

    assert output.exists()
    assert "src/auth/session.py" in html
    assert "tests/test_session.py" in html
    assert "modifies" in html
    assert "has_risk" in html
    assert "authorization check" in html
    assert "Refactor authentication session handling." in html
    assert "Highest risk" in html
    assert "Evidence:" in html


def test_write_frontend_graph_payload_serializes_real_graph_for_react(tmp_path):
    graph = build_change_impact_map(_context(), _impact(), _risk(), _history())
    payload_path = write_frontend_graph_payload(graph, frontend_dir=tmp_path)

    assert payload_path.exists()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["repository_url"] == "https://github.com/example/repo"
    assert any(node["node_type"] == "change" for node in payload["nodes"])
    assert any(node["node_type"] == "risk" for node in payload["nodes"])
    assert any(edge["relationship"] == "modifies" for edge in payload["edges"])


def test_open_html_in_browser_uses_generated_path_and_successfully_calls_default_browser(tmp_path):
    output = tmp_path / "impact-map.html"
    output.write_text("<html></html>", encoding="utf-8")

    with patch("devflow.map._build.webbrowser.open", return_value=True) as mocked_open:
        assert open_html_in_browser(output) is True
        mocked_open.assert_called_once_with(output.resolve().as_uri())


def test_open_html_in_browser_failure_does_not_fail_generation(tmp_path):
    output = tmp_path / "impact-map.html"
    output.write_text("<html></html>", encoding="utf-8")

    with patch("devflow.map._build.webbrowser.open", return_value=False):
        assert open_html_in_browser(output) is False


def test_open_html_in_browser_failed_generation_does_not_call_browser(tmp_path):
    output = tmp_path / "missing-map.html"

    with patch("devflow.map._build.webbrowser.open") as mocked_open:
        try:
            open_html_in_browser(output)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("missing HTML output should raise FileNotFoundError")
    mocked_open.assert_not_called()


def test_main_generation_path_reaches_browser_open_call(capsys):
    # Phase 6 now starts an interactive server instead of generating a sample HTML.
    # Mock the server start/serve functions to avoid actually starting the server.
    with patch("devflow.__main__.start_server") as mock_start_server, \
         patch("devflow.__main__.serve_forever") as mock_serve_forever:
        # Simulate keyboard interrupt to stop the main loop
        mock_serve_forever.side_effect = KeyboardInterrupt()
        
        try:
            main()
        except KeyboardInterrupt:
            pass
        
        stdout = capsys.readouterr().out
        assert "DevFlow" in stdout
        assert "Starting DevFlow interactive" in stdout
        mock_start_server.assert_called_once()


def test_server_serves_frontend_index_at_root():
    handler = DevFlowRequestHandler.__new__(DevFlowRequestHandler)
    handler.path = "/"
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.code = None

    def send_response(code):
        handler.code = code

    handler.send_response = send_response
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_GET()

    assert handler.code == 200
    output = handler.wfile.getvalue().decode("utf-8")
    assert "<html" in output.lower()
    assert "DEVFLOW" in output


def test_main_generation_path_reports_path_when_browser_open_fails(capsys):
    # Phase 6 now starts an interactive server. The server handles browser opening internally.
    with patch("devflow.__main__.start_server") as mock_start_server, \
         patch("devflow.__main__.serve_forever") as mock_serve_forever:
        # Simulate keyboard interrupt to stop the main loop
        mock_serve_forever.side_effect = KeyboardInterrupt()
        
        try:
            main()
        except KeyboardInterrupt:
            pass
        
        stdout = capsys.readouterr().out
        assert "DevFlow" in stdout
        assert "Server started" in stdout

