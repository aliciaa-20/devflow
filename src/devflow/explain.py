"""`devflow explain` -- why a single finding matters, in the terminal.

Answers the question a developer actually asks when handed a finding:

    "Why is this risky, what proves it, and what breaks if I get it wrong?"

Everything rendered here already exists in the Developer Report and the
Repository Knowledge Graph.  This module joins and presents them; it computes
no new judgment, and it labels every claim by the strength of the evidence
behind it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from devflow.graph_index import RepositoryGraphIndex, build_graph_index
from devflow.models.repository_graph import RepositoryKnowledgeGraph
from devflow.render import (
    bullet,
    evidence_mark,
    field,
    heading,
    legend,
    paint,
    rule,
    severity_badge,
    tree,
    wrap,
)

DEFAULT_REPO_GRAPH_PATH = "frontend/public/devflow-repo-graph.json"

# Git hashes appear inside history evidence descriptions; surfacing them
# separately lets the developer go straight to `git show`.
_COMMIT_RE = re.compile(r"\b([0-9a-f]{7,40})\b")


def load_repository_graph(path: str | Path) -> Optional[RepositoryKnowledgeGraph]:
    """Load the Repository Knowledge Graph payload, if one has been generated."""
    graph_path = Path(path)
    if not graph_path.is_file():
        return None
    try:
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return RepositoryKnowledgeGraph.from_dict(payload)
    except Exception:  # noqa: BLE001
        return None


def find_finding(report: dict[str, Any], finding_id: str) -> Optional[dict[str, Any]]:
    for finding in report.get("findings") or []:
        if str(finding.get("id")) == finding_id:
            return finding
    return None


def _ranking_for(report: dict[str, Any], finding_id: str) -> Optional[dict[str, Any]]:
    prioritization = report.get("prioritization") or {}
    for entry in prioritization.get("rankings") or []:
        if str(entry.get("finding_id")) == finding_id:
            return entry
    return None


def _subject_paths(finding: dict[str, Any], index: RepositoryGraphIndex) -> list[str]:
    """Affected artifacts that the import graph actually contains."""
    return [
        path
        for path in (finding.get("affected_artifacts") or [])
        if index.available and index.has_file(path)
    ]


def _blast_radius_section(paths: list[str], index: RepositoryGraphIndex) -> list[str]:
    lines: list[str] = []
    for path in paths:
        dependents = index.transitive_dependents(path)
        direct = set(index.imported_by(path))
        if not dependents:
            lines.append(
                field("exposure", "no file in the analyzed import graph imports this")
            )
            continue

        lines.append(
            field(
                "exposure",
                f"{paint(str(len(dependents)), 'bold')} file(s) reach it "
                f"({len(direct)} directly)",
            )
        )
        lines.append("")

        def children_of(node: str) -> list[str]:
            return list(index.imported_by(node))

        def annotate(node: str, depth: int) -> str:
            return "direct import" if depth == 0 else ""

        lines.extend(
            "  " + line
            for line in tree(path, children_of, max_depth=2, annotate=annotate)
        )
    return lines


def _evidence_section(finding: dict[str, Any]) -> list[str]:
    evidence = finding.get("evidence") or []
    if not evidence:
        return [field("evidence", paint("none recorded", "grey"))]
    lines: list[str] = []
    for item in evidence:
        mark, label = evidence_mark(item.get("evidence_type"))
        body = " ".join(str(item.get("description") or "").split())
        wrapped = wrap(body, indent=6)
        if wrapped:
            first = wrapped[0].lstrip()
            lines.append(f"  {mark}  {paint(label, 'grey')}")
            lines.append(f"      {first}")
            lines.extend(wrapped[1:])
        lines.append("")
    return lines


# A busy file can carry dozens of commits; the recent ones carry the signal.
_MAX_HISTORY_LINES = 8

_MESSAGE_RE = re.compile(r'Message:\s*"([^"]+)"')


def _history_section(report: dict[str, Any], paths: list[str]) -> list[str]:
    """Recent commits touching the same artifacts, newest first."""
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for finding in report.get("findings") or []:
        if finding.get("category") != "historical":
            continue
        artifacts = set(finding.get("affected_artifacts") or [])
        if not artifacts.intersection(paths):
            continue
        for item in finding.get("evidence") or []:
            description = " ".join(str(item.get("description") or "").split())
            commit_match = _COMMIT_RE.search(description)
            commit = commit_match.group(1)[:7] if commit_match else ""
            if commit and commit in seen:
                continue
            if commit:
                seen.add(commit)
            # Prefer the commit subject over the full evidence sentence.
            message_match = _MESSAGE_RE.search(description)
            summary = (
                message_match.group(1)
                if message_match
                else description.replace(commit_match.group(1), "").strip(" .:")
                if commit_match
                else description
            )
            entries.append((commit, summary))

    lines: list[str] = []
    for commit, summary in entries[:_MAX_HISTORY_LINES]:
        prefix = paint(commit.ljust(7), "magenta") + "  " if commit else " " * 9
        wrapped = wrap(summary, indent=11)
        if wrapped:
            lines.append("  " + prefix + wrapped[0].lstrip())
            lines.extend(wrapped[1:])
    if len(entries) > _MAX_HISTORY_LINES:
        lines.append(
            paint(f"  ... {len(entries) - _MAX_HISTORY_LINES} older commit(s)", "grey")
        )
    return lines


def _coverage_section(paths: list[str], index: RepositoryGraphIndex) -> list[str]:
    lines: list[str] = []
    for path in paths:
        tests = index.tests_for(path)
        if tests:
            for test in tests:
                lines.append(f"  {paint('covered', 'green')}  {test}")
        else:
            lines.append(
                f"  {paint('gap', 'yellow')}      no test is structurally "
                f"associated with {path}"
            )
    return lines


def _confidence_section(finding: dict[str, Any], ranking: Optional[dict]) -> list[str]:
    lines = [
        field("evidence strength", str(finding.get("evidence_strength") or "unrated")),
        field(
            "claim type",
            paint("interpretation - not an established defect", "yellow")
            if finding.get("is_inference")
            else paint("supported by direct repository evidence", "green"),
        ),
    ]
    if ranking:
        source = str(ranking.get("source") or "deterministic")
        origin = (
            paint("IBM watsonx.ai judgment", "blue")
            if source == "watsonx"
            else paint("DevFlow deterministic ordering", "grey")
        )
        lines.append(field("ranked #%s by" % ranking.get("rank"), origin))
        rationale = " ".join(str(ranking.get("rationale") or "").split())
        if rationale:
            lines.extend(wrap(rationale, indent=4))
    return lines


def explain_finding(
    report: dict[str, Any],
    finding_id: str,
    *,
    repo_graph_path: str | Path = DEFAULT_REPO_GRAPH_PATH,
) -> list[str]:
    """Render the full explanation for one finding."""
    finding = find_finding(report, finding_id)
    if finding is None:
        available = [str(f.get("id")) for f in (report.get("findings") or [])][:8]
        raise ValueError(
            f"No finding '{finding_id}' in the current report. "
            f"Try one of: {', '.join(available)}"
            + ("..." if len(report.get("findings") or []) > 8 else "")
        )

    index = build_graph_index(load_repository_graph(repo_graph_path))
    paths = _subject_paths(finding, index)
    ranking = _ranking_for(report, finding_id)

    out: list[str] = []
    out.append("")
    out.append(rule(finding_id))
    out.append("")
    # The badge already states the severity; strip it from the title so the
    # header does not read "HIGH   HIGH code risk".
    title = str(finding.get("title") or "")
    severity = str(finding.get("severity") or "")
    if severity and title.lower().startswith(severity.lower()):
        title = title[len(severity) :].strip() or title
    out.append(f" {severity_badge(finding.get('severity'))} {paint(title, 'bold')}")
    artifacts = finding.get("affected_artifacts") or []
    if artifacts:
        out.append(f"          {paint(', '.join(artifacts), 'cyan')}")
    out.append("")

    out.append(heading("why this matters"))
    out.extend(wrap(str(finding.get("description") or "")))
    if finding.get("potential_impact"):
        out.append("")
        out.extend(wrap(str(finding["potential_impact"])))
    out.append("")

    if paths:
        out.append(heading("blast radius"))
        out.extend(_blast_radius_section(paths, index))
        out.append("")
    elif not index.available:
        out.append(heading("blast radius"))
        out.append(
            field("unavailable", paint("no repository graph on disk", "grey"))
        )
        out.append("")

    out.append(heading("evidence"))
    out.append(
        legend(
            [
                (paint("*", "green"), "observed fact"),
                (paint("o", "cyan"), "derived"),
                (paint("?", "yellow"), "interpretation"),
            ]
        )
    )
    out.append("")
    out.extend(_evidence_section(finding))

    history = _history_section(report, paths or artifacts)
    if history:
        out.append(heading("history"))
        out.extend(history)
        out.append("")

    if paths:
        coverage = _coverage_section(paths, index)
        if coverage:
            out.append(heading("test coverage"))
            out.extend(coverage)
            out.append("")

    out.append(heading("confidence"))
    out.extend(_confidence_section(finding, ranking))
    out.append("")

    if finding.get("recommendation"):
        out.append(heading("recommended action"))
        out.extend(wrap(str(finding["recommendation"])))
        out.append("")

    out.append(heading("next"))
    out.append(f"  devflow resolve {finding_id}")
    out.append("")
    return out
