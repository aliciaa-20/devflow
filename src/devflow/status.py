"""`devflow status` -- where the change stands, end to end.

Joins the Developer Report with every resolution session under bob_sessions/
to answer one question: what has been investigated, what has been fixed and
verified, and what is still open?

The verification column is deliberately blunt.  A resolution counts as verified
only when DevFlow itself executed the tests and they passed.  Bob's claimed
status is displayed next to that result, so a disagreement between what the
agent reported and what actually happened is visible rather than smoothed over.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from devflow.render import (
    check,
    field,
    heading,
    paint,
    rule,
    severity_badge,
    status_badge,
    wrap,
)

DEFAULT_SESSIONS_DIR = "bob_sessions"

# Terminal statuses that mean the workflow reached a verified conclusion.
_TERMINAL = {"validated", "rejected_before_investigation", "rejected_before_apply"}


def load_sessions(sessions_dir: str | Path = DEFAULT_SESSIONS_DIR) -> list[dict[str, Any]]:
    """Load every resolution session state, newest first."""
    root = Path(sessions_dir)
    if not root.is_dir():
        return []
    sessions: list[dict[str, Any]] = []
    for state_file in sorted(root.glob("*/state.json")):
        try:
            sessions.append(json.loads(state_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    sessions.sort(key=lambda s: str(s.get("created_at") or ""), reverse=True)
    return sessions


def _gate_line(label: str, gate: Optional[dict[str, Any]]) -> str:
    if not gate:
        return field(label, paint("pending", "grey"))
    decision = str(gate.get("decision") or "pending")
    who = gate.get("decided_by") or "unknown"
    when = str(gate.get("decided_at") or "")[:19].replace("T", " ")
    mark = paint("approved", "green") if decision == "approved" else paint(decision, "yellow")
    return field(label, f"{mark}  {paint(f'by {who} {when}', 'grey')}")


def _verification_lines(outcome: dict[str, Any]) -> list[str]:
    """Render what DevFlow actually observed, beside what Bob claimed."""
    lines: list[str] = []
    executed = outcome.get("tests_executed") or []
    for record in executed:
        passed = bool(record.get("passed"))
        command = paint(str(record.get("command") or ""), "cyan")
        exit_note = paint("(exit {})".format(record.get("exit_code")), "grey")
        lines.append(field("tests executed", f"{check(passed)}  {command} {exit_note}"))
    modified = outcome.get("modified_files") or []
    lines.append(
        field(
            "files changed",
            ", ".join(modified) if modified else paint("none detected by git diff", "grey"),
        )
    )
    claimed = outcome.get("bob_claimed_status")
    final = outcome.get("final_status")
    if claimed:
        agreement = str(claimed).lower() == str(final).lower()
        note = (
            paint("matches DevFlow's verified result", "grey")
            if agreement
            else paint("DISAGREES with DevFlow's verified result", "bright_red", "bold")
        )
        lines.append(field("bob claimed", f"{status_badge(claimed)}  {note}"))
    lines.append(field("devflow verified", status_badge(final)))
    remaining = outcome.get("remaining_risks") or []
    if remaining:
        lines.append(field("remaining risks", paint(str(len(remaining)), "yellow")))
        for item in remaining[:5]:
            lines.extend(wrap(f"- {item}", indent=6))
    return lines


def _risk_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in (report.get("findings") or []) if f.get("category") == "risk"]


def build_status(
    report: Optional[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> list[str]:
    out: list[str] = [""]

    if report is None:
        out.append(rule("devflow status"))
        out.append("")
        out.append(field("analysis", paint("none - run `devflow analyze` first", "yellow")))
        out.append("")
        return out

    out.append(rule("devflow status"))
    out.append("")
    out.append(field("repository", paint(str(report.get("repository_url") or "-"), "cyan")))
    out.append(field("change", str(report.get("change_summary") or "-")))
    out.append(field("analyzed at", str(report.get("generated_at") or "-")))

    prioritization = report.get("prioritization") or {}
    source = str(prioritization.get("source") or "deterministic")
    ranked_by = (
        paint("IBM watsonx.ai", "blue") + paint(f" ({prioritization.get('model_id')})", "grey")
        if source == "watsonx"
        else paint("deterministic ordering", "grey")
    )
    if prioritization.get("from_cache"):
        ranked_by += paint(" [cached]", "grey")
    out.append(field("prioritized by", ranked_by))
    discarded = prioritization.get("discarded_finding_ids") or []
    if discarded:
        out.append(
            field(
                "model ids discarded",
                paint(f"{len(discarded)} not present in DevFlow findings", "yellow"),
            )
        )
    out.append("")

    # -- findings ----------------------------------------------------------
    risks = _risk_findings(report)
    # A resolution settles the finding it was opened for -- never every finding
    # that happens to touch the same file. Matching on artifacts would report
    # untouched findings as resolved, which is a fabricated validation claim.
    resolved_finding_ids = {
        str(session.get("finding_id"))
        for session in sessions
        if str((session.get("outcome") or {}).get("final_status") or "").lower()
        in ("resolved", "validated")
    }
    # Sessions that ran but did not fully resolve are surfaced separately, so a
    # partial or failed attempt is never mistaken for an untouched finding.
    attempted_finding_ids = {
        str(session.get("finding_id"))
        for session in sessions
        if session.get("outcome")
    } - resolved_finding_ids

    out.append(heading("risk findings"))
    if not risks:
        out.append(field("none", paint("no risk findings in this analysis", "grey")))
    for finding in risks:
        finding_id = str(finding.get("id"))
        if finding_id in resolved_finding_ids:
            marker = paint("resolved", "green")
        elif finding_id in attempted_finding_ids:
            marker = paint("attempted, not resolved", "yellow")
        else:
            marker = paint("open", "yellow")
        out.append(
            f"  {severity_badge(finding.get('severity'))} "
            f"{finding_id:28} {marker}"
        )
    out.append("")

    counts = {"open": 0, "resolved": 0}
    for finding in risks:
        settled = str(finding.get("id")) in resolved_finding_ids
        counts["resolved" if settled else "open"] += 1
    out.append(
        field(
            "summary",
            f"{paint(str(counts['resolved']), 'green')} resolved  /  "
            f"{paint(str(counts['open']), 'yellow')} remaining",
        )
    )
    out.append("")

    # -- resolutions -------------------------------------------------------
    out.append(heading("resolution sessions"))
    if not sessions:
        out.append(
            field("none", paint("run `devflow resolve <finding-id>` to start one", "grey"))
        )
        out.append("")
        return out

    for session in sessions:
        out.append("")
        out.append(
            f"  {paint(str(session.get('id')), 'bold')}  "
            f"{status_badge(session.get('status'))}"
        )
        out.append(field("finding", str(session.get("finding_id") or "-")))
        out.append(_gate_line("gate 1 investigate", session.get("investigate_gate")))
        out.append(_gate_line("gate 2 apply", session.get("apply_gate")))

        proposed = session.get("proposed_fix") or {}
        if proposed.get("summary"):
            out.extend(wrap(f"proposal: {proposed['summary']}", indent=4))

        outcome = session.get("outcome")
        if outcome:
            out.extend(_verification_lines(outcome))
        elif str(session.get("status")) not in _TERMINAL:
            out.append(
                field("awaiting", paint(_next_action_for(session), "yellow"))
            )
    out.append("")
    return out


def _next_action_for(session: dict[str, Any]) -> str:
    status = str(session.get("status") or "")
    resolution_id = session.get("id")
    if status == "investigation_approved":
        return f"Bob's proposal -> devflow apply {resolution_id} <file>"
    if status == "fix_proposed":
        return f"approval -> devflow apply {resolution_id} <file>"
    if status == "apply_approved":
        return f"validation -> devflow validate {resolution_id} ..."
    return "next step"
