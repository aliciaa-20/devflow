"""Tests for DevFlow Phase 8 (Bob Resolution).

All fixtures are local -- no network, no live Bob invocation. Bob's markdown
output is simulated as fixture text, matching the fixed headings defined in
.bob/custom_modes.yaml's resolver mode.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from devflow.models.resolution import (
    FinalStatus,
    ResolutionIngestError,
    ResolutionRequest,
    ResolutionStatus,
)
from devflow.resolution._build import (
    create_resolution_request,
    decide_apply_gate,
    decide_investigation_gate,
    ingest_proposed_fix,
    run_validation,
)
from devflow.resolution._ingest import parse_proposed_fix, parse_resolution_summary
from devflow.resolution._sessions import session_dir

SAMPLE_FINDING = {
    "id": "finding-1",
    "category": "risk",
    "title": "Missing test coverage for auth check",
    "description": "auth.py changed but no test exercises the new branch.",
    "affected_artifacts": ["src/auth.py"],
    "relationship": "modifies",
    "potential_impact": "Regression risk in auth flow.",
    "severity": "high",
    "evidence": [
        {
            "artifact": "src/auth.py",
            "description": "Direct diff evidence.",
            "evidence_type": "DIRECT_EVIDENCE",
            "confidence": "confirmed",
        }
    ],
    "evidence_strength": "CONFIRMED",
    "is_inference": False,
    "recommendation": "Add a test for the new auth branch.",
    "graph_node_id": "source:src/auth.py",
}

SAMPLE_REPORT = {
    "repository_url": "https://github.com/example/project",
    "owner": "example",
    "name": "project",
    "change_summary": "Refactor auth handling.",
    "findings": [SAMPLE_FINDING],
}

WELL_FORMED_PROPOSED_FIX = """\
### Finding

Missing test coverage for auth check.

### Root Cause

The new branch in auth.py is not covered by any existing test.

### Proposed Change

Add a unit test exercising the new auth branch.

### Files to Modify

- tests/test_auth.py

### Tests

- tests/test_auth.py::test_new_auth_branch

### Validation

Run `pytest tests/test_auth.py`.
"""

MALFORMED_PROPOSED_FIX = """\
### Finding

Missing test coverage for auth check.

### Proposed Change

Add a unit test exercising the new auth branch.
"""

WELL_FORMED_RESOLUTION_RESOLVED = """\
## Resolution Summary

Added a test covering the new auth branch.

## Root Cause

The new branch in auth.py was not covered by any existing test.

## Files Changed

- tests/test_auth.py

## Tests Added / Updated

- tests/test_auth.py::test_new_auth_branch

## Tests Executed

pytest tests/test_auth.py -> 1 passed

## Validation

All tests passed.

## Remaining Risks

- None identified.

## Final Status

RESOLVED
"""


def _init_git_repo(root):
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "real_file.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)


def _make_request(tmp_path):
    return create_resolution_request(
        SAMPLE_REPORT, "finding-1", bob_sessions_dir=tmp_path / "bob_sessions"
    )


def test_create_resolution_request_snapshots_finding_verbatim(tmp_path):
    request = _make_request(tmp_path)
    assert request.finding_snapshot == SAMPLE_FINDING
    assert request.finding_id == "finding-1"
    assert request.graph_node_id == "source:src/auth.py"
    assert request.status == ResolutionStatus.REQUESTED


def test_investigation_gate_rejection_stops_workflow(tmp_path):
    request = _make_request(tmp_path)
    request = decide_investigation_gate(
        request,
        approved=False,
        decided_by="dev",
        bob_sessions_dir=tmp_path / "bob_sessions",
    )
    assert request.status == ResolutionStatus.REJECTED_BEFORE_INVESTIGATION
    assert request.investigate_gate.decision.value == "rejected"

    with pytest.raises(ValueError):
        ingest_proposed_fix(
            request, tmp_path / "does-not-matter.md", bob_sessions_dir=tmp_path / "bob_sessions"
        )


def test_ingest_proposed_fix_requires_investigation_gate_approved_first(tmp_path):
    request = _make_request(tmp_path)
    bob_output = tmp_path / "bob-output.md"
    bob_output.write_text(WELL_FORMED_PROPOSED_FIX, encoding="utf-8")

    with pytest.raises(ValueError):
        ingest_proposed_fix(request, bob_output, bob_sessions_dir=tmp_path / "bob_sessions")


def test_parse_proposed_fix_from_well_formed_bob_output(tmp_path):
    fix = parse_proposed_fix(WELL_FORMED_PROPOSED_FIX, raw_bob_output_path="irrelevant.md")
    assert fix.summary == "Add a unit test exercising the new auth branch."
    assert fix.files_to_modify == ("tests/test_auth.py",)
    assert fix.tests_to_add_or_update == ("tests/test_auth.py::test_new_auth_branch",)
    assert "pytest" in fix.validation_plan


def test_parse_proposed_fix_raises_on_malformed_output():
    with pytest.raises(ResolutionIngestError):
        parse_proposed_fix(MALFORMED_PROPOSED_FIX, raw_bob_output_path="irrelevant.md")


def test_parse_resolution_summary_rejects_unrecognized_final_status():
    bad_text = WELL_FORMED_RESOLUTION_RESOLVED.replace("RESOLVED", "SORT OF DONE")
    with pytest.raises(ResolutionIngestError):
        parse_resolution_summary(bad_text)


def test_apply_gate_rejection_stops_before_validation(tmp_path):
    bob_sessions_dir = tmp_path / "bob_sessions"
    request = _make_request(tmp_path)
    request = decide_investigation_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=bob_sessions_dir
    )
    bob_output = tmp_path / "bob-output.md"
    bob_output.write_text(WELL_FORMED_PROPOSED_FIX, encoding="utf-8")
    request = ingest_proposed_fix(request, bob_output, bob_sessions_dir=bob_sessions_dir)

    request = decide_apply_gate(
        request, approved=False, decided_by="dev", bob_sessions_dir=bob_sessions_dir
    )
    assert request.status == ResolutionStatus.REJECTED_BEFORE_APPLY

    with pytest.raises(ValueError):
        run_validation(
            request,
            local_path=tmp_path,
            raw_result_output_path=tmp_path / "does-not-matter.md",
            test_command="true",
            bob_sessions_dir=bob_sessions_dir,
        )


def _run_to_fix_approved(tmp_path, bob_sessions_dir):
    request = _make_request(tmp_path)
    request = decide_investigation_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=bob_sessions_dir
    )
    bob_output = tmp_path / "bob-output.md"
    bob_output.write_text(WELL_FORMED_PROPOSED_FIX, encoding="utf-8")
    request = ingest_proposed_fix(request, bob_output, bob_sessions_dir=bob_sessions_dir)
    request = decide_apply_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=bob_sessions_dir
    )
    assert request.status == ResolutionStatus.FIX_APPROVED
    return request


def test_run_validation_records_actual_subprocess_result(tmp_path):
    bob_sessions_dir = tmp_path / "bob_sessions"
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    request = _run_to_fix_approved(tmp_path, bob_sessions_dir)
    result_file = tmp_path / "bob-result.md"
    result_file.write_text(WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")

    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="true",
        bob_sessions_dir=bob_sessions_dir,
    )

    assert request.status == ResolutionStatus.VALIDATED
    record = request.outcome.tests_executed[0]
    assert record.command == "true"
    assert record.passed is True
    assert record.exit_code == 0
    assert request.outcome.final_status == FinalStatus.RESOLVED


def test_run_validation_downgrades_status_when_bob_claims_resolved_but_tests_fail(tmp_path):
    bob_sessions_dir = tmp_path / "bob_sessions"
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    request = _run_to_fix_approved(tmp_path, bob_sessions_dir)
    result_file = tmp_path / "bob-result.md"
    result_file.write_text(WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")

    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="false",
        bob_sessions_dir=bob_sessions_dir,
    )

    assert request.outcome.tests_executed[0].passed is False
    assert request.outcome.final_status == FinalStatus.VALIDATION_FAILED, (
        "an unverified RESOLVED claim must never survive a real failing test run"
    )


def test_modified_files_come_from_git_diff_not_bob_claim(tmp_path):
    bob_sessions_dir = tmp_path / "bob_sessions"
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    # Make a real, uncommitted change to a file Bob's own output does not mention.
    (repo_dir / "real_file.py").write_text("VALUE = 2\n", encoding="utf-8")

    request = _run_to_fix_approved(tmp_path, bob_sessions_dir)
    result_file = tmp_path / "bob-result.md"
    # Bob's own "Files Changed" section claims a different file entirely.
    claimed_text = WELL_FORMED_RESOLUTION_RESOLVED.replace(
        "- tests/test_auth.py", "- totally/unrelated/path.py"
    )
    result_file.write_text(claimed_text, encoding="utf-8")

    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="true",
        bob_sessions_dir=bob_sessions_dir,
    )

    assert request.outcome.modified_files == ("real_file.py",)
    assert "totally/unrelated/path.py" not in request.outcome.modified_files


def test_session_files_written_at_each_transition(tmp_path):
    bob_sessions_dir = tmp_path / "bob_sessions"
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    request = _run_to_fix_approved(tmp_path, bob_sessions_dir)
    result_file = tmp_path / "bob-result.md"
    result_file.write_text(WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")
    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="true",
        bob_sessions_dir=bob_sessions_dir,
    )

    directory = session_dir(request.id, bob_sessions_dir=bob_sessions_dir)
    for filename in (
        "request.json",
        "state.json",
        "bob_investigation.md",
        "bob_result.md",
        "test_run.txt",
    ):
        assert (directory / filename).exists(), f"expected {filename} to be written"

    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "validated"


def test_resolution_request_to_dict_round_trips_through_json(tmp_path):
    bob_sessions_dir = tmp_path / "bob_sessions"
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    request = _run_to_fix_approved(tmp_path, bob_sessions_dir)
    result_file = tmp_path / "bob-result.md"
    result_file.write_text(WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")
    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="true",
        bob_sessions_dir=bob_sessions_dir,
    )

    round_tripped = json.loads(json.dumps(request.to_dict()))
    rebuilt = ResolutionRequest.from_dict(round_tripped)
    assert rebuilt == request
