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

from devflow.resolution._build import (
    create_resolution_request,
    decide_apply_gate,
    decide_investigation_gate,
    ingest_proposed_fix,
    run_validation,
)
from devflow.resolution._sessions import load_request, session_dir


def _print_finding(finding: dict) -> None:
    print(f"Finding: {finding.get('id')}")
    print(f"  Title:       {finding.get('title')}")
    print(f"  Category:    {finding.get('category')}")
    print(f"  Severity:    {finding.get('severity')}")
    print(f"  Description: {finding.get('description')}")
    if finding.get("is_inference"):
        print("  WARNING: this finding is INFERENCE-level, not confirmed by direct evidence.")
    evidence = finding.get("evidence") or []
    if evidence:
        print("  Evidence:")
        for item in evidence:
            print(f"    - [{item.get('evidence_type')}] {item.get('description')}")


def _confirm(prompt: str) -> bool:
    answer = input(f"{prompt} (yes/no): ").strip().lower()
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

    print()
    print(f"Resolution id: {request.id}")
    print(f"Status: {request.status.value}")
    if not approved:
        print("Investigation rejected. Stopping here.")
        return 0

    prompt_path = session_dir(request.id) / "bob_prompt.md"
    print()
    print("DevFlow prepared Bob's investigation prompt from this finding's evidence:")
    print(f"  {prompt_path}")
    print()
    print("Next step:")
    print("  1. Open Bob IDE and switch to the `resolver` custom mode.")
    print("  2. Paste the prompt above. It asks Bob to investigate in parallel")
    print("     using the four DevFlow skills, and to propose without editing.")
    print('  3. Save Bob\'s "Propose the Fix" output to a file.')
    print(f"  4. Run: devflow apply {request.id} <path-to-bob-output.md>")
    return 0


def _cmd_ingest_fix(args: argparse.Namespace) -> int:
    request = load_request(args.resolution_id)
    request = ingest_proposed_fix(request, args.bob_output_path)

    fix = request.proposed_fix
    print("Proposed fix:")
    print(f"  Summary:     {fix.summary}")
    print(f"  Root cause:  {fix.root_cause}")
    print(f"  Files:       {', '.join(fix.files_to_modify) or '(none listed)'}")
    print(f"  Tests:       {', '.join(fix.tests_to_add_or_update) or '(none listed)'}")
    print(f"  Validation:  {fix.validation_plan}")

    approved = _confirm("Apply this fix and run tests?")
    request = decide_apply_gate(request, approved=approved, decided_by=getpass.getuser())

    print()
    print(f"Status: {request.status.value}")
    if not approved:
        print("Fix rejected. Stopping here.")
        return 0

    print()
    print("Next step:")
    print("  1. Let Bob implement the fix in your local checkout.")
    print('  2. Save Bob\'s closing "Resolution Summary ... Final Status" output to a file.')
    print(
        f"  3. Run: python -m devflow.resolution validate {request.id} "
        "--local-path <checkout> --result <bob-result.md> --test-command \"<command>\""
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
    print(f"Resolution recorded as {outcome.final_status.value}.")
    print(f"  Modified files:  {', '.join(outcome.modified_files) or '(none detected)'}")
    print(
        f"  Tests executed:  {outcome.tests_executed[0].command} "
        f"(passed={outcome.tests_executed[0].passed}, exit_code={outcome.tests_executed[0].exit_code})"
    )
    if outcome.remaining_risks:
        print(f"  Remaining risks: {', '.join(outcome.remaining_risks)}")
    print()
    print(
        "The Change Impact Map and Developer Report reflect the pre-fix analysis; "
        "re-run `python -m devflow <url> <change>` to refresh them against the "
        "current repository state."
    )
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
        print(f"Error: {exc}", file=sys.stderr)
        return 1
