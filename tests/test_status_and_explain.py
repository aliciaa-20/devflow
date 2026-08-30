"""Tests for `devflow status` and `devflow explain`.

These are presentation surfaces, so the properties that matter are honesty
ones: a finding is only reported resolved when its own resolution succeeded,
a disagreement between Bob's claim and DevFlow's verified result is shown, and
evidence keeps its strength labelling.
"""

import json

import pytest

from devflow.explain import explain_finding, find_finding, load_repository_graph
from devflow.models.repository_graph import (
    RepositoryGraphEdge,
    RepositoryGraphNode,
    RepositoryKnowledgeGraph,
    RepositoryNodeType,
    RepositoryRelationshipType,
    file_node_id,
)
from devflow.status import build_status, load_sessions


@pytest.fixture(autouse=True)
def _no_colour(monkeypatch):
    """Assert on text, not escape codes."""
    monkeypatch.setenv("NO_COLOR", "1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _report(**overrides):
    report = {
        "repository_url": "https://github.com/example/repo",
        "change_summary": "Refactor session handling.",
        "generated_at": "2026-08-30T00:00:00Z",
        "findings": [
            {
                "id": "risk:0:code",
                "category": "risk",
                "title": "HIGH code risk",
                "description": "session.py has 2 dependents.",
                "affected_artifacts": ["src/session.py"],
                "severity": "high",
                "evidence": [
                    {
                        "artifact": "src/session.py",
                        "description": "2 file(s) reach it through static import edges.",
                        "evidence_type": "DIRECT_EVIDENCE",
                    },
                    {
                        "artifact": "src/session.py",
                        "description": "path keywords match change keywords",
                        "evidence_type": "DERIVED_RELATIONSHIP",
                    },
                ],
                "evidence_strength": "likely",
                "is_inference": True,
                "recommendation": "Review importing callers.",
            },
            {
                "id": "risk:1:test_gap",
                "category": "risk",
                "title": "LOW test gap",
                "description": "No covering test.",
                "affected_artifacts": ["src/session.py"],
                "severity": "low",
                "evidence": [],
                "is_inference": False,
            },
            {
                "id": "history:src/session.py",
                "category": "historical",
                "title": "src/session.py",
                "description": "Changed before.",
                "affected_artifacts": ["src/session.py"],
                "evidence": [
                    {
                        "artifact": "src/session.py",
                        "description": 'Git commit abc1234 modified it. Message: "fix session leak".',
                        "evidence_type": "DIRECT_EVIDENCE",
                    }
                ],
            },
        ],
        "prioritization": {
            "source": "watsonx",
            "model_id": "ibm/granite-4-h-small",
            "from_cache": False,
            "discarded_finding_ids": [],
            "appended_finding_ids": [],
            "error": None,
            "rankings": [
                {
                    "finding_id": "risk:0:code",
                    "rank": 1,
                    "rationale": "Widest blast radius.",
                    "severity": "high",
                    "title": "HIGH code risk",
                    "source": "watsonx",
                }
            ],
        },
    }
    report.update(overrides)
    return report


def _session(finding_id, *, status="validated", final=None, claimed=None, passed=True):
    session = {
        "id": f"res_test_{finding_id.replace(':', '-')}",
        "repository_url": "https://github.com/example/repo",
        "change_summary": "Refactor session handling.",
        "finding_id": finding_id,
        "finding_snapshot": {"affected_artifacts": ["src/session.py"]},
        "status": status,
        "created_at": "2026-08-30T01:00:00Z",
        "investigate_gate": {
            "gate": "investigate",
            "decision": "approved",
            "decided_by": "dev",
            "decided_at": "2026-08-30T01:00:00Z",
        },
        "apply_gate": None,
    }
    if final:
        session["outcome"] = {
            "modified_files": ["src/session.py"],
            "change_rationale": "why",
            "tests_added_or_updated": ["tests/test_session.py"],
            "tests_executed": [
                {"command": "pytest -q", "passed": passed, "exit_code": 0 if passed else 1}
            ],
            "final_status": final,
            "bob_claimed_status": claimed,
            "remaining_risks": [],
            "raw_bob_output_path": "x.md",
            "completed_at": "2026-08-30T02:00:00Z",
        }
    return session


def _graph():
    session = RepositoryGraphNode(
        id=file_node_id(RepositoryNodeType.SOURCE_FILE, "src/session.py"),
        label="session.py",
        node_type=RepositoryNodeType.SOURCE_FILE,
        description="",
        path="src/session.py",
    )
    auth = RepositoryGraphNode(
        id=file_node_id(RepositoryNodeType.SOURCE_FILE, "src/auth.py"),
        label="auth.py",
        node_type=RepositoryNodeType.SOURCE_FILE,
        description="",
        path="src/auth.py",
    )
    test = RepositoryGraphNode(
        id=file_node_id(RepositoryNodeType.TEST_FILE, "tests/test_session.py"),
        label="test_session.py",
        node_type=RepositoryNodeType.TEST_FILE,
        description="",
        path="tests/test_session.py",
    )
    graph = RepositoryKnowledgeGraph(
        repository_url="https://github.com/example/repo", owner="example", name="repo"
    )
    graph.nodes = [session, auth, test]
    graph.edges = [
        RepositoryGraphEdge(auth.id, session.id, RepositoryRelationshipType.IMPORTS, "d"),
        RepositoryGraphEdge(session.id, auth.id, RepositoryRelationshipType.IMPORTED_BY, "d"),
        RepositoryGraphEdge(session.id, test.id, RepositoryRelationshipType.TESTED_BY, "d"),
    ]
    return graph


@pytest.fixture
def graph_file(tmp_path):
    path = tmp_path / "repo-graph.json"
    path.write_text(json.dumps(_graph().to_dict()), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# status: the honesty rules
# ---------------------------------------------------------------------------


def test_a_finding_is_open_until_its_own_resolution_succeeds():
    out = "\n".join(build_status(_report(), []))
    assert "risk:0:code" in out
    assert "0 resolved  /  2 remaining" in out


def test_resolving_one_finding_does_not_resolve_its_file_siblings():
    """Both risks touch src/session.py; only the resolved one may be marked."""
    sessions = [_session("risk:0:code", final="RESOLVED", claimed="RESOLVED")]
    lines = build_status(_report(), sessions)
    out = "\n".join(lines)
    assert "1 resolved  /  1 remaining" in out
    code_line = next(line for line in lines if "risk:0:code" in line and "risk" in line)
    gap_line = next(line for line in lines if "risk:1:test_gap" in line)
    assert "resolved" in code_line
    assert "open" in gap_line


def test_a_failed_resolution_is_not_reported_as_open_or_resolved():
    sessions = [
        _session("risk:0:code", final="VALIDATION_FAILED", claimed="RESOLVED", passed=False)
    ]
    lines = build_status(_report(), sessions)
    code_line = next(line for line in lines if "risk:0:code" in line and "MEDIUM" not in line)
    assert "attempted, not resolved" in code_line
    assert "0 resolved  /  2 remaining" in "\n".join(lines)


def test_disagreement_between_bob_and_devflow_is_surfaced():
    sessions = [
        _session("risk:0:code", final="VALIDATION_FAILED", claimed="RESOLVED", passed=False)
    ]
    out = "\n".join(build_status(_report(), sessions))
    assert "DISAGREES" in out
    assert "FAIL" in out


def test_agreement_between_bob_and_devflow_is_labelled_calmly():
    sessions = [_session("risk:0:code", final="RESOLVED", claimed="RESOLVED")]
    out = "\n".join(build_status(_report(), sessions))
    assert "DISAGREES" not in out
    assert "matches DevFlow's verified result" in out


def test_status_reports_the_prioritization_source():
    out = "\n".join(build_status(_report(), []))
    assert "IBM watsonx.ai" in out
    assert "granite-4-h-small" in out


def test_status_flags_discarded_model_ids():
    report = _report()
    report["prioritization"]["discarded_finding_ids"] = ["ghost"]
    out = "\n".join(build_status(report, []))
    assert "1 not present in DevFlow findings" in out


def test_status_without_an_analysis_says_so():
    out = "\n".join(build_status(None, []))
    assert "run `devflow analyze` first" in out


def test_status_names_the_next_action_for_an_open_session():
    sessions = [_session("risk:0:code", status="investigation_approved")]
    out = "\n".join(build_status(_report(), sessions))
    assert "devflow apply" in out


def test_load_sessions_ignores_unreadable_state(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "state.json").write_text("{ not json", encoding="utf-8")
    assert load_sessions(tmp_path) == []


def test_load_sessions_returns_empty_for_missing_directory(tmp_path):
    assert load_sessions(tmp_path / "absent") == []


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------


def test_explain_rejects_an_unknown_finding_and_suggests_real_ones():
    with pytest.raises(ValueError, match="risk:0:code"):
        explain_finding(_report(), "does-not-exist")


def test_explain_renders_the_blast_radius_from_real_edges(graph_file):
    out = "\n".join(explain_finding(_report(), "risk:0:code", repo_graph_path=graph_file))
    assert "BLAST RADIUS" in out
    assert "src/auth.py" in out
    assert "direct import" in out


def test_explain_labels_evidence_by_strength(graph_file):
    out = "\n".join(explain_finding(_report(), "risk:0:code", repo_graph_path=graph_file))
    assert "observed fact" in out
    assert "derived relationship" in out


def test_explain_marks_an_inference_finding_as_not_a_defect(graph_file):
    out = "\n".join(explain_finding(_report(), "risk:0:code", repo_graph_path=graph_file))
    assert "not an established defect" in out


def test_explain_marks_a_direct_finding_as_supported(graph_file):
    out = "\n".join(explain_finding(_report(), "risk:1:test_gap", repo_graph_path=graph_file))
    assert "supported by direct repository evidence" in out


def test_explain_shows_test_coverage(graph_file):
    out = "\n".join(explain_finding(_report(), "risk:0:code", repo_graph_path=graph_file))
    assert "tests/test_session.py" in out


def test_explain_attributes_the_ranking_to_watsonx(graph_file):
    out = "\n".join(explain_finding(_report(), "risk:0:code", repo_graph_path=graph_file))
    assert "IBM watsonx.ai judgment" in out
    assert "Widest blast radius." in out


def test_explain_renders_commit_subjects_from_history(graph_file):
    out = "\n".join(explain_finding(_report(), "risk:0:code", repo_graph_path=graph_file))
    assert "HISTORY" in out
    assert "fix session leak" in out
    assert "abc1234" in out


def test_explain_degrades_without_a_repository_graph(tmp_path):
    out = "\n".join(
        explain_finding(_report(), "risk:0:code", repo_graph_path=tmp_path / "absent.json")
    )
    assert "no repository graph on disk" in out
    assert "WHY THIS MATTERS" in out


def test_explain_does_not_repeat_severity_in_the_title(graph_file):
    lines = explain_finding(_report(), "risk:0:code", repo_graph_path=graph_file)
    header = next(line for line in lines if "HIGH" in line)
    assert header.count("HIGH") == 1


def test_load_repository_graph_tolerates_corrupt_payloads(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text("{ not json", encoding="utf-8")
    assert load_repository_graph(path) is None


def test_find_finding_returns_none_for_unknown_id():
    assert find_finding(_report(), "nope") is None
