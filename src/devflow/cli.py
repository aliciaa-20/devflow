"""DevFlow developer CLI.

Five journey commands plus two read-only inspection commands:

    devflow analyze   <repo-url> "<change>"    change     -> understand
    devflow findings                           understand -> prioritize
    devflow explain   <finding-id>             why it matters
    devflow status                             where it stands
    devflow resolve   <finding-id>             prioritize -> resolve   [GATE 1]
    devflow apply     <resolution-id> <file>   resolve -> implement    [GATE 2]
    devflow validate  <resolution-id> ...      implement -> verified

This module is a presentation layer over the same entry points used by
``python -m devflow`` and ``python -m devflow.resolution``. It performs no
analysis of its own: it formats what those produce and tells the developer
what to run next.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from devflow.render import (
    check,
    command_hint,
    emit,
    field,
    paint,
    progress,
    rule,
    section,
    severity_badge,
    steps,
    table,
    title,
    wrap,
)

DEFAULT_REPORT_PATH = "frontend/public/devflow-report.json"
DEFAULT_REPO_GRAPH_PATH = "frontend/public/devflow-repo-graph.json"

EPILOG = """\
typical session:
  devflow analyze https://github.com/pallets/flask "Refactor request context handling."
  devflow findings --top 5
  devflow explain risk:0:code
  devflow resolve risk:0:code

evidence markers:
  *  observed fact          parsed from the repository (import edge, git commit)
  o  derived relationship   inferred from structure (a test named after a module)
  ?  interpretation         a judgement, never an established defect

colour is disabled automatically when output is piped, when NO_COLOR is set,
or under TERM=dumb.
"""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_report(path: str) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.is_file():
        raise FileNotFoundError(
            f"No report at '{path}'. Run `devflow analyze <repo-url> \"<change>\"` first."
        )
    return json.loads(report_path.read_text(encoding="utf-8"))


def _watsonx_config(disabled: bool):
    """Build a config, honouring an explicit request to skip watsonx.

    ``disabled`` must be passed through rather than simulated with empty
    credentials: an empty API key falls back to the environment, so the call
    would still go out.
    """
    from devflow.watsonx._client import WatsonxConfig

    return WatsonxConfig(disabled=True) if disabled else None


def _prioritization_label(prioritization: dict[str, Any]) -> str:
    if str(prioritization.get("source")) == "watsonx":
        label = paint("IBM watsonx.ai", "blue")
        model = prioritization.get("model_id")
        if model:
            label += paint(f" ({model})", "grey")
        if prioritization.get("from_cache"):
            label += paint(" [cached]", "grey")
        return label
    return paint("deterministic", "grey")


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

_PIPELINE_STEPS = 4


def _cmd_analyze(args: argparse.Namespace) -> int:
    if args.serve:
        from devflow.__main__ import main as run_devflow

        return run_devflow([args.repository_url, args.change])

    # devflow.__main__ enables INFO-level logging as a module-level side
    # effect for its own (server) entry point; importing it below for
    # _analyze_repository would otherwise pull that in here too, leaking
    # internal progress/debug logging -- including temporary clone paths --
    # into this command's polished output. logging.basicConfig() is a no-op
    # once handlers exist, so claiming the configuration first keeps this
    # command's own verbosity in charge without touching devflow.__main__.
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    from devflow.__main__ import _analyze_repository
    from devflow.models.change import ChangeRequestError
    from devflow.models.repository import RepositoryInputError

    emit(title("devflow analyze", args.repository_url))
    emit(wrap(args.change, indent=2))
    print()
    print(paint("  reconstructing context from the repository...", "grey"))

    try:
        graph, report = _analyze_repository(args.repository_url, args.change)
    except (RepositoryInputError, ChangeRequestError, ValueError) as exc:
        print(paint(f"\n  failed: {exc}", "red"), file=sys.stderr)
        return 1

    print(progress(1, _PIPELINE_STEPS, "repository context reconstructed"))
    print(progress(2, _PIPELINE_STEPS, "impact and risk analysed from import edges"))
    print(progress(3, _PIPELINE_STEPS, "change impact map and report built"))

    prioritization = _prioritize_and_persist(report, no_watsonx=args.no_watsonx)
    print(progress(4, _PIPELINE_STEPS, "findings prioritized"))

    risks = [f for f in (report.findings or []) if getattr(f, "category", "") == "risk"]
    emit(section("result"))
    emit(
        table(
            [
                ["change impact map", f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"],
                ["developer report", f"{len(report.findings)} findings"],
                ["risk findings", str(len(risks))],
                ["prioritized by", _prioritization_label(prioritization.to_dict())],
            ]
        )
    )
    if prioritization.error:
        emit(wrap(prioritization.error, indent=2))

    emit(section("next"))
    print(command_hint("devflow findings --top 5", "what to look at first"))
    print(command_hint("devflow status", "where this change stands"))
    print()
    return 0


def _prioritize_and_persist(report, *, no_watsonx: bool):
    """Rank the report's findings and rewrite the payload with the result."""
    from devflow.report import write_frontend_report_payload
    from devflow.watsonx import prioritize_findings

    prioritization = prioritize_findings(
        report.to_dict(),
        config=_watsonx_config(no_watsonx),
        use_cache=not no_watsonx,
    )
    write_frontend_report_payload(report, prioritization=prioritization)
    return prioritization


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------


def _cmd_findings(args: argparse.Namespace) -> int:
    payload = _load_report(args.report)
    findings = {str(f.get("id")): f for f in payload.get("findings") or []}
    if not findings:
        emit(title("devflow findings"))
        print(paint("  No findings in the current report.", "grey"))
        print()
        print(command_hint('devflow analyze <repo-url> "<change>"'))
        return 0

    prioritization = payload.get("prioritization")
    # A stored ranking is reused only when the developer has not asked for a
    # different one. --no-watsonx must re-rank: otherwise it would silently
    # display the watsonx ordering it was invoked to avoid.
    if prioritization is None or args.refresh or args.no_watsonx:
        from devflow.watsonx import prioritize_findings

        prioritization = prioritize_findings(
            payload,
            config=_watsonx_config(args.no_watsonx),
            use_cache=not args.no_watsonx,
        ).to_dict()

    rankings = prioritization.get("rankings") or []
    if args.json:
        print(json.dumps(prioritization, indent=2))
        return 0

    emit(title("devflow findings", str(payload.get("change_summary") or "")))
    emit(
        table(
            [
                ["ranked by", _prioritization_label(prioritization)],
                ["findings", f"{len(rankings)} total, showing {min(args.top, len(rankings))}"],
            ]
        )
    )
    if prioritization.get("error"):
        emit(wrap(str(prioritization["error"]), indent=2))
    discarded = prioritization.get("discarded_finding_ids") or []
    if discarded:
        emit(
            wrap(
                f"Discarded {len(discarded)} identifier(s) the model returned that "
                f"DevFlow does not recognise: {', '.join(discarded)}",
                indent=2,
            )
        )

    emit(section("priority order"))
    for entry in rankings[: args.top]:
        finding = findings.get(str(entry.get("finding_id")), {})
        origin = "watsonx" if entry.get("source") == "watsonx" else "deterministic"
        print(
            f"  {paint('#' + str(entry.get('rank')), 'bold')}"
            f"{severity_badge(entry.get('severity'))}  "
            f"{paint(str(entry.get('finding_id')), 'cyan')}"
        )
        emit(wrap(str(entry.get("title") or finding.get("title") or ""), indent=6))
        emit(wrap(f"{origin}: {entry.get('rationale')}", indent=6))
        artifacts = finding.get("affected_artifacts") or []
        if artifacts:
            emit(wrap(", ".join(artifacts[:4]), indent=6))
        print()

    remaining = len(rankings) - args.top
    if remaining > 0:
        print(paint(f"  {remaining} more — use --top {len(rankings)} to see all.", "grey"))

    emit(section("next"))
    top_id = str(rankings[0].get("finding_id")) if rankings else "<finding-id>"
    print(command_hint(f"devflow explain {top_id}", "why it matters"))
    print(command_hint(f"devflow resolve {top_id}", "start a resolution"))
    print()
    return 0


# ---------------------------------------------------------------------------
# explain / status
# ---------------------------------------------------------------------------


def _cmd_explain(args: argparse.Namespace) -> int:
    from devflow.explain import explain_finding

    payload = _load_report(args.report)
    emit(explain_finding(payload, args.finding_id, repo_graph_path=args.repo_graph))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from devflow.status import build_status, load_sessions

    try:
        report = _load_report(args.report)
    except FileNotFoundError:
        report = None
    emit(build_status(report, load_sessions(args.sessions_dir)))
    return 0


# ---------------------------------------------------------------------------
# resolve / apply / validate  (delegate to the Phase 8 resolution CLI)
# ---------------------------------------------------------------------------


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
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    analyze = subparsers.add_parser(
        "analyze",
        help="Reconstruct context and build the map and report.",
        description="Clone the repository, reconstruct context, and build the "
        "Change Impact Map and Developer Report.",
    )
    analyze.add_argument("repository_url", metavar="<repo-url>")
    analyze.add_argument("change", metavar="<change>", help="Developer change description.")
    analyze.add_argument(
        "--serve", action="store_true", help="Open the interactive map after analysis."
    )
    analyze.add_argument(
        "--no-watsonx",
        action="store_true",
        help="Rank deterministically; do not call IBM watsonx.ai.",
    )
    analyze.set_defaults(func=_cmd_analyze)

    findings = subparsers.add_parser(
        "findings",
        help="Findings in priority order, with rationale.",
        description="Show what to investigate first and why.",
    )
    findings.add_argument("--top", type=int, default=5, metavar="N", help="How many to show (default 5).")
    findings.add_argument("--json", action="store_true", help="Emit the raw ranking JSON.")
    findings.add_argument("--report", default=DEFAULT_REPORT_PATH, metavar="PATH")
    findings.add_argument(
        "--refresh", action="store_true", help="Re-rank instead of reusing the stored ranking."
    )
    findings.add_argument(
        "--no-watsonx",
        action="store_true",
        help="Rank deterministically; implies --refresh.",
    )
    findings.set_defaults(func=_cmd_findings)

    explain = subparsers.add_parser(
        "explain",
        help="Why one finding is risky.",
        description="Blast radius, evidence, history and test coverage for a "
        "single finding.",
    )
    explain.add_argument("finding_id", metavar="<finding-id>")
    explain.add_argument("--report", default=DEFAULT_REPORT_PATH, metavar="PATH")
    explain.add_argument(
        "--repo-graph",
        default=DEFAULT_REPO_GRAPH_PATH,
        metavar="PATH",
        help="Path to the Repository Knowledge Graph payload.",
    )
    explain.set_defaults(func=_cmd_explain)

    status = subparsers.add_parser(
        "status",
        help="Where the change stands.",
        description="Findings, approval gates, and what DevFlow verified.",
    )
    status.add_argument("--report", default=DEFAULT_REPORT_PATH, metavar="PATH")
    status.add_argument("--sessions-dir", default="bob_sessions", metavar="PATH")
    status.set_defaults(func=_cmd_status)

    resolve = subparsers.add_parser(
        "resolve",
        help="Start a Bob resolution (human gate 1).",
        description="Print the finding and its evidence, then ask for approval "
        "to have IBM Bob investigate it.",
    )
    resolve.add_argument("finding_id", metavar="<finding-id>")
    resolve.add_argument("--report", default=DEFAULT_REPORT_PATH, metavar="PATH")
    resolve.set_defaults(func=_cmd_resolve)

    apply_cmd = subparsers.add_parser(
        "apply",
        help="Ingest Bob's proposal (human gate 2).",
        description="Parse Bob's proposed fix and ask for approval to apply it.",
    )
    apply_cmd.add_argument("resolution_id", metavar="<resolution-id>")
    apply_cmd.add_argument("bob_output", metavar="<bob-output.md>")
    apply_cmd.set_defaults(func=_cmd_apply)

    validate = subparsers.add_parser(
        "validate",
        help="Run the tests yourself and verify Bob's claim.",
        description="Execute the test command and a real git diff, then "
        "reconcile the result against what Bob reported.",
    )
    validate.add_argument("resolution_id", metavar="<resolution-id>")
    validate.add_argument("--local-path", required=True, metavar="PATH")
    validate.add_argument("--result", required=True, metavar="PATH", help="Bob's saved closing output.")
    validate.add_argument("--test-command", required=True, metavar="CMD")
    validate.set_defaults(func=_cmd_validate)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(paint(f"Error: {exc}", "red"), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDevFlow stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
