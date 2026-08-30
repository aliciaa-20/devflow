"""CLI entry point for DevFlow Phase 8 (Bob Resolution).

Usage (three steps, run across separate invocations since Bob's investigation
and file edits happen outside this process, in the developer's own editor):

    python -m devflow.resolution request <finding_id> \\
        --report frontend/public/devflow-report.json

        Prints the finding and its evidence, then asks for explicit approval
        to investigate. On approval, prints the resolution id and instructs
        the developer to run Bob's `resolver` custom mode themselves and
        save its "Propose the Fix" output to a file.

    python -m devflow.resolution ingest-fix <resolution_id> <bob_output.md>

        Parses the saved Bob output, prints the proposed fix, then asks for
        explicit approval to apply it. On approval, instructs the developer
        to let Bob implement the fix against their local checkout and save
        Bob's closing "Resolution Summary" output to a file.

    python -m devflow.resolution validate <resolution_id> \\
        --local-path <path/to/checkout> --result <bob_result.md> \\
        --test-command "pytest tests/test_x.py"

        Runs the real test command and a real `git diff` against the local
        checkout, reconciles the result against what Bob's closing report
        claims, and records the final, DevFlow-verified outcome.

Every step is recorded under bob_sessions/<resolution_id>/.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from devflow.render import (
    check,
    command_hint,
    emit,
    evidence_mark,
    field,
    paint,
    section,
    severity_badge,
    status_badge,
    steps,
    title,
    wrap,
)
from devflow.resolution._build import (
    create_resolution_request,
    decide_apply_gate,
    decide_investigation_gate,
    ingest_proposed_fix,
    run_validation,
)
from devflow.resolution._sessions import load_request, session_dir


def _print_finding(finding: dict) -> None:
    emit(title(f"finding {finding.get('id')}", str(finding.get("title") or "")))
    print(field("category", str(finding.get("category") or "-")))
    print(field("severity", severity_badge(finding.get("severity"))))
    emit(wrap(str(finding.get("description") or ""), indent=2))
    if finding.get("is_inference"):
        print()
        print(paint("  ? interpretation-level: not confirmed by direct evidence.", "yellow"))
    evidence = finding.get("evidence") or []
    if evidence:
        emit(section("evidence"))
        for item in evidence:
            mark, label = evidence_mark(item.get("evidence_type"))
            print(f"  {mark}  {paint(label, 'grey')}")
            emit(wrap(str(item.get("description") or ""), indent=6))
    print()


def _confirm(prompt: str) -> bool:
    answer = input(f"{paint(prompt, 'bold')} (yes/no): ").strip().lower()
    return answer in ("yes", "y")


def _cmd_request(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))

    request = create_resolution_request(report_payload, args.finding_id)
    _print_finding(request.finding_snapshot)

    approved = _confirm("Approve Bob investigation for this finding?")
    request = decide_investigation_gate(
        request, approved=approved, decided_by=getpass.getuser()
    )

    emit(section("resolution"))
    print(field("id", paint(request.id, "cyan")))
    print(field("status", status_badge(request.status.value)))
    if not approved:
        print()
        print(paint("  Investigation rejected. Stopping here.", "yellow"))
        return 0

    prompt_path = session_dir(request.id) / "bob_prompt.md"
    emit(section("next"))
    emit(
        steps(
            [
                "Open Bob IDE and switch to the `resolver` custom mode.",
                "Paste in the investigation prompt below (path shown).",
                "It investigates in parallel and proposes a fix without editing.",
                'Save Bob\'s "Propose the Fix" output to a file.',
            ]
        )
    )
    print()
    print(field("prompt", str(prompt_path)))
    print()
    print(command_hint(f"devflow apply {request.id} <path-to-bob-output.md>"))
    return 0


def _cmd_ingest_fix(args: argparse.Namespace) -> int:
    request = load_request(args.resolution_id)
    request = ingest_proposed_fix(request, args.bob_output_path)

    fix = request.proposed_fix
    emit(title("proposed fix", fix.summary))
    print(field("root cause", fix.root_cause))
    print(field("files", ", ".join(fix.files_to_modify) or paint("(none listed)", "grey")))
    print(field("tests", ", ".join(fix.tests_to_add_or_update) or paint("(none listed)", "grey")))
    emit(wrap(f"validation plan: {fix.validation_plan}", indent=2))
    print()

    approved = _confirm("Apply this fix and run tests?")
    request = decide_apply_gate(request, approved=approved, decided_by=getpass.getuser())

    emit(section("resolution"))
    print(field("status", status_badge(request.status.value)))
    if not approved:
        print()
        print(paint("  Fix rejected. Stopping here.", "yellow"))
        return 0

    emit(section("next"))
    emit(
        steps(
            [
                "Let Bob implement the fix in your local checkout.",
                'Save Bob\'s closing "Resolution Summary ... Final Status" output to a file.',
            ]
        )
    )
    print()
    print(
        command_hint(
            f'devflow validate {request.id} --local-path <checkout> '
            '--result <bob-result.md> --test-command "<command>"'
        )
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    request = load_request(args.resolution_id)
    request = run_validation(
        request,
        local_path=args.local_path,
        raw_result_output_path=args.result,
        test_command=args.test_command,
    )

    outcome = request.outcome
    emit(title("devflow validate", request.id))
    print(field("result", status_badge(outcome.final_status.value)))
    print(
        field(
            "files changed",
            ", ".join(outcome.modified_files) or paint("(none detected)", "grey"),
        )
    )
    test_run = outcome.tests_executed[0]
    print(
        field(
            "tests executed",
            f"{check(test_run.passed)}  {paint(test_run.command, 'cyan')} "
            f"{paint(f'(exit {test_run.exit_code})', 'grey')}",
        )
    )
    if outcome.remaining_risks:
        print(field("remaining risks", ", ".join(outcome.remaining_risks)))
    print()
    emit(
        wrap(
            "The Change Impact Map and Developer Report reflect the pre-fix "
            "analysis; re-run `devflow analyze <repo-url> \"<change>\"` to refresh "
            "them against the current repository state.",
            indent=2,
        )
    )
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m devflow.resolution")
    subparsers = parser.add_subparsers(dest="command", required=True)

    request_parser = subparsers.add_parser("request", help="Start a resolution for one finding.")
    request_parser.add_argument("finding_id")
    request_parser.add_argument(
        "--report", default="frontend/public/devflow-report.json", help="Path to devflow-report.json"
    )
    request_parser.set_defaults(func=_cmd_request)

    ingest_parser = subparsers.add_parser(
        "ingest-fix", help="Ingest Bob's saved investigation output."
    )
    ingest_parser.add_argument("resolution_id")
    ingest_parser.add_argument("bob_output_path")
    ingest_parser.set_defaults(func=_cmd_ingest_fix)

    validate_parser = subparsers.add_parser(
        "validate", help="Run real validation against the applied fix."
    )
    validate_parser.add_argument("resolution_id")
    validate_parser.add_argument("--local-path", required=True)
    validate_parser.add_argument("--result", required=True, help="Path to Bob's saved closing output.")
    validate_parser.add_argument("--test-command", required=True)
    validate_parser.set_defaults(func=_cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(paint(f"Error: {exc}", "red"), file=sys.stderr)
        return 1
