"""Build and render a repository-agnostic Change Impact Map."""

from __future__ import annotations

import json
import webbrowser
import subprocess
from pathlib import Path
from typing import Any, Optional
from devflow.models.context import ArtifactKind, RepositoryContext
from devflow.models.graph import (
    ChangeImpactMap,
    GraphEdge,
    GraphEvidence,
    GraphNode,
    GraphNodeType,
    GraphRelationship,
)
from devflow.models.history import RepositoryHistory
from devflow.models.impact import ImpactAnalysis, ImpactFinding
from devflow.models.risk import RiskAnalysis
from devflow.map._ids import artifact_node_id, change_node_id, history_node_id, risk_node_id


def build_change_impact_map(
    context: RepositoryContext,
    impact: ImpactAnalysis,
    risk_analysis: Optional[RiskAnalysis] = None,
    history: Optional[RepositoryHistory] = None,
) -> ChangeImpactMap:
    """Construct a graph model from Phase 2-5 structured outputs."""
    graph = ChangeImpactMap(
        repository_url=context.repository_url,
        owner=context.owner,
        name=context.name,
        change_summary=context.change_summary,
    )

    if context.error:
        graph.error = f"Skipped: Phase 2 context had an error: {context.error}"
        return graph
    if impact.error:
        graph.error = f"Skipped: Phase 4 impact analysis had an error: {impact.error}"
        return graph

    node_map: dict[str, GraphNode] = {}
    edge_map: dict[tuple[str, str, str], GraphEdge] = {}

    def add_node(
        node_id: str,
        label: str,
        node_type: GraphNodeType,
        description: str,
        risk_severity: Optional[str] = None,
        **metadata: Any,
    ) -> GraphNode:
        existing = node_map.get(node_id)
        if existing is None:
            node = GraphNode(
                id=node_id,
                label=label,
                node_type=node_type,
                description=description,
                metadata=dict(metadata),
                risk_severity=risk_severity,
            )
            node_map[node_id] = node
            return node
        merged = dict(existing.metadata)
        merged.update(metadata)
        node = GraphNode(
            id=existing.id,
            label=existing.label,
            node_type=existing.node_type,
            description=existing.description or description,
            metadata=merged,
            risk_severity=existing.risk_severity or risk_severity,
        )
        node_map[node_id] = node
        return node

    def add_edge(
        source: str,
        target: str,
        relationship: str,
        description: str,
        confidence: str,
        evidence: tuple[GraphEvidence, ...] = (),
    ) -> None:
        key = (source, target, relationship)
        if key in edge_map:
            return
        edge_map[key] = GraphEdge(
            source=source,
            target=target,
            relationship=relationship,
            description=description,
            confidence=confidence,
            evidence=evidence,
        )

    central_id = change_node_id()
    add_node(
        central_id,
        "Developer change",
        GraphNodeType.CHANGE,
        context.change_summary,
        repository_url=context.repository_url,
        owner=context.owner,
        name=context.name,
        summary=context.change_summary,
    )

    context_artifacts = {artifact.path: artifact for artifact in context.artifacts}
    impact_artifacts = {finding.affected_artifact for finding in impact.findings}

    # The context may be broad by design. The primary map is intentionally
    # scoped to artifacts that Phase 4 connected to this specific change.
    for artifact_path in sorted(impact_artifacts):
        artifact = context_artifacts.get(artifact_path)
        if artifact is None:
            continue
        node_id = artifact_node_id(artifact.path)
        evidence_items = (
            _graph_evidence(
                {
                    "artifact": artifact.path,
                    "description": artifact.evidence,
                    "evidence_type": _confidence_to_evidence_type(artifact.confidence),
                },
                artifact.confidence,
            ),
        )
        add_node(
            node_id,
            artifact.path,
            _node_type_for_kind(artifact.kind),
            artifact.evidence,
            evidence=[item.to_dict() for item in evidence_items],
            relevance_reason=artifact.reason.value,
            confidence=artifact.confidence,
            artifact_kind=artifact.kind.value,
        )

    for finding in impact.findings:
        target_id = artifact_node_id(finding.affected_artifact)
        evidence_items = tuple(
            _graph_evidence(ev, finding.evidence_strength.value)
            for ev in finding.evidence
        )
        add_node(
            target_id,
            finding.affected_artifact,
            _node_type_for_artifact_path(finding.affected_artifact, context),
            finding.potential_impact,
            relationship=finding.relationship.value,
            evidence_strength=finding.evidence_strength.value,
            finding_type=finding.finding_type,
            evidence=[item.to_dict() for item in evidence_items],
        )
        add_edge(
            central_id,
            target_id,
            finding.relationship.value,
            finding.potential_impact,
            finding.evidence_strength.value,
            evidence_items,
        )
    if risk_analysis:
        for index, risk in enumerate(risk_analysis.risks):
            risk_id = risk_node_id(index, risk.category.value)
            risk_evidence = tuple(
                _graph_evidence(ev, risk.evidence_strength.value)
                for ev in risk.evidence
            )
            add_node(
                risk_id,
                f"{risk.severity.value.upper()} risk",
                GraphNodeType.RISK,
                risk.explanation,
                risk_severity=risk.severity.value,
                severity=risk.severity.value,
                category=risk.category.value,
                recommendation=risk.recommended_action,
                evidence_strength=risk.evidence_strength.value,
                assessment_type=risk.assessment_type.value,
                evidence=[item.to_dict() for item in risk_evidence],
            )
            add_edge(
                central_id,
                risk_id,
                GraphRelationship.HAS_RISK.value,
                risk.explanation,
                risk.severity.value,
            )
            for artifact_path in risk.affected_artifacts:
                if artifact_path not in impact_artifacts:
                    continue
                target_id = artifact_node_id(artifact_path)
                artifact_evidence = tuple(
                    _graph_evidence(ev, risk.evidence_strength.value)
                    for ev in risk.evidence
                )
                add_node(
                    target_id,
                    artifact_path,
                    _node_type_for_artifact_path(artifact_path, context),
                    risk.explanation,
                    risk_affected=True,
                    evidence=[item.to_dict() for item in artifact_evidence],
                )
                add_edge(
                    risk_id,
                    target_id,
                    GraphRelationship.RISK_FOR.value,
                    f"{risk.category.value} risk affects '{artifact_path}'",
                    risk.severity.value,
                    artifact_evidence,
                )

    if history and not history.error:
        for artifact_path, artifact_history in history.artifact_histories.items():
            if not artifact_history.commits:
                continue
            if artifact_path not in impact_artifacts:
                continue
            history_id = history_node_id(artifact_path)
            history_evidence = tuple(
                _graph_evidence(e, "confirmed")
                for e in artifact_history.evidence
            )
            add_node(
                history_id,
                f"History: {artifact_path}",
                GraphNodeType.HISTORICAL,
                f"{len(artifact_history.commits)} relevant commit(s) for '{artifact_path}'",
                commit_count=str(len(artifact_history.commits)),
                latest_commit=artifact_history.commits[0].short_hash,
                evidence=[item.to_dict() for item in history_evidence],
            )
            target_id = artifact_node_id(artifact_path)
            add_edge(
                target_id,
                history_id,
                GraphRelationship.HISTORICALLY_CHANGED_WITH.value,
                f"Git evidence shows {len(artifact_history.commits)} historical changes.",
                "confirmed",
                history_evidence,
            )

    graph.nodes = sorted(
        node_map.values(),
        key=lambda node: (
            _node_sort_order(node.node_type),
            node.label.lower(),
        ),
    )
    graph.edges = sorted(
        edge_map.values(),
        key=lambda edge: (edge.relationship, edge.source, edge.target),
    )
    return graph


def _graph_evidence(evidence: Any, confidence: str) -> GraphEvidence:
    if isinstance(evidence, dict):
        artifact_path = evidence.get("artifact", "unknown")
        description = evidence.get("description", str(evidence))
        evidence_type = evidence.get("evidence_type", "DIRECT_EVIDENCE")
        return GraphEvidence(
            artifact=str(artifact_path),
            description=str(description),
            evidence_type=str(evidence_type),
            confidence=str(confidence),
        )
    artifact_path = getattr(evidence, "artifact_path", getattr(evidence, "artifact", "unknown"))
    description = getattr(evidence, "description", str(evidence))
    evidence_type = getattr(evidence, "evidence_type", "direct_evidence")
    if hasattr(evidence_type, "value"):
        evidence_type = evidence_type.value
    return GraphEvidence(
        artifact=str(artifact_path),
        description=str(description),
        evidence_type=str(evidence_type),
        confidence=str(confidence),
    )


def _confidence_to_evidence_type(confidence: str) -> str:
    normalized = (confidence or "possible").lower()
    if normalized == "confirmed":
        return "DIRECT_EVIDENCE"
    if normalized == "likely":
        return "DERIVED_RELATIONSHIP"
    return "INFERENCE"


def render_change_impact_map(
    graph: ChangeImpactMap,
    output_path: str | Path,
) -> Path:
    """Write a standalone HTML visualization for the graph."""
    if graph.error:
        raise ValueError(graph.error)

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_render_html(graph), encoding="utf-8")
    return target


def serialize_change_impact_map(graph: ChangeImpactMap, output_path: str | Path) -> Path:
    """Write the canonical JSON payload for the structured Phase 6 graph."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(graph.to_dict(), ensure_ascii=False, indent=2)
    target.write_text(payload, encoding="utf-8")
    return target


def write_frontend_graph_payload(graph: ChangeImpactMap, *, frontend_dir: Optional[str | Path] = None) -> Path:
    """Persist the graph payload in the Vite frontend's public directory for live dev consumption."""
    repo_root = Path(frontend_dir) if frontend_dir else Path(__file__).resolve().parents[3]
    frontend_root = repo_root / "frontend"
    target = frontend_root / "public" / "devflow-graph.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return serialize_change_impact_map(graph, target)


def open_html_in_browser(output_path: str | Path, *, opener: Optional[Any] = None) -> bool:
    """Open a generated HTML file or URL in the OS default browser without failing generation."""
    target = str(output_path)
    browser = opener or webbrowser.open

    if target.startswith(('http://', 'https://')):
        try:
            return bool(browser(target))
        except Exception:
            return False

    file_target = Path(output_path).expanduser().resolve()
    if not file_target.exists():
        raise FileNotFoundError(f"HTML output does not exist: {file_target}")

    file_url = file_target.as_uri()
    try:
        return bool(browser(file_url))
    except Exception:
        return False


def _render_html(graph: ChangeImpactMap) -> str:
    payload = json.dumps(graph.to_dict(), ensure_ascii=False)
    template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DevFlow Change Impact Map</title>
  <style>
    :root {
      --bg: #09111f;
      --panel: #101a2a;
      --panel-strong: #152031;
      --panel-soft: #1a2637;
      --line: rgba(148, 163, 184, 0.22);
      --text: #e5eefb;
      --muted: #a2b6d3;
      --change: #8b5cf6;
      --source: #60a5fa;
      --test: #34d399;
      --documentation: #fbbf24;
      --dependency: #f472b6;
      --configuration: #a78bfa;
      --historical: #f59e0b;
      --risk-low: #34d399;
      --risk-medium: #fbbf24;
      --risk-high: #f97316;
      --risk-critical: #ef4444;
      --other: #94a3b8;
    }

    * { box-sizing: border-box; }

    html, body {
      margin: 0;
      height: 100%;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, var(--bg), #0d1728);
      color: var(--text);
    }

    body { overflow: hidden; }

    .app {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr) 320px;
      min-height: 100vh;
      background: var(--bg);
    }

    .sidebar, .inspector {
      background: rgba(16, 26, 42, 0.96);
      border-right: 1px solid var(--line);
      padding: 18px 16px;
      overflow: auto;
    }

    .inspector {
      border-left: 1px solid var(--line);
      border-right: 0;
    }

    .brand {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;
      letter-spacing: 0.1em;
      font-size: 11px;
      text-transform: uppercase;
      color: #cfe0ff;
      font-weight: 700;
    }

    .brand-mark {
      width: 10px;
      height: 10px;
      border-radius: 2px;
      background: linear-gradient(135deg, #8b5cf6, #60a5fa);
      box-shadow: 0 0 16px rgba(139, 92, 246, 0.7);
    }

    .panel-title {
      margin: 0 0 10px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      font-weight: 700;
    }

    h1 {
      margin: 0 0 12px;
      font-size: 1.35rem;
      line-height: 1.3;
    }

    .summary-copy {
      margin: 0 0 14px;
      color: var(--text);
      font-size: 0.94rem;
      line-height: 1.55;
    }

    .meta-list {
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 0.8rem;
      margin-bottom: 18px;
    }

    .meta-list strong { color: var(--text); }

    .stat-card {
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      margin-bottom: 12px;
    }

    .stat-card > div {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 0.8rem;
      margin: 4px 0;
    }

    .legend {
      display: grid;
      gap: 8px;
      margin-top: 8px;
      font-size: 0.8rem;
      color: var(--muted);
    }

    .legend-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .legend-swatch {
      width: 12px;
      height: 12px;
      border-radius: 4px;
      border: 1px solid rgba(255,255,255,0.2);
      display: inline-block;
    }

    .legend-edge {
      display: inline-block;
      width: 24px;
      height: 2px;
      border-radius: 999px;
      vertical-align: middle;
      background: #cbd5e1;
    }

    .main {
      display: flex;
      flex-direction: column;
      min-width: 0;
      background: linear-gradient(180deg, rgba(9,17,31,0.75), rgba(10,19,31,0.90));
    }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      background: rgba(15, 23, 42, 0.35);
      flex-shrink: 0;
    }

    button {
      border: 1px solid var(--line);
      background: rgba(148, 163, 184, 0.08);
      color: var(--text);
      border-radius: 8px;
      padding: 7px 10px;
      font-size: 0.75rem;
      cursor: pointer;
      transition: 120ms ease;
    }

    button:hover {
      background: rgba(148, 163, 184, 0.16);
      border-color: rgba(148, 163, 184, 0.3);
    }

    .viewport {
      position: relative;
      flex: 1;
      min-height: 0;
      overflow: hidden;
      background:
        linear-gradient(rgba(148, 163, 184, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(148, 163, 184, 0.05) 1px, transparent 1px),
        radial-gradient(circle at 50% 30%, rgba(96,165,250,0.14), transparent 42%);
      background-size: 28px 28px, 28px 28px, cover;
    }

    svg {
      width: 100%;
      height: 100%;
      display: block;
      user-select: none;
      touch-action: none;
      cursor: grab;
    }

    svg.dragging { cursor: grabbing; }

    .edge-label {
      font-size: 10px;
      fill: #dfeafc;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: lowercase;
      paint-order: stroke;
      stroke: rgba(9,17,31,0.8);
      stroke-width: 4px;
      stroke-linejoin: round;
      pointer-events: none;
    }

    .node {
      cursor: pointer;
    }

    .node-label {
      fill: #f8fafc;
      font-size: 11px;
      font-weight: 700;
      text-anchor: middle;
      dominant-baseline: central;
      pointer-events: none;
    }

    .node-type {
      fill: rgba(248, 250, 252, 0.8);
      font-size: 8px;
      font-weight: 600;
      text-anchor: middle;
      pointer-events: none;
      letter-spacing: 0.1em;
    }

    .selected-node > .shape {
      filter: drop-shadow(0 0 14px rgba(248,250,252,0.6));
      stroke: #f8fafc;
      stroke-width: 2.2;
    }

    .dimmed-node { opacity: 0.22; }
    .selected-edge { filter: drop-shadow(0 0 10px rgba(248,250,252,0.7)); }
    .dimmed-edge { opacity: 0.16; }

    .tooltip {
      position: absolute;
      pointer-events: none;
      padding: 6px 8px;
      border-radius: 8px;
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid var(--line);
      color: var(--text);
      font-size: 11px;
      opacity: 0;
      transform: translate(-50%, -110%);
      transition: opacity 120ms ease;
      z-index: 10;
    }

    .inspector-section { margin-bottom: 18px; }
    .inspector-title {
      font-size: 1.05rem;
      margin: 0 0 8px;
      line-height: 1.3;
    }

    .inspector-subtitle {
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin: 0 0 6px;
    }

    .inspector-body {
      color: var(--text);
      font-size: 0.9rem;
      line-height: 1.6;
      margin: 0 0 8px;
    }

    .chip-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 8px;
      border-radius: 999px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      background: rgba(148, 163, 184, 0.08);
      color: var(--text);
      font-size: 0.73rem;
    }

    .evidence-list {
      list-style: none;
      padding: 0;
      margin: 8px 0 0;
      display: grid;
      gap: 8px;
    }

    .evidence-item {
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(255,255,255,0.02);
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.45;
    }

    .evidence-item strong { color: var(--text); }
    .empty-state {
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.6;
    }

    @media (max-width: 1100px) { .app { grid-template-columns: 240px minmax(0, 1fr) 260px; } }
    @media (max-width: 860px) {
      .app {
        grid-template-columns: 1fr;
        grid-template-rows: auto 1fr auto;
        height: 100vh;
      }
      .sidebar, .inspector { border: 0; border-bottom: 1px solid var(--line); }
      .main { min-height: 340px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark"></span> DevFlow</div>
      <h1>Change Impact Map</h1>
      <div class="summary-copy" id="summaryText"></div>
      <div class="meta-list" id="repoMeta"></div>

      <div class="stat-card">
        <div><span>Nodes</span><strong id="nodeCount">0</strong></div>
        <div><span>Edges</span><strong id="edgeCount">0</strong></div>
        <div><span>Risks</span><strong id="riskCount">0</strong></div>
      </div>

      <h2 class="panel-title">Risk summary</h2>
      <div id="riskSummary"></div>

      <h2 class="panel-title">Legend</h2>
      <div class="legend" id="legend"></div>
    </aside>

    <main class="main">
      <div class="toolbar">
        <button id="resetViewBtn" type="button">Reset view</button>
        <button id="fitGraphBtn" type="button">Fit graph</button>
      </div>
      <div class="viewport">
        <svg id="graphSvg" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid meet">
          <g id="graphLayer"></g>
        </svg>
        <div class="tooltip" id="tooltip"></div>
      </div>
    </main>

    <aside class="inspector" id="inspector"></aside>
  </div>

  <script>
    const graphData = __PAYLOAD__;
    const svg = document.getElementById('graphSvg');
    const graphLayer = document.getElementById('graphLayer');
    const inspector = document.getElementById('inspector');
    const tooltip = document.getElementById('tooltip');

    const nodeMap = new Map(graphData.nodes.map(node => [node.id, node]));
    const edgeMap = new Map(graphData.edges.map(edge => [edge.source + '->' + edge.target + ':' + edge.relationship, edge]));
    const adjacency = new Map();
    for (const node of graphData.nodes) adjacency.set(node.id, new Set());
    for (const edge of graphData.edges) {
      adjacency.get(edge.source)?.add(edge.target);
      adjacency.get(edge.target)?.add(edge.source);
    }

    const state = {
      selectedNodeId: 'change',
      selectedEdgeKey: null,
      scale: 1,
      x: 0,
      y: 0,
      dragging: false,
      dragStart: null,
      nodeEls: new Map(),
      edgeEls: new Map(),
      positions: new Map()
    };

    const nodeTypeColors = {
      change: '#8b5cf6',
      source: '#60a5fa',
      test: '#34d399',
      documentation: '#fbbf24',
      dependency: '#f472b6',
      configuration: '#a78bfa',
      historical: '#f59e0b',
      risk: '#ef4444',
      other: '#94a3b8'
    };

    const severityColors = {
      low: '#34d399',
      medium: '#fbbf24',
      high: '#f97316',
      critical: '#ef4444'
    };

    const relationshipColors = {
      modifies: '#60a5fa',
      impacts: '#a78bfa',
      tested_by: '#34d399',
      documented_by: '#fbbf24',
      depends_on: '#f472b6',
      configured_by: '#a78bfa',
      historically_changed_with: '#f59e0b',
      has_risk: '#ef4444',
      risk_for: '#ef4444',
      relevant_to: '#94a3b8',
      related_to: '#94a3b8'
    };

    function nodeTypeLabel(nodeType) {
      return String(nodeType || 'other').replace(/_/g, ' ');
    }

    function prettyRelationship(value) {
      return String(value || '').replace(/_/g, ' ');
    }

    function safeText(value) {
      return String(value || 'n/a');
    }

    function nodeShape(node, x, y, size) {
      const ns = 'http://www.w3.org/2000/svg';
      const shape = document.createElementNS(ns, 'g');
      const fill = node.node_type === 'risk'
        ? severityColors[(node.metadata && node.metadata.severity) || 'high'] || '#ef4444'
        : nodeTypeColors[node.node_type] || nodeTypeColors.other;

      if (node.node_type === 'change') {
        const rect = document.createElementNS(ns, 'rect');
        rect.setAttribute('x', String(x - size));
        rect.setAttribute('y', String(y - size * 0.78));
        rect.setAttribute('rx', '20');
        rect.setAttribute('width', String(size * 2));
        rect.setAttribute('height', String(size * 1.56));
        rect.setAttribute('fill', fill);
        rect.setAttribute('stroke', 'rgba(255,255,255,0.6)');
        rect.setAttribute('stroke-width', '1.5');
        rect.setAttribute('class', 'shape');
        shape.appendChild(rect);
      } else if (node.node_type === 'risk') {
        const points = [];
        for (let i = 0; i < 8; i += 1) {
          const angle = -Math.PI / 2 + i * (Math.PI / 4);
          const px = x + Math.cos(angle) * size;
          const py = y + Math.sin(angle) * size;
          points.push(`${px},${py}`);
        }
        const poly = document.createElementNS(ns, 'polygon');
        poly.setAttribute('points', points.join(' '));
        poly.setAttribute('fill', fill);
        poly.setAttribute('stroke', 'rgba(255,255,255,0.7)');
        poly.setAttribute('stroke-width', '1.6');
        poly.setAttribute('class', 'shape');
        shape.appendChild(poly);
      } else if (node.node_type === 'test') {
        const circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('cx', String(x));
        circle.setAttribute('cy', String(y));
        circle.setAttribute('r', String(size));
        circle.setAttribute('fill', fill);
        circle.setAttribute('stroke', 'rgba(255,255,255,0.75)');
        circle.setAttribute('stroke-width', '1.6');
        circle.setAttribute('class', 'shape');
        shape.appendChild(circle);
      } else if (node.node_type === 'documentation') {
        const rect = document.createElementNS(ns, 'rect');
        rect.setAttribute('x', String(x - size));
        rect.setAttribute('y', String(y - size));
        rect.setAttribute('width', String(size * 2));
        rect.setAttribute('height', String(size * 2));
        rect.setAttribute('rx', '8');
        rect.setAttribute('fill', fill);
        rect.setAttribute('stroke', 'rgba(255,255,255,0.7)');
        rect.setAttribute('stroke-width', '1.5');
        rect.setAttribute('class', 'shape');
        shape.appendChild(rect);
        const fold = document.createElementNS(ns, 'path');
        fold.setAttribute('d', `M ${x + size * 0.45} ${y - size} L ${x + size} ${y - size + size * 0.55} L ${x + size} ${y + size} L ${x - size} ${y + size} L ${x - size} ${y - size} Z`);
        fold.setAttribute('fill', 'rgba(255,255,255,0.12)');
        fold.setAttribute('stroke', 'rgba(255,255,255,0.18)');
        shape.appendChild(fold);
      } else if (node.node_type === 'dependency') {
        const points = [];
        for (let i = 0; i < 6; i += 1) {
          const angle = -Math.PI / 2 + i * (Math.PI / 3);
          const px = x + Math.cos(angle) * size;
          const py = y + Math.sin(angle) * size;
          points.push(`${px},${py}`);
        }
        const poly = document.createElementNS(ns, 'polygon');
        poly.setAttribute('points', points.join(' '));
        poly.setAttribute('fill', fill);
        poly.setAttribute('stroke', 'rgba(255,255,255,0.75)');
        poly.setAttribute('stroke-width', '1.5');
        poly.setAttribute('class', 'shape');
        shape.appendChild(poly);
      } else if (node.node_type === 'configuration') {
        const rect = document.createElementNS(ns, 'rect');
        rect.setAttribute('x', String(x - size));
        rect.setAttribute('y', String(y - size));
        rect.setAttribute('width', String(size * 2));
        rect.setAttribute('height', String(size * 2));
        rect.setAttribute('rx', '4');
        rect.setAttribute('transform', `skewX(-12 ${x} ${y})`);
        rect.setAttribute('fill', fill);
        rect.setAttribute('stroke', 'rgba(255,255,255,0.7)');
        rect.setAttribute('stroke-width', '1.5');
        rect.setAttribute('class', 'shape');
        shape.appendChild(rect);
      } else if (node.node_type === 'historical') {
        const diamond = document.createElementNS(ns, 'path');
        diamond.setAttribute('d', `M ${x} ${y - size} L ${x + size} ${y} L ${x} ${y + size} L ${x - size} ${y} Z`);
        diamond.setAttribute('fill', fill);
        diamond.setAttribute('stroke', 'rgba(255,255,255,0.7)');
        diamond.setAttribute('stroke-width', '1.5');
        diamond.setAttribute('class', 'shape');
        shape.appendChild(diamond);
      } else {
        const circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('cx', String(x));
        circle.setAttribute('cy', String(y));
        circle.setAttribute('r', String(size));
        circle.setAttribute('fill', fill);
        circle.setAttribute('stroke', 'rgba(255,255,255,0.7)');
        circle.setAttribute('stroke-width', '1.5');
        circle.setAttribute('class', 'shape');
        shape.appendChild(circle);
      }
      return shape;
    }

    function buildLayout() {
      const positions = new Map();
      const center = { x: 600, y: 360 };
      const queue = ['change'];
      const depthMap = new Map([['change', 0]]);
      const visited = new Set(['change']);
      while (queue.length) {
        const current = queue.shift();
        for (const neighbor of adjacency.get(current) || []) {
          if (visited.has(neighbor)) continue;
          visited.add(neighbor);
          depthMap.set(neighbor, (depthMap.get(current) || 0) + 1);
          queue.push(neighbor);
        }
      }
      const byDepth = new Map();
      for (const node of graphData.nodes) {
        const depth = depthMap.get(node.id) ?? 99;
        if (!byDepth.has(depth)) byDepth.set(depth, []);
        byDepth.get(depth).push(node);
      }
      for (const [depth, nodes] of [...byDepth.entries()].sort((a, b) => a[0] - b[0])) {
        const safeNodes = nodes.filter(node => node.id !== 'change');
        if (!safeNodes.length) continue;
        const radius = 170 + depth * 120;
        safeNodes.sort((a, b) => a.label.localeCompare(b.label));
        safeNodes.forEach((node, index) => {
          const angle = (Math.PI * 2 * index) / safeNodes.length - Math.PI / 2;
          const x = center.x + Math.cos(angle) * radius;
          const y = center.y + Math.sin(angle) * radius;
          positions.set(node.id, { x, y });
        });
      }
      for (const node of graphData.nodes) {
        if (!positions.has(node.id)) {
          const idx = positions.size;
          positions.set(node.id, { x: center.x + (idx % 6) * 45 - 110, y: center.y + Math.floor(idx / 6) * 55 - 110 });
        }
      }
      return positions;
    }

    function updateTransform() {
      graphLayer.setAttribute('transform', `translate(${state.x} ${state.y}) scale(${state.scale})`);
    }

    function resetView() {
      state.scale = 1;
      state.x = 0;
      state.y = 0;
      updateTransform();
    }

    function fitGraph() {
      const bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
      for (const { x, y } of state.positions.values()) {
        bounds.minX = Math.min(bounds.minX, x);
        bounds.minY = Math.min(bounds.minY, y);
        bounds.maxX = Math.max(bounds.maxX, x);
        bounds.maxY = Math.max(bounds.maxY, y);
      }
      const width = bounds.maxX - bounds.minX || 400;
      const height = bounds.maxY - bounds.minY || 260;
      const padding = 120;
      const scaleX = (1200 - padding * 2) / width;
      const scaleY = (800 - padding * 2) / height;
      const newScale = Math.min(1.2, Math.max(0.55, Math.min(scaleX, scaleY)));
      const cx = (bounds.minX + bounds.maxX) / 2;
      const cy = (bounds.minY + bounds.maxY) / 2;
      state.scale = newScale;
      state.x = 600 - cx * newScale;
      state.y = 400 - cy * newScale;
      updateTransform();
    }

    function summarizeEvidence() {
      const evidenceByType = { direct_evidence: 0, derived_relationship: 0, inference: 0 };
      for (const node of graphData.nodes) {
        const items = Array.isArray(node.metadata && node.metadata.evidence) ? node.metadata.evidence : [];
        for (const item of items) {
          const type = String(item && item.evidence_type || 'direct_evidence').toLowerCase().replace(/\\s+/g, '_');
          if (type.includes('direct')) evidenceByType.direct_evidence += 1;
          else if (type.includes('derived')) evidenceByType.derived_relationship += 1;
          else if (type.includes('inference')) evidenceByType.inference += 1;
        }
      }
      for (const edge of graphData.edges) {
        const items = Array.isArray(edge.evidence) ? edge.evidence : [];
        for (const item of items) {
          const type = String(item && item.evidence_type || 'direct_evidence').toLowerCase().replace(/\\s+/g, '_');
          if (type.includes('direct')) evidenceByType.direct_evidence += 1;
          else if (type.includes('derived')) evidenceByType.derived_relationship += 1;
          else if (type.includes('inference')) evidenceByType.inference += 1;
        }
      }
      return evidenceByType;
    }

    function highestRiskSeverity() {
      const risks = graphData.nodes.filter(node => node.node_type === 'risk');
      if (!risks.length) return 'None';
      const order = ['critical', 'high', 'medium', 'low'];
      let highest = 'low';
      for (const node of risks) {
        const severity = (node.metadata && node.metadata.severity) || (node.risk_severity || 'low');
        const currentRank = order.indexOf(String(severity).toLowerCase());
        const highestRank = order.indexOf(highest);
        if (currentRank > highestRank) highest = String(severity).toLowerCase();
      }
      return highest;
    }

    function renderInspector(nodeId, edgeKey) {
      if (edgeKey) {
        const edge = edgeMap.get(edgeKey);
        if (!edge) return;
        const evidence = Array.isArray(edge.evidence) ? edge.evidence : [];
        inspector.innerHTML = `
          <div class="inspector-section">
            <div class="inspector-subtitle">Edge</div>
            <h2 class="inspector-title">${prettyRelationship(edge.relationship)}</h2>
            <div class="inspector-body">${safeText(edge.description || 'No edge description provided.')}</div>
            <div class="chip-list">
              <span class="chip">Source: ${safeText(edge.source)}</span>
              <span class="chip">Target: ${safeText(edge.target)}</span>
              <span class="chip">Confidence: ${safeText(edge.confidence)}</span>
            </div>
          </div>

          <div class="inspector-section">
            <div class="inspector-subtitle">Evidence</div>
            <ul class="evidence-list">
              ${evidence.length ? evidence.map(item => `
                <li class="evidence-item"><strong>${safeText(item.artifact)}</strong><br>${safeText(item.description)}<br><em>${safeText(item.evidence_type)} • ${safeText(item.confidence)}</em></li>
              `).join('') : '<li class="evidence-item">No evidence recorded.</li>'}
            </ul>
          </div>
        `;
        return;
      }

      const node = nodeMap.get(nodeId);
      if (!node) {
        inspector.innerHTML = '<div class="empty-state">Select a node or edge to inspect its evidence and relationship details.</div>';
        return;
      }

      const metadata = node.metadata || {};
      const chips = [];
      if (metadata.confidence) chips.push(`Confidence: ${metadata.confidence}`);
      if (metadata.relationship) chips.push(`Relationship: ${prettyRelationship(metadata.relationship)}`);
      if (metadata.evidence_strength) chips.push(`Evidence: ${metadata.evidence_strength}`);
      if (metadata.severity) chips.push(`Severity: ${metadata.severity}`);
      if (metadata.category) chips.push(`Category: ${metadata.category}`);
      if (metadata.commit_count) chips.push(`Commits: ${metadata.commit_count}`);
      if (metadata.relevance_reason) chips.push(`Reason: ${safeText(metadata.relevance_reason)}`);

      const evidenceItems = metadata.evidence ? (Array.isArray(metadata.evidence) ? metadata.evidence : [metadata.evidence]) : [];
      inspector.innerHTML = `
        <div class="inspector-section">
          <div class="inspector-subtitle">${nodeTypeLabel(node.node_type)}</div>
          <h2 class="inspector-title">${safeText(node.label)}</h2>
          <div class="inspector-body">${safeText(node.description || 'No description available.')}</div>
          <div class="chip-list">${chips.map(item => `<span class="chip">${item}</span>`).join('')}</div>
        </div>

        <div class="inspector-section">
          <div class="inspector-subtitle">Evidence</div>
          <ul class="evidence-list">
            ${evidenceItems.length ? evidenceItems.map(item => `
              <li class="evidence-item"><strong>${safeText(item.artifact || node.label)}</strong><br>${safeText(item.description || item)}<br><em>${safeText(item.evidence_type || 'N/A')} • ${safeText(item.confidence || metadata.evidence_strength || metadata.confidence || 'N/A')}</em></li>
            `).join('') : '<li class="evidence-item">No evidence recorded.</li>'}
          </ul>
        </div>

        ${metadata.recommendation ? `
          <div class="inspector-section">
            <div class="inspector-subtitle">Recommendation</div>
            <div class="inspector-body">${safeText(metadata.recommendation)}</div>
          </div>
        ` : ''}
      `;
    }

    function renderSidebar() {
      const summaryText = document.getElementById('summaryText');
      const repoMeta = document.getElementById('repoMeta');
      const nodeCount = document.getElementById('nodeCount');
      const edgeCount = document.getElementById('edgeCount');
      const riskCount = document.getElementById('riskCount');
      const riskSummary = document.getElementById('riskSummary');
      const legend = document.getElementById('legend');

      const risks = graphData.nodes.filter(node => node.node_type === 'risk');
      const artifactNodes = graphData.nodes.filter(node => node.node_type !== 'change' && node.node_type !== 'risk');
      const evidenceSummary = summarizeEvidence();
      const highestRisk = highestRiskSeverity();

      summaryText.textContent = graphData.change_summary || 'Developer change summary unavailable.';
      repoMeta.innerHTML = `
        <div><strong>Repository:</strong> ${safeText(graphData.repository_url)}</div>
        <div><strong>Owner:</strong> ${safeText(graphData.owner)}</div>
        <div><strong>Name:</strong> ${safeText(graphData.name)}</div>
        <div><strong>Relevant artifacts:</strong> ${safeText(artifactNodes.length)}</div>
        <div><strong>Highest risk:</strong> ${safeText(highestRisk)}</div>
        <div><strong>Evidence:</strong> ${safeText(Object.values(evidenceSummary).reduce((total, count) => total + count, 0) ? `${evidenceSummary.direct_evidence} direct, ${evidenceSummary.derived_relationship} derived, ${evidenceSummary.inference} inference` : 'none')}</div>
      `;

      nodeCount.textContent = String(graphData.nodes.length);
      edgeCount.textContent = String(graphData.edges.length);
      riskCount.textContent = String(risks.length);

      const counts = {};
      for (const node of risks) {
        const severity = (node.metadata && node.metadata.severity) || (node.risk_severity || 'low');
        counts[severity] = (counts[severity] || 0) + 1;
      }
      const severityOrder = ['critical', 'high', 'medium', 'low'];
      riskSummary.innerHTML = severityOrder.map(level => {
        const count = counts[level] || 0;
        if (!count) return '';
        return `<div class="meta-list"><div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${severityColors[level]};margin-right:8px;"></span>${level.toUpperCase()}: <strong>${count}</strong></div></div>`;
      }).join('') || '<div class="empty-state">No explicit risk findings.</div>';

      const nodeTypes = [
        ['change', 'Change'],
        ['source', 'Source'],
        ['test', 'Test'],
        ['documentation', 'Documentation'],
        ['dependency', 'Dependency'],
        ['configuration', 'Configuration'],
        ['historical', 'Historical'],
        ['risk', 'Risk']
      ];
      const edgeTypes = ['modifies', 'impacts', 'tested_by', 'depends_on', 'documented_by', 'has_risk', 'risk_for'];
      const nodeLegend = nodeTypes.map(([type, label]) => `
        <div class="legend-row"><span class="legend-swatch" style="background:${nodeTypeColors[type]};"></span>${label}</div>
      `).join('');
      const edgeLegend = edgeTypes.map(type => `
        <div class="legend-row"><span class="legend-edge" style="background:${relationshipColors[type] || '#cbd5e1'};"></span>${prettyRelationship(type)}</div>
      `).join('');
      legend.innerHTML = nodeLegend + '<br>' + edgeLegend;
    }

    function renderGraph() {
      graphLayer.innerHTML = '';
      state.nodeEls.clear();
      state.edgeEls.clear();

      const edgesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const nodesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');

      for (const edge of graphData.edges) {
        const key = edge.source + '->' + edge.target + ':' + edge.relationship;
        const start = state.positions.get(edge.source);
        const end = state.positions.get(edge.target);
        if (!start || !end) continue;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const cx = start.x + dx * 0.5;
        const cy = start.y + dy * 0.5;
        const curve = `M ${start.x} ${start.y} Q ${cx} ${cy - 12} ${end.x} ${end.y}`;
        path.setAttribute('d', curve);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', relationshipColors[edge.relationship] || '#cbd5e1');
        path.setAttribute('stroke-width', edge.relationship === 'has_risk' || edge.relationship === 'risk_for' ? '3' : '2');
        path.setAttribute('stroke-linecap', 'round');
        path.setAttribute('opacity', '0.9');
        path.dataset.key = key;
        path.classList.add('edge');
        path.addEventListener('click', (event) => {
          event.stopPropagation();
          state.selectedNodeId = null;
          state.selectedEdgeKey = key;
          renderGraph();
          renderInspector(null, key);
        });
        path.addEventListener('mouseenter', (event) => {
          tooltip.textContent = prettyRelationship(edge.relationship);
          tooltip.style.opacity = '1';
          tooltip.style.left = `${event.clientX}px`;
          tooltip.style.top = `${event.clientY}px`;
        });
        path.addEventListener('mouseleave', () => {
          tooltip.style.opacity = '0';
        });
        edgesGroup.appendChild(path);
        state.edgeEls.set(key, path);

        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        const midX = (start.x + end.x) / 2;
        const midY = (start.y + end.y) / 2;
        label.setAttribute('x', String(midX));
        label.setAttribute('y', String(midY - 12));
        label.setAttribute('class', 'edge-label');
        label.setAttribute('text-anchor', 'middle');
        label.textContent = prettyRelationship(edge.relationship);
        label.style.pointerEvents = 'none';
        label.dataset.edgeKey = key;
        edgesGroup.appendChild(label);
      }

      for (const node of graphData.nodes) {
        const pos = state.positions.get(node.id);
        if (!pos) continue;
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        group.setAttribute('class', 'node');
        group.dataset.nodeId = node.id;

        const size = node.node_type === 'change' ? 42 : node.node_type === 'risk' ? 28 : 24;
        const shape = nodeShape(node, pos.x, pos.y, size);
        shape.setAttribute('class', 'shape');
        group.appendChild(shape);

        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        label.setAttribute('x', String(pos.x));
        label.setAttribute('y', String(pos.y + (node.node_type === 'change' ? 0 : 32)));
        label.setAttribute('class', 'node-label');
        const shortLabel = node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label;
        label.textContent = shortLabel;
        group.appendChild(label);

        const typeLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        typeLabel.setAttribute('x', String(pos.x));
        typeLabel.setAttribute('y', String(pos.y + 46));
        typeLabel.setAttribute('class', 'node-type');
        typeLabel.textContent = node.node_type.toUpperCase();
        group.appendChild(typeLabel);

        group.addEventListener('click', (event) => {
          event.stopPropagation();
          state.selectedNodeId = node.id;
          state.selectedEdgeKey = null;
          renderGraph();
          renderInspector(node.id, null);
        });
        group.addEventListener('mouseenter', (event) => {
          tooltip.textContent = `${node.label} (${node.node_type})`;
          tooltip.style.opacity = '1';
          tooltip.style.left = `${event.clientX}px`;
          tooltip.style.top = `${event.clientY}px`;
        });
        group.addEventListener('mouseleave', () => {
          tooltip.style.opacity = '0';
        });

        nodesGroup.appendChild(group);
        state.nodeEls.set(node.id, group);
      }

      graphLayer.appendChild(edgesGroup);
      graphLayer.appendChild(nodesGroup);

      const selectedNodeId = state.selectedNodeId;
      const selectedEdgeKey = state.selectedEdgeKey;

      for (const [id, group] of state.nodeEls) {
        const connected = !selectedNodeId || id === selectedNodeId || (adjacency.get(selectedNodeId) || new Set()).has(id);
        if (selectedNodeId && selectedNodeId !== id && !connected) {
          group.classList.add('dimmed-node');
        } else {
          group.classList.remove('dimmed-node');
        }
        if (selectedNodeId === id) {
          group.classList.add('selected-node');
        } else {
          group.classList.remove('selected-node');
        }
      }

      for (const [key, path] of state.edgeEls) {
        const edge = edgeMap.get(key);
        if (!edge) continue;
        const selected = selectedEdgeKey === key || (selectedNodeId && (edge.source === selectedNodeId || edge.target === selectedNodeId));
        if (selectedEdgeKey && key !== selectedEdgeKey) {
          path.classList.add('dimmed-edge');
        } else if (selectedNodeId && !selected && !selectedEdgeKey) {
          path.classList.add('dimmed-edge');
        } else {
          path.classList.remove('dimmed-edge');
        }
        if (selectedEdgeKey === key) {
          path.classList.add('selected-edge');
        } else {
          path.classList.remove('selected-edge');
        }
      }

      if (selectedNodeId) {
        renderInspector(selectedNodeId, null);
      } else if (selectedEdgeKey) {
        renderInspector(null, selectedEdgeKey);
      }
    }

    svg.addEventListener('pointerdown', (event) => {
      if (event.target === svg || event.target === graphLayer || event.target.nodeName === 'svg') {
        state.dragging = true;
        state.dragStart = { x: event.clientX, y: event.clientY, panX: state.x, panY: state.y };
        svg.classList.add('dragging');
        state.selectedNodeId = 'change';
        state.selectedEdgeKey = null;
        renderGraph();
        renderInspector('change', null);
      }
    });

    svg.addEventListener('pointermove', (event) => {
      if (!state.dragging || !state.dragStart) return;
      const dx = event.clientX - state.dragStart.x;
      const dy = event.clientY - state.dragStart.y;
      state.x = state.dragStart.panX + dx / state.scale;
      state.y = state.dragStart.panY + dy / state.scale;
      updateTransform();
    });

    svg.addEventListener('pointerup', () => {
      state.dragging = false;
      state.dragStart = null;
      svg.classList.remove('dragging');
    });

    svg.addEventListener('pointerleave', () => {
      state.dragging = false;
      state.dragStart = null;
      svg.classList.remove('dragging');
    });

    svg.addEventListener('wheel', (event) => {
      event.preventDefault();
      const zoomFactor = event.deltaY > 0 ? 0.9 : 1.1;
      const beforeScale = state.scale;
      state.scale = Math.min(2.2, Math.max(0.4, state.scale * zoomFactor));
      const rect = svg.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;
      const worldX = (mouseX - state.x) / beforeScale;
      const worldY = (mouseY - state.y) / beforeScale;
      state.x = mouseX - worldX * state.scale;
      state.y = mouseY - worldY * state.scale;
      updateTransform();
    }, { passive: false });

    document.getElementById('resetViewBtn').addEventListener('click', () => {
      resetView();
    });

    document.getElementById('fitGraphBtn').addEventListener('click', () => {
      fitGraph();
    });

    svg.addEventListener('click', (event) => {
      if (event.target === svg || event.target === graphLayer || event.target.nodeName === 'svg') {
        state.selectedNodeId = 'change';
        state.selectedEdgeKey = null;
        renderGraph();
        renderInspector('change', null);
      }
    });

    state.positions = buildLayout();
    renderSidebar();
    renderGraph();
    renderInspector('change', null);
    fitGraph();
  </script>
</body>
</html>
"""
    return template.replace('__PAYLOAD__', payload)


def _node_type_for_kind(kind: ArtifactKind) -> GraphNodeType:
    if kind == ArtifactKind.SOURCE:
        return GraphNodeType.SOURCE
    if kind == ArtifactKind.TEST:
        return GraphNodeType.TEST
    if kind == ArtifactKind.DOCUMENTATION:
        return GraphNodeType.DOCUMENTATION
    if kind == ArtifactKind.DEPENDENCY:
        return GraphNodeType.DEPENDENCY
    if kind == ArtifactKind.CONFIGURATION:
        return GraphNodeType.CONFIGURATION
    return GraphNodeType.OTHER


def _node_type_for_artifact_path(path: str, context: RepositoryContext) -> GraphNodeType:
    for artifact in context.artifacts:
        if artifact.path == path:
            return _node_type_for_kind(artifact.kind)
    return GraphNodeType.OTHER


def _node_sort_order(node_type: GraphNodeType) -> int:
    order = {
        GraphNodeType.CHANGE: 0,
        GraphNodeType.SOURCE: 1,
        GraphNodeType.TEST: 2,
        GraphNodeType.DOCUMENTATION: 3,
        GraphNodeType.DEPENDENCY: 4,
        GraphNodeType.CONFIGURATION: 5,
        GraphNodeType.HISTORICAL: 6,
        GraphNodeType.RISK: 7,
        GraphNodeType.OTHER: 8,
    }
    return order.get(node_type, 99)
