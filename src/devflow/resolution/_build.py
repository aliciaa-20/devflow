"""DevFlow Phase 8 -- Bob Resolution.

The smallest reliable vertical slice: a developer selects one approved
Developer Report finding, DevFlow gates the workflow behind two explicit
human-approval decisions, and a developer runs Bob's `resolver` custom mode
themselves (outside this codebase -- there is no programmatic Bob SDK here)
against their own local checkout. DevFlow's job is the two gates,
deterministic ingestion of Bob's structured markdown output, and running the
one thing it can verify for real: the actual test command and a real
`git diff`, rather than trusting a claimed outcome.

See docs / the Phase 8 plan for the full design and its explicit scope
boundary (no batch resolution, no automatic Phase 4-7 re-run, no HTTP
endpoints, no programmatic Bob invocation -- all deferred).
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Patterns that pytest and unittest emit at the end of a run.  These are
# "best effort" -- if the output doesn't match we leave the counts as -1
# rather than inventing numbers.
_PYTEST_SUMMARY_RE = re.compile(
    r"=+\s+(?:(\d+) passed)?(?:,?\s*(\d+) failed)?(?:,?\s*(\d+) error)?.*=+$",
    re.MULTILINE,
)
_UNITTEST_SUMMARY_RE = re.compile(r"^Ran (\d+) tests? in", re.MULTILINE)

from devflow.models.resolution import (
    ApprovalDecision,
    ApprovalGate,
    FinalStatus,
    ResolutionOutcome,
    ResolutionRequest,
    ResolutionStatus,
    TestExecutionRecord,
)
from devflow.resolution._ingest import parse_proposed_fix, parse_resolution_summary
from devflow.resolution._prompt import build_bob_prompt
from devflow.resolution._sessions import write_raw_text, write_request_snapshot, write_state, session_dir

import time


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "finding"


def _new_resolution_id(finding_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"res_{timestamp}_{_slugify(finding_id)}"


def find_finding(report_payload: dict[str, Any], finding_id: str) -> dict[str, Any]:
    """Look up one finding by id in an on-disk devflow-report.json payload."""
    for finding in report_payload.get("findings", []):
        if finding.get("id") == finding_id:
            return finding
    raise ValueError(f"No finding with id {finding_id!r} found in the report.")


def create_resolution_request(
    report_payload: dict[str, Any],
    finding_id: str,
    *,
    bob_sessions_dir: Optional[str | Path] = None,
) -> ResolutionRequest:
    """Start a resolution session for one approved Developer Report finding.

    finding_snapshot is the finding's verbatim dict from the report, preserving
    its evidence exactly as Phases 4/5/7 produced it -- nothing is re-derived
    or re-classified here.
    """
    finding = find_finding(report_payload, finding_id)
    request = ResolutionRequest(
        id=_new_resolution_id(finding_id),
        repository_url=report_payload.get("repository_url", ""),
        owner=report_payload.get("owner", ""),
        name=report_payload.get("name", ""),
        change_summary=report_payload.get("change_summary", ""),
        finding_id=finding_id,
        finding_snapshot=finding,
        graph_node_id=finding.get("graph_node_id"),
    )
    write_request_snapshot(request, bob_sessions_dir=bob_sessions_dir)
    write_state(request, bob_sessions_dir=bob_sessions_dir)
    return request


def decide_investigation_gate(
    request: ResolutionRequest,
    *,
    approved: bool,
    decided_by: str,
    note: Optional[str] = None,
    bob_sessions_dir: Optional[str | Path] = None,
) -> ResolutionRequest:
    """Gate 1: approve or reject Bob investigating this finding."""
    if request.status != ResolutionStatus.REQUESTED:
        raise ValueError(
            f"Cannot decide the investigation gate from status {request.status.value!r}."
        )
    decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.REJECTED
    request.investigate_gate = ApprovalGate(
        gate="investigate", decision=decision, decided_by=decided_by, note=note
    )
    request.status = (
        ResolutionStatus.INVESTIGATION_APPROVED
        if approved
        else ResolutionStatus.REJECTED_BEFORE_INVESTIGATION
    )
    write_state(request, bob_sessions_dir=bob_sessions_dir)
    if approved:
        # Hand Bob the context DevFlow already gathered, rather than making the
        # developer restate the finding by hand. Preserved in the session
        # directory so the submitted evidence shows exactly what Bob was asked.
        write_raw_text(
            request.id,
            "bob_prompt.md",
            build_bob_prompt(request),
            bob_sessions_dir=bob_sessions_dir,
        )
    return request


def ingest_proposed_fix(
    request: ResolutionRequest,
    raw_output_path: str | Path,
    *,
    bob_sessions_dir: Optional[str | Path] = None,
) -> ResolutionRequest:
    """Ingest the developer-saved copy of Bob's "Propose the Fix" output.

    Only callable once the investigation gate has been approved. The raw text
    is preserved verbatim in bob_sessions/ before it's parsed, so the original
    Bob output is always recoverable even if parsing fails.
    """
    if request.status != ResolutionStatus.INVESTIGATION_APPROVED:
        raise ValueError(
            f"Cannot ingest a proposed fix from status {request.status.value!r}; "
            "the investigation gate must be approved first."
        )
    raw_text = Path(raw_output_path).read_text(encoding="utf-8")
    saved_path = write_raw_text(
        request.id, "bob_investigation.md", raw_text, bob_sessions_dir=bob_sessions_dir
    )
    request.proposed_fix = parse_proposed_fix(raw_text, raw_bob_output_path=str(saved_path))
    request.status = ResolutionStatus.FIX_PROPOSED
    write_state(request, bob_sessions_dir=bob_sessions_dir)
    return request


def decide_apply_gate(
    request: ResolutionRequest,
    *,
    approved: bool,
    decided_by: str,
    note: Optional[str] = None,
    bob_sessions_dir: Optional[str | Path] = None,
) -> ResolutionRequest:
    """Gate 2: approve or reject applying the proposed fix."""
    if request.status != ResolutionStatus.FIX_PROPOSED:
        raise ValueError(
            f"Cannot decide the apply-fix gate from status {request.status.value!r}; "
            "a fix must be proposed first."
        )
    decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.REJECTED
    request.apply_gate = ApprovalGate(
        gate="apply_fix", decision=decision, decided_by=decided_by, note=note
    )
    request.status = (
        ResolutionStatus.FIX_APPROVED if approved else ResolutionStatus.REJECTED_BEFORE_APPLY
    )
    write_state(request, bob_sessions_dir=bob_sessions_dir)
    return request


def _git_modified_files(local_path: str | Path) -> tuple[str, ...]:
    """Real modified-file list from git, independent of what Bob claimed."""
    try:
        result = subprocess.run(
            ["git", "-C", str(local_path), "diff", "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def _parse_test_counts(combined: str) -> tuple[int, int]:
    """Return (test_count, failure_count) parsed from test-runner summary output.

    Returns (-1, -1) when no recognisable summary line is found -- the caller
    must treat these as "not determinable", not as zero.
    """
    m = _PYTEST_SUMMARY_RE.search(combined)
    if m:
        passed_str, failed_str, error_str = m.group(1), m.group(2), m.group(3)
        failures = (int(failed_str) if failed_str else 0) + (int(error_str) if error_str else 0)
        passed = int(passed_str) if passed_str else 0
        return passed + failures, failures

    m2 = _UNITTEST_SUMMARY_RE.search(combined)
    if m2:
        total = int(m2.group(1))
        # unittest says "OK" or "FAILED" on the last line
        failed = 0 if combined.rstrip().endswith("OK") else -1
        return total, failed

    return -1, -1


def _run_test_command(command: str, *, cwd: str | Path) -> tuple[TestExecutionRecord, str]:
    """Actually execute the developer-approved test command -- never simulated."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=600,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        combined_output = stdout + stderr
        test_count, failure_count = _parse_test_counts(combined_output)
        record = TestExecutionRecord(
            command=command,
            passed=result.returncode == 0,
            exit_code=result.returncode,
            output_excerpt=combined_output[-4000:],
            stdout=stdout,
            stderr=stderr,
            test_count=test_count,
            failure_count=failure_count,
        )
        return record, combined_output
    except subprocess.TimeoutExpired as exc:
        combined_output = f"Command timed out after {exc.timeout}s."
        record = TestExecutionRecord(
            command=command,
            passed=False,
            exit_code=-1,
            output_excerpt=combined_output,
            stdout="",
            stderr=combined_output,
            test_count=-1,
            failure_count=-1,
        )
        return record, combined_output


def run_validation(
    request: ResolutionRequest,
    *,
    local_path: str | Path,
    raw_result_output_path: str | Path,
    test_command: str,
    bob_sessions_dir: Optional[str | Path] = None,
) -> ResolutionRequest:
    """Apply-and-validate step: run the real test command and diff, then
    reconcile against what Bob's closing report claims.

    Only callable once the apply-fix gate has been approved (the developer is
    expected to have already let Bob implement the fix in `local_path` before
    calling this). If Bob's raw output claims RESOLVED or PARTIALLY_RESOLVED
    but the actually-executed test command fails, the recorded final_status is
    downgraded to VALIDATION_FAILED -- an unverified success claim is never
    trusted over a real failing test run.
    """
    if request.status != ResolutionStatus.FIX_APPROVED:
        raise ValueError(
            f"Cannot run validation from status {request.status.value!r}; "
            "the apply-fix gate must be approved first."
        )

    raw_text = Path(raw_result_output_path).read_text(encoding="utf-8")
    saved_path = write_raw_text(
        request.id, "bob_result.md", raw_text, bob_sessions_dir=bob_sessions_dir
    )
    summary = parse_resolution_summary(raw_text)

    modified_files = _git_modified_files(local_path)
    test_record, full_output = _run_test_command(test_command, cwd=local_path)
    write_raw_text(request.id, "test_run.txt", full_output, bob_sessions_dir=bob_sessions_dir)

    claimed_status = summary["claimed_final_status"]
    final_status = claimed_status
    if not test_record.passed and final_status in (
        FinalStatus.RESOLVED,
        FinalStatus.PARTIALLY_RESOLVED,
    ):
        final_status = FinalStatus.VALIDATION_FAILED

    request.outcome = ResolutionOutcome(
        modified_files=modified_files,
        change_rationale=summary["change_rationale"],
        tests_added_or_updated=summary["tests_added_or_updated"],
        tests_executed=(test_record,),
        final_status=final_status,
        bob_claimed_status=claimed_status,
        remaining_risks=summary["remaining_risks"],
        raw_bob_output_path=str(saved_path),
    )
    request.status = ResolutionStatus.VALIDATED
    write_state(request, bob_sessions_dir=bob_sessions_dir)
    return request


def wait_for_bob_investigation(
    resolution_id: str,
    *,
    timeout_seconds: int = 600,
    bob_sessions_dir: Optional[str | Path] = None,
) -> str:
    """Poll for bob_investigation.md to appear in the session directory.

    Returns the raw text content when the file is detected.
    Raises TimeoutError if timeout is exceeded.
    """
    start_time = time.time()
    poll_interval = 2  # seconds

    session = session_dir(resolution_id, bob_sessions_dir=bob_sessions_dir)
    investigation_path = session / "bob_investigation.md"

    while time.time() - start_time < timeout_seconds:
        if investigation_path.is_file():
            return investigation_path.read_text(encoding="utf-8")
        time.sleep(poll_interval)

    elapsed = int(time.time() - start_time)
    raise TimeoutError(
        f"Waited {elapsed}s for Bob investigation output. "
        f"Save Bob's 'Propose the Fix' output to {investigation_path}"
    )
