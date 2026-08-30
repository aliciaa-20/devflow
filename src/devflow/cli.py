"""DevFlow developer CLI.

Five commands covering the product journey:

    devflow analyze   <repo-url> "<change>"    change  -> understand
    devflow findings                           understand -> prioritize
    devflow resolve   <finding-id>             prioritize -> resolve   [GATE 1]
    devflow apply     <resolution-id> <file>   resolve -> implement    [GATE 2]
    devflow validate  <resolution-id> ...      implement -> verified

``python -m devflow`` continues to work exactly as before; this module is a
thin front end over the same entry points, not a reimplementation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

DEFAULT_REPORT_PATH = "frontend/public/devflow-report.json"
DEFAULT_REPO_GRAPH_PATH = "frontend/public/devflow-repo-graph.json"


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


def _cmd_analyze(args: argparse.Namespace) -> int:
    from devflow.__main__ import main as run_devflow

    argv = [args.repository_url, args.change]
    if not args.serve:
        # _analyze_repository writes the payloads; skip the blocking server.
        from devflow.__main__ import _analyze_repository
        from devflow.models.change import ChangeRequestError
        from devflow.models.repository import RepositoryInputError

        print(f"Analyzing {args.repository_url} ...")
        try:
            graph, report = _analyze_repository(args.repository_url, args.change)
        except (RepositoryInputError, ChangeRequestError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        prioritization = _prioritize_and_persist(report, no_watsonx=args.no_watsonx)
        print(f"Change Impact Map: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        print(f"Developer Report:  {len(report.findings)} findings")
        _print_prioritization_banner(prioritization)
        print()
        print("Next: devflow findings")
        return 0

    return run_devflow(argv)


def _prioritize_and_persist(report, *, no_watsonx: bool):
    """Rank the report's findings and rewrite the payload with the result."""
    from devflow.report import write_frontend_report_payload
    from devflow.watsonx import prioritize_findings
    from devflow.watsonx._client import WatsonxConfig

    payload = report.to_dict()
    if no_watsonx:
        config = WatsonxConfig(api_key="", project_id="")
        prioritization = prioritize_findings(payload, config=config, use_cache=False)
    else:
        prioritization = prioritize_findings(payload)
    write_frontend_report_payload(report, prioritization=prioritization)
    return prioritization


def _print_prioritization_banner(prioritization) -> None:
    from devflow.models.prioritization import PrioritizationSource

    if prioritization.source == PrioritizationSource.WATSONX:
        origin = "IBM watsonx.ai"
        if prioritization.from_cache:
            origin += " (cached response)"
        detail = f" [{prioritization.model_id}]" if prioritization.model_id else ""
        print(f"Prioritization:    {origin}{detail}")
        if prioritization.discarded_finding_ids:
            print(
                f"                   discarded {len(prioritization.discarded_finding_ids)} "
                "model finding id(s) not present in DevFlow's findings"
            )
    else:
        print("Prioritization:    deterministic")
        if prioritization.error:
            print(f"                   ({prioritization.error})")


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------


def _load_report(path: str) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.is_file():
        raise FileNotFoundError(
            f"No report at '{path}'. Run `devflow analyze <repo-url> \"<change>\"` first."
        )
    return json.loads(report_path.read_text(encoding="utf-8"))


def _cmd_findings(args: argparse.Namespace) -> int:
    payload = _load_report(args.report)
    findings = {str(f.get("id")): f for f in payload.get("findings") or []}
    if not findings:
        print("No findings in the current report.")
        return 0

    prioritization = payload.get("prioritization")
    if prioritization is None or args.refresh:
        from devflow.watsonx import prioritize_findings
        from devflow.watsonx._client import WatsonxConfig

        config = WatsonxConfig(api_key="", project_id="") if args.no_watsonx else None
        prioritization = prioritize_findings(
            payload, config=config, use_cache=not args.no_watsonx
        ).to_dict()

    rankings = prioritization.get("rankings") or []
    if args.json:
        print(json.dumps(prioritization, indent=2))
        return 0

    source = prioritization.get("source")
    label = "IBM watsonx.ai" if source == "watsonx" else "deterministic"
    if prioritization.get("from_cache"):
        label += " (cached)"
    print(f"Findings ranked by: {label}")
    if prioritization.get("error"):
        print(f"  note: {prioritization['error']}")
    discarded = prioritization.get("discarded_finding_ids") or []
    if discarded:
        print(f"  discarded {len(discarded)} model id(s) absent from DevFlow findings: "
              f"{', '.join(discarded)}")
    print()

    for entry in rankings[: args.top]:
        finding = findings.get(entry.get("finding_id"), {})
        severity = (entry.get("severity") or "unrated").upper()
        origin = "watsonx" if entry.get("source") == "watsonx" else "deterministic"
        print(f"#{entry.get('rank')}  [{severity:8}] {entry.get('finding_id')}")
        print(f"    {entry.get('title') or finding.get('title') or ''}")
        print(f"    why first ({origin}): {entry.get('rationale')}")
        artifacts = finding.get("affected_artifacts") or []
        if artifacts:
            print(f"    artifacts: {', '.join(artifacts[:4])}")
        evidence = finding.get("evidence") or []
        direct = [e for e in evidence if e.get("evidence_type") == "DIRECT_EVIDENCE"]
        if direct:
            print(f"    evidence:  {direct[0].get('description', '')[:160]}")
        print()

    if len(rankings) > args.top:
        print(f"({len(rankings) - args.top} more; use --top {len(rankings)} to see all)")
    print("Next: devflow resolve <finding-id>")
    return 0


# ---------------------------------------------------------------------------
# resolve / apply / validate  (delegate to the Phase 8 resolution CLI)
# ---------------------------------------------------------------------------


def _cmd_status(args: argparse.Namespace) -> int:
    from devflow.status import build_status, load_sessions

    try:
        report = _load_report(args.report)
    except FileNotFoundError:
        report = None
    for line in build_status(report, load_sessions(args.sessions_dir)):
        print(line)
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    from devflow.explain import explain_finding

    payload = _load_report(args.report)
    for line in explain_finding(
        payload, args.finding_id, repo_graph_path=args.repo_graph
    ):
        print(line)
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    from devflow.resolution.cli import main as resolution_main

    return resolution_main(["request", args.finding_id, "--report", args.report])


def _cmd_apply(args: argparse.Namespace) -> int:
    from devflow.resolution.cli import main as resolution_main

    return resolution_main(["ingest-fix", args.resolution_id, args.bob_output])


def _cmd_validate(args: argparse.Namespace) -> int:
    from devflow.resolution.cli import main as resolution_main

    return resolution_main(
        [
            "validate",
            args.resolution_id,
            "--local-path",
            args.local_path,
            "--result",
            args.result,
            "--test-command",
            args.test_command,
        ]
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devflow",
        description="From unfamiliar code to confident change.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze", help="Analyze a repository against a described change."
    )
    analyze.add_argument("repository_url")
    analyze.add_argument("change", help="Developer change description.")
    analyze.add_argument(
        "--serve", action="store_true", help="Open the interactive UI after analysis."
    )
    analyze.add_argument(
        "--no-watsonx",
        action="store_true",
        help="Force deterministic prioritization (skip IBM watsonx.ai).",
    )
    analyze.set_defaults(func=_cmd_analyze)

    findings = subparsers.add_parser("findings", help="Show findings in priority order.")
    findings.add_argument("--top", type=int, default=5, help="How many to show (default 5).")
    findings.add_argument("--json", action="store_true", help="Emit the raw ranking JSON.")
    findings.add_argument("--report", default=DEFAULT_REPORT_PATH)
    findings.add_argument(
        "--refresh", action="store_true", help="Re-rank instead of reusing the stored ranking."
    )
    findings.add_argument(
        "--no-watsonx", action="store_true", help="Force deterministic prioritization."
    )
    findings.set_defaults(func=_cmd_findings)

    status = subparsers.add_parser(
        "status", help="Where the change stands: findings, gates, verification."
    )
    status.add_argument("--report", default=DEFAULT_REPORT_PATH)
    status.add_argument("--sessions-dir", default="bob_sessions")
    status.set_defaults(func=_cmd_status)

    explain = subparsers.add_parser(
        "explain", help="Why one finding is risky: evidence, blast radius, history."
    )
    explain.add_argument("finding_id")
    explain.add_argument("--report", default=DEFAULT_REPORT_PATH)
    explain.add_argument(
        "--repo-graph",
        default=DEFAULT_REPO_GRAPH_PATH,
        help="Path to the Repository Knowledge Graph payload.",
    )
    explain.set_defaults(func=_cmd_explain)

    resolve = subparsers.add_parser(
        "resolve", help="Start a Bob resolution for one finding (human gate 1)."
    )
    resolve.add_argument("finding_id")
    resolve.add_argument("--report", default=DEFAULT_REPORT_PATH)
    resolve.set_defaults(func=_cmd_resolve)

    apply_cmd = subparsers.add_parser(
        "apply", help="Ingest Bob's proposed fix and approve it (human gate 2)."
    )
    apply_cmd.add_argument("resolution_id")
    apply_cmd.add_argument("bob_output", help="Path to Bob's saved proposal markdown.")
    apply_cmd.set_defaults(func=_cmd_apply)

    validate = subparsers.add_parser(
        "validate", help="Run the tests yourself and verify Bob's claimed result."
    )
    validate.add_argument("resolution_id")
    validate.add_argument("--local-path", required=True)
    validate.add_argument("--result", required=True, help="Path to Bob's saved closing output.")
    validate.add_argument("--test-command", required=True)
    validate.set_defaults(func=_cmd_validate)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDevFlow stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
