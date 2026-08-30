"""Integration tests for the finding-to-resolution vertical slice (Phase 8).

These tests exercise the complete flow from a real DevFlow finding through the
resolution gates to a verified (or failed) outcome.  They complement the unit
tests in test_phase8_resolution.py by:

- Using the real devflow-report.json that exists on disk (not a synthetic
  fixture) to verify AC1: "A real existing DevFlow finding can be selected".
- Asserting the CLI dispatch path end-to-end (resolve → ingest-fix → validate).
- Asserting that the Bob handoff prompt carries the real evidence from the
  report, not re-derived or fabricated content.

Where the full CLI requires interactive stdin (the approval gates), tests use
the _build.py layer directly with explicit approved= parameters rather than
mocking stdin, which matches the pattern established in test_phase8_resolution.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
    find_finding,
    ingest_proposed_fix,
    run_validation,
)
from devflow.resolution._ingest import parse_proposed_fix, parse_resolution_summary
from devflow.resolution._prompt import build_bob_prompt
from devflow.resolution._sessions import load_request, session_dir

# ---------------------------------------------------------------------------
# Paths to real project artifacts
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_REPORT_PATH = _REPO_ROOT / "frontend" / "public" / "devflow-report.json"

# The risk finding that appears in every real analysis of the flask repository.
_REAL_RISK_FINDING_ID = "risk:0:code"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_real_report() -> dict:
    """Load the actual devflow-report.json from the frontend/public directory."""
    return json.loads(_REAL_REPORT_PATH.read_text(encoding="utf-8"))


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "placeholder.py").write_text("# placeholder\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)


# ---------------------------------------------------------------------------
# Fixture: well-formed Bob output fixtures (same format as resolver mode output)
# ---------------------------------------------------------------------------

_WELL_FORMED_FIX = """\
### Finding

HIGH code risk — src/flask/ctx.py

### Root Cause

src/flask/ctx.py is referenced by 21 files through static import edges. Any
behavioral change propagates without containment. No direct test exercises the
refactored context-push path.

### Proposed Change

Add a focused regression test for the context-push/pop path in
tests/test_reqctx.py so that future regressions in ctx.py are caught
immediately rather than discovered by callers.

### Files to Modify

- tests/test_reqctx.py

### Tests

- tests/test_reqctx.py::test_nested_context_push_restore

### Validation

Run `pytest tests/test_reqctx.py -k test_nested_context_push_restore`.
"""

_WELL_FORMED_RESOLUTION_RESOLVED = """\
## Resolution Summary

Added tests/test_reqctx.py::test_nested_context_push_restore to cover the
refactored context-push/pop path.

## Files Changed

- tests/test_reqctx.py

## Tests Added / Updated

- tests/test_reqctx.py::test_nested_context_push_restore

## Tests Executed

pytest tests/test_reqctx.py::test_nested_context_push_restore -> 1 passed

## Validation

All assertions pass.

## Remaining Risks

- Broader regression suite not yet run.

## Final Status

RESOLVED
"""


# ---------------------------------------------------------------------------
# AC1: A real existing DevFlow finding can be selected
# ---------------------------------------------------------------------------


def test_real_report_exists_on_disk():
    """The real devflow-report.json must exist and contain findings."""
    assert _REAL_REPORT_PATH.is_file(), (
        f"devflow-report.json not found at {_REAL_REPORT_PATH}. "
        "Run `devflow analyze` to generate it."
    )
    report = _load_real_report()
    findings = report.get("findings") or []
    assert len(findings) > 0, "The real report must contain at least one finding."


def test_real_finding_can_be_looked_up_by_id():
    """find_finding() must return the actual finding from the real report."""
    pytest.importorskip("devflow.resolution._build")  # ensure module is importable
    report = _load_real_report()
    finding = find_finding(report, _REAL_RISK_FINDING_ID)
    assert finding["id"] == _REAL_RISK_FINDING_ID
    assert finding["category"] == "risk"
    # The real report carries evidence from Phase 2 and Phase 4 ingestion.
    assert len(finding.get("evidence") or []) > 0, (
        "The real finding must carry at least one evidence item."
    )


def test_resolution_request_created_from_real_finding(tmp_path):
    """A ResolutionRequest built from the real report must contain the actual
    finding evidence, not fabricated content."""
    report = _load_real_report()
    request = create_resolution_request(
        report,
        _REAL_RISK_FINDING_ID,
        bob_sessions_dir=tmp_path / "sessions",
    )
    assert request.id.startswith("res_")
    assert request.finding_id == _REAL_RISK_FINDING_ID
    assert request.status == ResolutionStatus.REQUESTED

    # Repository context from the real report
    assert request.repository_url == report["repository_url"]
    assert request.owner == report["owner"]
    assert request.name == report["name"]
    assert request.change_summary == report["change_summary"]

    # Evidence is verbatim from the report -- not re-derived
    snap = request.finding_snapshot
    real_finding = find_finding(report, _REAL_RISK_FINDING_ID)
    assert snap["evidence"] == real_finding["evidence"]
    assert snap["affected_artifacts"] == real_finding["affected_artifacts"]
    assert snap["severity"] == real_finding["severity"]


def test_resolution_request_persisted_to_session_directory(tmp_path):
    """Creating a request must immediately write request.json and state.json."""
    report = _load_real_report()
    sessions_dir = tmp_path / "sessions"
    request = create_resolution_request(
        report,
        _REAL_RISK_FINDING_ID,
        bob_sessions_dir=sessions_dir,
    )
    sdir = session_dir(request.id, bob_sessions_dir=sessions_dir)
    assert (sdir / "request.json").is_file()
    assert (sdir / "state.json").is_file()

    state = json.loads((sdir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "requested"
    assert state["finding_id"] == _REAL_RISK_FINDING_ID


# ---------------------------------------------------------------------------
# AC2: Gate 1 blocks progression without explicit approval
# ---------------------------------------------------------------------------


def test_gate1_rejection_persists_and_blocks_ingest(tmp_path):
    """Rejecting Gate 1 must persist the decision and prevent fix ingestion."""
    report = _load_real_report()
    sessions_dir = tmp_path / "sessions"
    request = create_resolution_request(
        report, _REAL_RISK_FINDING_ID, bob_sessions_dir=sessions_dir
    )
    request = decide_investigation_gate(
        request, approved=False, decided_by="dev", bob_sessions_dir=sessions_dir
    )
    assert request.status == ResolutionStatus.REJECTED_BEFORE_INVESTIGATION
    assert request.investigate_gate.decision.value == "rejected"

    # State must be persisted so a re-load shows the rejection
    reloaded = load_request(request.id, bob_sessions_dir=sessions_dir)
    assert reloaded.status == ResolutionStatus.REJECTED_BEFORE_INVESTIGATION

    # Fix ingestion must be blocked
    fake_fix = tmp_path / "fix.md"
    fake_fix.write_text(_WELL_FORMED_FIX, encoding="utf-8")
    with pytest.raises(ValueError, match="investigation gate"):
        ingest_proposed_fix(request, fake_fix, bob_sessions_dir=sessions_dir)


def test_gate1_approval_writes_bob_prompt(tmp_path):
    """Approving Gate 1 must write a bob_prompt.md containing the actual
    finding evidence so the developer can hand it to Bob."""
    report = _load_real_report()
    sessions_dir = tmp_path / "sessions"
    request = create_resolution_request(
        report, _REAL_RISK_FINDING_ID, bob_sessions_dir=sessions_dir
    )
    request = decide_investigation_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=sessions_dir
    )
    sdir = session_dir(request.id, bob_sessions_dir=sessions_dir)
    prompt_path = sdir / "bob_prompt.md"
    assert prompt_path.is_file(), "bob_prompt.md must be written on gate 1 approval"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    # Must contain the real repository URL and finding
    assert report["repository_url"] in prompt_text
    assert _REAL_RISK_FINDING_ID in prompt_text
    assert request.id in prompt_text


# ---------------------------------------------------------------------------
# AC3: Bob handoff contains actual finding evidence
# ---------------------------------------------------------------------------


def test_bob_prompt_carries_real_evidence_from_report(tmp_path):
    """build_bob_prompt must carry the evidence DevFlow already gathered --
    no re-derivation, no fabrication."""
    report = _load_real_report()
    real_finding = find_finding(report, _REAL_RISK_FINDING_ID)
    sessions_dir = tmp_path / "sessions"
    request = create_resolution_request(
        report, _REAL_RISK_FINDING_ID, bob_sessions_dir=sessions_dir
    )
    prompt = build_bob_prompt(request)

    # Repository identity
    assert report["repository_url"] in prompt
    assert report["change_summary"] in prompt

    # Evidence items from the real finding must appear in the prompt
    for item in real_finding.get("evidence") or []:
        evidence_type = item.get("evidence_type", "")
        assert evidence_type in prompt, (
            f"Evidence type {evidence_type!r} from the real finding must appear in the handoff prompt."
        )

    # Affected artifacts from the real finding
    for artifact in real_finding.get("affected_artifacts") or []:
        assert artifact in prompt, (
            f"Affected artifact {artifact!r} must appear in the handoff prompt."
        )

    # Human-approval boundary must be explicit
    assert "Do not modify any file yet" in prompt
    assert "DevFlow requires explicit human approval" in prompt

    # Follow-up command uses the real resolution id
    assert f"devflow apply {request.id}" in prompt


def test_inference_findings_flagged_in_bob_prompt(tmp_path):
    """If the real risk finding is marked is_inference=True the prompt must
    warn Bob it is not an established defect."""
    report = _load_real_report()
    real_finding = find_finding(report, _REAL_RISK_FINDING_ID)
    if not real_finding.get("is_inference"):
        pytest.skip("real risk:0:code is not marked is_inference; skipping inference-flag check")
    sessions_dir = tmp_path / "sessions"
    request = create_resolution_request(
        report, _REAL_RISK_FINDING_ID, bob_sessions_dir=sessions_dir
    )
    prompt = build_bob_prompt(request)
    assert "INFERENCE" in prompt
    assert "not an established defect" in prompt


# ---------------------------------------------------------------------------
# AC4: Malformed Bob output is rejected loudly
# ---------------------------------------------------------------------------


def test_missing_required_sections_raise_ingest_error():
    """parse_proposed_fix must raise ResolutionIngestError -- never silently
    return a partial ProposedFix -- when required sections are absent."""
    malformed_cases = [
        # Missing Files to Modify
        "### Proposed Change\nSome change.\n\n### Tests\n- t.py::f\n\n### Validation\npytest\n",
        # Missing Tests
        "### Proposed Change\nSome change.\n\n### Files to Modify\n- f.py\n\n### Validation\npytest\n",
        # Missing Validation
        "### Proposed Change\nSome change.\n\n### Files to Modify\n- f.py\n\n### Tests\n- t.py::f\n",
        # Completely empty
        "",
        # Prose only, no headings
        "This is just prose without any markdown headings at all.",
    ]
    for malformed in malformed_cases:
        with pytest.raises(ResolutionIngestError):
            parse_proposed_fix(malformed, raw_bob_output_path="fake.md")


def test_unrecognized_final_status_raises_ingest_error():
    """parse_resolution_summary must raise ResolutionIngestError for any
    final status value not in the fixed vocabulary."""
    bad_text = (
        "## Resolution Summary\n\nDid something.\n\n"
        "## Final Status\n\nSORTA FIXED\n"
    )
    with pytest.raises(ResolutionIngestError):
        parse_resolution_summary(bad_text)


def test_missing_final_status_section_raises_ingest_error():
    """parse_resolution_summary must raise when Final Status section is absent."""
    no_status = "## Resolution Summary\n\nDid something.\n"
    with pytest.raises(ResolutionIngestError):
        parse_resolution_summary(no_status)


# ---------------------------------------------------------------------------
# AC5: Gate 2 blocks application without explicit approval
# ---------------------------------------------------------------------------


def _walk_to_fix_proposed(tmp_path: Path) -> tuple[ResolutionRequest, Path]:
    """Helper: get a request to FIX_PROPOSED using the real report."""
    report = _load_real_report()
    sessions_dir = tmp_path / "sessions"
    request = create_resolution_request(
        report, _REAL_RISK_FINDING_ID, bob_sessions_dir=sessions_dir
    )
    request = decide_investigation_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=sessions_dir
    )
    fix_file = tmp_path / "fix.md"
    fix_file.write_text(_WELL_FORMED_FIX, encoding="utf-8")
    request = ingest_proposed_fix(request, fix_file, bob_sessions_dir=sessions_dir)
    assert request.status == ResolutionStatus.FIX_PROPOSED
    return request, sessions_dir


def test_gate2_rejection_persists_and_blocks_validation(tmp_path):
    """Rejecting Gate 2 must persist the decision and prevent validation."""
    request, sessions_dir = _walk_to_fix_proposed(tmp_path)
    request = decide_apply_gate(
        request, approved=False, decided_by="dev", bob_sessions_dir=sessions_dir
    )
    assert request.status == ResolutionStatus.REJECTED_BEFORE_APPLY

    reloaded = load_request(request.id, bob_sessions_dir=sessions_dir)
    assert reloaded.status == ResolutionStatus.REJECTED_BEFORE_APPLY

    result_file = tmp_path / "result.md"
    result_file.write_text(_WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")
    with pytest.raises(ValueError, match="apply-fix gate"):
        run_validation(
            request,
            local_path=tmp_path,
            raw_result_output_path=result_file,
            test_command="true",
            bob_sessions_dir=sessions_dir,
        )


def test_gate2_approval_required_even_after_fix_proposed(tmp_path):
    """Gate 2 must not be skippable: running validation directly on a
    FIX_PROPOSED request (without decide_apply_gate) raises ValueError."""
    request, sessions_dir = _walk_to_fix_proposed(tmp_path)
    # Status is FIX_PROPOSED, not FIX_APPROVED -- validation must be blocked.
    result_file = tmp_path / "result.md"
    result_file.write_text(_WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")
    with pytest.raises(ValueError, match="apply-fix gate"):
        run_validation(
            request,
            local_path=tmp_path,
            raw_result_output_path=result_file,
            test_command="true",
            bob_sessions_dir=sessions_dir,
        )


# ---------------------------------------------------------------------------
# AC7 + AC8: Real validation captures subprocess + real git diff
# ---------------------------------------------------------------------------


def _walk_to_fix_approved(tmp_path: Path) -> tuple[ResolutionRequest, Path]:
    request, sessions_dir = _walk_to_fix_proposed(tmp_path)
    request = decide_apply_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=sessions_dir
    )
    assert request.status == ResolutionStatus.FIX_APPROVED
    return request, sessions_dir


def test_validation_runs_real_subprocess_and_captures_output(tmp_path):
    """run_validation must execute the exact command given and capture stdout,
    stderr, and exit_code -- never simulated."""
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    request, sessions_dir = _walk_to_fix_approved(tmp_path)

    result_file = tmp_path / "result.md"
    result_file.write_text(_WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")

    # Command that writes a distinct sentinel to stdout
    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="echo integration-sentinel",
        bob_sessions_dir=sessions_dir,
    )

    record = request.outcome.tests_executed[0]
    assert record.command == "echo integration-sentinel"
    assert record.exit_code == 0
    assert record.passed is True
    assert "integration-sentinel" in record.stdout
    assert isinstance(record.stderr, str)
    assert "integration-sentinel" in record.output_excerpt


def test_modified_files_reflect_real_git_diff_not_bob_claim(tmp_path):
    """modified_files must come from `git diff --name-only`, not from Bob's
    own 'Files Changed' section."""
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    # Create a real, uncommitted change in a file Bob's output does NOT mention
    (repo_dir / "placeholder.py").write_text("CHANGED = True\n", encoding="utf-8")

    request, sessions_dir = _walk_to_fix_approved(tmp_path)
    result_file = tmp_path / "result.md"
    result_file.write_text(_WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")

    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="true",
        bob_sessions_dir=sessions_dir,
    )

    # real git diff shows placeholder.py; Bob's output mentions tests/test_reqctx.py
    assert "placeholder.py" in request.outcome.modified_files
    assert "tests/test_reqctx.py" not in request.outcome.modified_files


# ---------------------------------------------------------------------------
# AC9 + AC10: Final status from evidence, not Bob's claim
# ---------------------------------------------------------------------------


def test_failing_tests_override_bob_resolved_claim(tmp_path):
    """When Bob claims RESOLVED but the real test command exits non-zero,
    final_status must be VALIDATION_FAILED, never RESOLVED."""
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    request, sessions_dir = _walk_to_fix_approved(tmp_path)

    result_file = tmp_path / "result.md"
    # Bob's output claims RESOLVED
    result_file.write_text(_WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")

    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="false",  # guaranteed failure
        bob_sessions_dir=sessions_dir,
    )

    assert request.outcome.tests_executed[0].passed is False
    assert request.outcome.final_status == FinalStatus.VALIDATION_FAILED, (
        "Bob's RESOLVED claim must be overridden by a real failing test run"
    )
    assert request.outcome.bob_claimed_status == FinalStatus.RESOLVED, (
        "Bob's claimed status must be preserved alongside DevFlow's verdict"
    )
    assert request.outcome.contradicted_bob is True


def test_passing_tests_with_resolved_claim_produces_resolved_outcome(tmp_path):
    """When tests pass and Bob claims RESOLVED, final_status is RESOLVED."""
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    request, sessions_dir = _walk_to_fix_approved(tmp_path)

    result_file = tmp_path / "result.md"
    result_file.write_text(_WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")

    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="true",
        bob_sessions_dir=sessions_dir,
    )

    assert request.status == ResolutionStatus.VALIDATED
    assert request.outcome.final_status == FinalStatus.RESOLVED
    assert request.outcome.contradicted_bob is False


def test_unresolved_finding_not_counted_as_resolved_in_status(tmp_path):
    """A VALIDATION_FAILED or NOT_RESOLVED outcome must not appear in the
    resolved set when devflow.status reads the sessions directory."""
    from devflow.status import build_status, load_sessions

    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    sessions_dir = tmp_path / "sessions"

    report = _load_real_report()
    request = create_resolution_request(
        report, _REAL_RISK_FINDING_ID, bob_sessions_dir=sessions_dir
    )
    request = decide_investigation_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=sessions_dir
    )
    fix_file = tmp_path / "fix.md"
    fix_file.write_text(_WELL_FORMED_FIX, encoding="utf-8")
    request = ingest_proposed_fix(request, fix_file, bob_sessions_dir=sessions_dir)
    request = decide_apply_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=sessions_dir
    )

    result_file = tmp_path / "result.md"
    result_file.write_text(_WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")

    # Run with a failing command: Bob says RESOLVED but tests fail
    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="false",
        bob_sessions_dir=sessions_dir,
    )
    assert request.outcome.final_status == FinalStatus.VALIDATION_FAILED

    # devflow status must not count this as resolved
    sessions = load_sessions(sessions_dir)
    resolved_ids = {
        str(s.get("finding_id"))
        for s in sessions
        if str((s.get("outcome") or {}).get("final_status") or "").lower()
        in ("resolved", "validated")
    }
    assert _REAL_RISK_FINDING_ID not in resolved_ids, (
        "A VALIDATION_FAILED finding must not appear in the resolved set"
    )


# ---------------------------------------------------------------------------
# Session persistence across invocations (round-trip)
# ---------------------------------------------------------------------------


def test_state_persisted_at_every_transition_and_reloadable(tmp_path):
    """Every state transition must write state.json so a new process can
    resume from the last persisted state."""
    repo_dir = tmp_path / "checkout"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)
    sessions_dir = tmp_path / "sessions"

    report = _load_real_report()
    request = create_resolution_request(
        report, _REAL_RISK_FINDING_ID, bob_sessions_dir=sessions_dir
    )
    resolution_id = request.id

    # Gate 1
    request = decide_investigation_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=sessions_dir
    )
    r1 = load_request(resolution_id, bob_sessions_dir=sessions_dir)
    assert r1.status == ResolutionStatus.INVESTIGATION_APPROVED

    # Ingest fix
    fix_file = tmp_path / "fix.md"
    fix_file.write_text(_WELL_FORMED_FIX, encoding="utf-8")
    request = ingest_proposed_fix(request, fix_file, bob_sessions_dir=sessions_dir)
    r2 = load_request(resolution_id, bob_sessions_dir=sessions_dir)
    assert r2.status == ResolutionStatus.FIX_PROPOSED
    assert r2.proposed_fix is not None

    # Gate 2
    request = decide_apply_gate(
        request, approved=True, decided_by="dev", bob_sessions_dir=sessions_dir
    )
    r3 = load_request(resolution_id, bob_sessions_dir=sessions_dir)
    assert r3.status == ResolutionStatus.FIX_APPROVED

    # Validation
    result_file = tmp_path / "result.md"
    result_file.write_text(_WELL_FORMED_RESOLUTION_RESOLVED, encoding="utf-8")
    request = run_validation(
        request,
        local_path=repo_dir,
        raw_result_output_path=result_file,
        test_command="true",
        bob_sessions_dir=sessions_dir,
    )
    r4 = load_request(resolution_id, bob_sessions_dir=sessions_dir)
    assert r4.status == ResolutionStatus.VALIDATED
    assert r4.outcome.final_status == FinalStatus.RESOLVED

    # All expected files must be present
    sdir = session_dir(resolution_id, bob_sessions_dir=sessions_dir)
    for fname in (
        "request.json",
        "state.json",
        "bob_prompt.md",
        "bob_investigation.md",
        "bob_result.md",
        "test_run.txt",
    ):
        assert (sdir / fname).is_file(), f"{fname} must be written by the end of the workflow"
