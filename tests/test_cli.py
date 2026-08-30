"""Tests for the developer-facing `devflow` CLI.

These cover argument wiring and the findings view.  Commands that clone a
repository or invoke the resolution gates are exercised elsewhere; here we only
assert that they dispatch to the right entry point with the right arguments.
"""

import json

import pytest

from devflow.cli import build_parser, main

WATSONX_ENV = (
    "DEVFLOW_WATSONX_APIKEY",
    "DEVFLOW_WATSONX_PROJECT_ID",
    "DEVFLOW_WATSONX_CACHE",
    "DEVFLOW_WATSONX_DISABLE",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Isolate from both the environment and a populated local .env file."""
    for name in WATSONX_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("devflow.watsonx._client.load_dotenv", lambda *a, **k: [])


def _report_file(tmp_path, *, with_prioritization=False):
    findings = [
        {
            "id": "risk:0:code",
            "category": "risk",
            "title": "HIGH code risk",
            "description": "Wide blast radius.",
            "affected_artifacts": ["src/session.py"],
            "severity": "high",
            "evidence": [
                {
                    "artifact": "src/session.py",
                    "description": "12 file(s) reach it through static import edges.",
                    "evidence_type": "DIRECT_EVIDENCE",
                }
            ],
            "is_inference": False,
        },
        {
            "id": "risk:1:test_gap",
            "category": "risk",
            "title": "LOW test gap",
            "description": "No covering test.",
            "affected_artifacts": ["src/util.py"],
            "severity": "low",
            "evidence": [],
            "is_inference": False,
        },
    ]
    payload = {
        "repository_url": "https://github.com/example/repo",
        "change_summary": "Refactor session handling.",
        "findings": findings,
    }
    if with_prioritization:
        payload["prioritization"] = {
            "source": "watsonx",
            "model_id": "ibm/granite-3-3-8b-instruct",
            "from_cache": True,
            "discarded_finding_ids": ["ghost-finding"],
            "appended_finding_ids": [],
            "error": None,
            "rankings": [
                {
                    "finding_id": "risk:1:test_gap",
                    "rank": 1,
                    "rationale": "Untested and reachable.",
                    "severity": "low",
                    "title": "LOW test gap",
                    "source": "watsonx",
                },
                {
                    "finding_id": "risk:0:code",
                    "rank": 2,
                    "rationale": "Already covered.",
                    "severity": "high",
                    "title": "HIGH code risk",
                    "source": "watsonx",
                },
            ],
        }
    path = tmp_path / "devflow-report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Parser surface
# ---------------------------------------------------------------------------


def test_cli_exposes_exactly_the_five_journey_commands():
    parser = build_parser()
    subparsers = [
        action for action in parser._actions if hasattr(action, "choices") and action.choices
    ]
    commands = set(subparsers[0].choices)
    assert commands == {"analyze", "findings", "resolve", "apply", "validate"}


def test_analyze_requires_a_repository_and_a_change():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["analyze", "https://github.com/example/repo"])


def test_validate_requires_its_verification_inputs():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["validate", "res_1", "--local-path", "/tmp/x"])


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------


def test_findings_reports_a_missing_report_clearly(tmp_path, capsys):
    exit_code = main(["findings", "--report", str(tmp_path / "absent.json")])
    assert exit_code == 1
    assert "devflow analyze" in capsys.readouterr().err


def test_findings_ranks_deterministically_without_credentials(tmp_path, capsys):
    exit_code = main(["findings", "--report", str(_report_file(tmp_path))])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Findings ranked by: deterministic" in out
    assert "not configured" in out
    # High severity outranks low when DevFlow orders the list itself.
    assert out.index("risk:0:code") < out.index("risk:1:test_gap")


def test_findings_reuses_a_stored_prioritization(tmp_path, capsys):
    exit_code = main(["findings", "--report", str(_report_file(tmp_path, with_prioritization=True))])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "IBM watsonx.ai (cached)" in out
    assert "Untested and reachable." in out
    # The stored watsonx order is honoured, not silently re-sorted by severity.
    assert out.index("risk:1:test_gap") < out.index("risk:0:code")


def test_findings_surfaces_discarded_model_ids(tmp_path, capsys):
    main(["findings", "--report", str(_report_file(tmp_path, with_prioritization=True))])
    out = capsys.readouterr().out
    assert "discarded 1 model id(s)" in out
    assert "ghost-finding" in out


def test_findings_refresh_ignores_the_stored_ranking(tmp_path, capsys):
    report = _report_file(tmp_path, with_prioritization=True)
    main(["findings", "--report", str(report), "--refresh", "--no-watsonx"])
    out = capsys.readouterr().out
    assert "Findings ranked by: deterministic" in out


def test_findings_json_mode_emits_the_raw_ranking(tmp_path, capsys):
    main(["findings", "--report", str(_report_file(tmp_path)), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "deterministic"
    assert [entry["finding_id"] for entry in payload["rankings"]] == [
        "risk:0:code",
        "risk:1:test_gap",
    ]


def test_findings_top_limits_the_listing(tmp_path, capsys):
    main(["findings", "--report", str(_report_file(tmp_path)), "--top", "1"])
    out = capsys.readouterr().out
    assert "risk:0:code" in out
    assert "1 more" in out


def test_findings_handles_an_empty_report(tmp_path, capsys):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"findings": []}), encoding="utf-8")
    assert main(["findings", "--report", str(path)]) == 0
    assert "No findings" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Delegation to the Phase 8 resolution gates
# ---------------------------------------------------------------------------


def _record_delegation(monkeypatch) -> dict:
    """Capture the argv the resolution CLI is called with, without running it."""
    seen: dict = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 0

    monkeypatch.setattr("devflow.resolution.cli.main", fake_main)
    return seen


def test_resolve_delegates_to_the_resolution_request_gate(monkeypatch):
    seen = _record_delegation(monkeypatch)
    assert main(["resolve", "risk:0:code", "--report", "r.json"]) == 0
    assert seen["argv"] == ["request", "risk:0:code", "--report", "r.json"]


def test_apply_delegates_to_the_ingest_fix_gate(monkeypatch):
    seen = _record_delegation(monkeypatch)
    assert main(["apply", "res_1", "fix.md"]) == 0
    assert seen["argv"] == ["ingest-fix", "res_1", "fix.md"]


def test_validate_delegates_with_every_verification_argument(monkeypatch):
    seen = _record_delegation(monkeypatch)
    exit_code = main(
        [
            "validate",
            "res_1",
            "--local-path",
            "/tmp/checkout",
            "--result",
            "result.md",
            "--test-command",
            "pytest -q",
        ]
    )
    assert exit_code == 0
    assert seen["argv"] == [
        "validate",
        "res_1",
        "--local-path",
        "/tmp/checkout",
        "--result",
        "result.md",
        "--test-command",
        "pytest -q",
    ]
