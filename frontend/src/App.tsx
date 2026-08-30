import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  applyNodeChanges,
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  ReactFlowProvider,
} from '@xyflow/react';
import ReportPanel, { type ReportData } from './ReportPanel';
import Dropdown from './ui/Dropdown';
import NodeIcon from './ui/NodeIcon';
import {
  BlastRadius,
  EvidenceList,
  RankingNote,
  ResolvePathway,
  TestCoverage,
  useRepoIndex,
  type Ranking,
  type RepoIndex,
} from './insights';

export type GraphData = {
  repository_url?: string;
  owner?: string;
  name?: string;
  change_summary?: string;
  nodes: Array<{
    id: string;
    label: string;
    node_type?: string;
    description?: string;
    metadata?: Record<string, any>;
    risk_severity?: string | null;
  }>;
  edges: Array<{
    id?: string;
    source: string;
    target: string;
    relationship?: string;
    description?: string;
    confidence?: string;
    evidence?: Array<Record<string, any>>;
  }>;
};

type AppProps = { graph: GraphData; report?: ReportData; error?: string; active?: boolean };
type NodeTypeFilter = 'all' | 'change' | 'source' | 'test' | 'documentation' | 'dependency' | 'configuration' | 'historical' | 'risk';

// The radial layout keeps the whole map roughly circular rather than an
// extreme-aspect-ratio ribbon, so a modest cap keeps labels legible without
// needing to zoom out to near-illegibility the way the old tree layout did.
const READABLE_MAX_ZOOM = 0.9;

/** Open the map centred on the change itself, at a readable zoom. */
function openAtChangeNode(instance: any, nodes: Node[]) {
  const change =
    nodes.find((node) => String(node.data?.nodeType) === 'change') ?? nodes[0];
  if (!change || !instance?.setCenter) {
    instance?.fitView?.({ padding: 0.24, duration: 180, maxZoom: READABLE_MAX_ZOOM });
    return;
  }
  const width = Number(change.measured?.width ?? minNodeWidth);
  const height = Number(change.measured?.height ?? nodeHeight);
  instance.setCenter(
    change.position.x + width / 2,
    change.position.y + height / 2,
    { zoom: READABLE_MAX_ZOOM, duration: 220 },
  );
}

const nodeHeight = 68;
const changeNodeHeight = 88;
const minNodeWidth = 148;
const maxNodeWidth = 232;

const typePalette: Record<string, string> = {
  change: '#8b5cf6',
  source: '#60a5fa',
  test: '#34d399',
  documentation: '#fbbf24',
  dependency: '#f472b6',
  configuration: '#a78bfa',
  historical: '#f59e0b',
  risk: '#ef4444',
  other: '#94a3b8',
};

const relationshipStyles: Record<string, { color: string; label: string }> = {
  modifies: { color: '#8b5cf6', label: 'modifies' },
  impacts: { color: '#60a5fa', label: 'impacts' },
  tested_by: { color: '#34d399', label: 'tested_by' },
  documented_by: { color: '#fbbf24', label: 'documented_by' },
  depends_on: { color: '#f472b6', label: 'depends_on' },
  configured_by: { color: '#a78bfa', label: 'configured_by' },
  historically_changed_with: { color: '#f59e0b', label: 'historically_changed_with' },
  has_risk: { color: '#ef4444', label: 'has_risk' },
  risk_for: { color: '#f97316', label: 'risk_for' },
  relevant_to: { color: '#94a3b8', label: 'relevant_to' },
  related_to: { color: '#9ca3af', label: 'related_to' },
};

const nodeTypeOptions: Array<{ value: NodeTypeFilter; label: string }> = [
  { value: 'all', label: 'All types' },
  { value: 'source', label: 'Source' },
  { value: 'test', label: 'Test' },
  { value: 'documentation', label: 'Documentation' },
  { value: 'dependency', label: 'Dependency' },
  { value: 'configuration', label: 'Configuration' },
  { value: 'historical', label: 'Historical' },
  { value: 'risk', label: 'Risk' },
];

const deriveNodeType = (value?: string): string => {
  const normalized = (value ?? 'other').toLowerCase();
  if (normalized in typePalette) return normalized;
  return 'other';
};

// Pure display formatting -- deliberately independent of deriveNodeType's
// strict typePalette whitelist (which exists to pick a fill color and must
// fall back to 'other' for anything unrecognized). Inspector is shared by
// both the Change Impact Map and the Repository Knowledge Graph view, which
// have different node_type vocabularies (e.g. 'source' vs 'source_file'), so
// this just title-cases whatever string it's given rather than coercing
// unknown-but-real types into a meaningless "Other" label.
const formatNodeType = (value?: string): string => {
  const raw = (value ?? 'other').replace(/_/g, ' ').trim();
  return raw.replace(/\b\w/g, (char) => char.toUpperCase());
};

// Border style encodes evidence_strength/confidence when the backend
// attached it to a node's metadata -- never invented, just surfaced. Solid
// is the neutral default for nodes that carry no confidence signal at all.
const confidenceBorderStyle = (metadata?: Record<string, any>): 'solid' | 'dashed' | 'dotted' => {
  const raw = String(metadata?.confidence ?? metadata?.evidence_strength ?? '').toLowerCase();
  if (raw === 'likely') return 'dashed';
  if (raw === 'possible') return 'dotted';
  return 'solid';
};

function estimateNodeWidth(label: string, nodeType: string) {
  const charCount = Math.max(label.length, 12);
  const baseWidth = nodeType === 'change' ? 216 : 156;
  const width = baseWidth + Math.min(100, Math.max(0, charCount - 16) * 6);
  return Math.min(maxNodeWidth, Math.max(minNodeWidth, width));
}

function makeNodeData(node: GraphData['nodes'][number]): Record<string, any> {
  const nodeType = deriveNodeType(node.node_type);
  return {
    id: node.id,
    label: node.label,
    nodeType,
    description: node.description ?? node.metadata?.description ?? '',
    metadata: node.metadata ?? {},
    riskSeverity: node.risk_severity ?? node.metadata?.severity ?? null,
  };
}

const RADIAL_TYPE_ORDER = ['source', 'test', 'documentation', 'dependency', 'configuration', 'historical', 'other'];
const RING_GAP = 172;
const RISK_RING_GAP = 158;
const MIN_RING_RADIUS = 280;
const MIN_SECTOR_DEG = 26;
const SIBLING_SPREAD_DEG = 15;
const NODE_GAP = 40;

const toRad = (deg: number) => (deg * Math.PI) / 180;

type Polar = { cx: number; cy: number; angle: number; radius: number };

function sideForAngleDeg(deg: number): 'top' | 'right' | 'bottom' | 'left' {
  const a = ((deg % 360) + 360) % 360;
  if (a >= 315 || a < 45) return 'right';
  if (a < 135) return 'bottom';
  if (a < 225) return 'left';
  return 'top';
}

function buildAdjacency(nodeIds: string[], edges: GraphData['edges']) {
  const adjacency = new Map<string, string[]>();
  nodeIds.forEach((id) => adjacency.set(id, []));
  edges.forEach((edge) => {
    if (!adjacency.has(edge.source) || !adjacency.has(edge.target)) return;
    adjacency.get(edge.source)!.push(edge.target);
    adjacency.get(edge.target)!.push(edge.source);
  });
  // Deterministic traversal order regardless of the edge array's own order.
  adjacency.forEach((list) => list.sort());
  return adjacency;
}

/** Shortest-hop BFS distance (and discovery parent) from the change node, so
 * the radial layout can place directly-affected artifacts on the inner ring
 * and anything reached only transitively further out -- without assuming any
 * particular graph shape. */
function bfsFromRoot(rootId: string, adjacency: Map<string, string[]>) {
  const depth = new Map<string, number>([[rootId, 0]]);
  const parent = new Map<string, string>();
  const queue = [rootId];
  while (queue.length) {
    const current = queue.shift()!;
    const currentDepth = depth.get(current)!;
    for (const next of adjacency.get(current) ?? []) {
      if (depth.has(next)) continue;
      depth.set(next, currentDepth + 1);
      parent.set(next, current);
      queue.push(next);
    }
  }
  return { depth, parent };
}

/**
 * Radial/orbital layout: the change node anchors the centre: nodes it
 * directly touches form an inner ring clustered by type (source together,
 * tests together, etc.), risk nodes orbit just outside the specific artifact
 * they were raised against (via `risk_for`), and anything reached only
 * transitively sits one ring further out from its own discovery parent. Pure
 * function of the graph's actual relationships and node ids -- no
 * Math.random -- so the same report always produces the same composition.
 */
function getGraphLayout(graph: GraphData) {
  const entries = graph.nodes.map((node) => ({ id: node.id, label: node.label, data: makeNodeData(node) }));
  const nodeTypeById = new Map(entries.map((entry) => [entry.id, entry.data.nodeType]));
  const dims = new Map(
    entries.map((entry) => [
      entry.id,
      {
        width: estimateNodeWidth(entry.label, entry.data.nodeType),
        height: entry.data.nodeType === 'change' ? changeNodeHeight : nodeHeight,
      },
    ]),
  );

  const changeEntry = entries.find((entry) => entry.data.nodeType === 'change') ?? entries[0];
  const rootId = changeEntry?.id ?? null;
  const allIds = entries.map((entry) => entry.id);
  const adjacency = buildAdjacency(allIds, graph.edges);
  const { depth, parent } = rootId
    ? bfsFromRoot(rootId, adjacency)
    : { depth: new Map<string, number>(), parent: new Map<string, string>() };

  // risk_for is directional in the data as risk -> affected artifact, but
  // resolve it by node type rather than assume edge direction.
  const riskTargets = new Map<string, string[]>();
  graph.edges.forEach((edge) => {
    if (edge.relationship !== 'risk_for') return;
    const sourceIsRisk = nodeTypeById.get(edge.source) === 'risk';
    const targetIsRisk = nodeTypeById.get(edge.target) === 'risk';
    if (sourceIsRisk && !targetIsRisk) {
      if (!riskTargets.has(edge.source)) riskTargets.set(edge.source, []);
      riskTargets.get(edge.source)!.push(edge.target);
    } else if (targetIsRisk && !sourceIsRisk) {
      if (!riskTargets.has(edge.target)) riskTargets.set(edge.target, []);
      riskTargets.get(edge.target)!.push(edge.source);
    }
  });
  riskTargets.forEach((list) => list.sort());

  const positions = new Map<string, Polar>();
  if (rootId) positions.set(rootId, { cx: 0, cy: 0, angle: 0, radius: 0 });

  // Inner ring: everything the change directly touches, except risks (which
  // orbit their affected artifact instead) -- plus anything unreachable from
  // the change at all, so nothing the backend sent is ever dropped.
  const ring1Ids = entries
    .filter((entry) => entry.id !== rootId && entry.data.nodeType !== 'risk' && (depth.get(entry.id) === 1 || !depth.has(entry.id)))
    .map((entry) => entry.id);

  const groups = RADIAL_TYPE_ORDER.map((type) => ({
    type,
    ids: ring1Ids.filter((id) => (nodeTypeById.get(id) ?? 'other') === type),
  })).filter((group) => group.ids.length);

  const ring1Total = ring1Ids.length || 1;
  const rawSpans = groups.map((group) => Math.max(MIN_SECTOR_DEG, (group.ids.length / ring1Total) * 360));
  const rawSum = rawSpans.reduce((a, b) => a + b, 0) || 1;
  const scale = rawSum > 360 ? 360 / rawSum : 1;

  let ring1Radius = MIN_RING_RADIUS;
  let cursor = -90; // start at the top, sweep clockwise
  const ring1Angle = new Map<string, number>();
  groups.forEach((group, index) => {
    const span = rawSpans[index] * scale;
    const step = span / group.ids.length;
    group.ids.forEach((id, idx) => {
      ring1Angle.set(id, cursor + step * (idx + 0.5));
    });
    if (group.ids.length > 1) {
      const stepRad = toRad(Math.max(step, 2));
      const maxWidth = Math.max(...group.ids.map((id) => dims.get(id)!.width));
      const required = (maxWidth + NODE_GAP) / (2 * Math.sin(stepRad / 2));
      ring1Radius = Math.max(ring1Radius, required);
    }
    cursor += span;
  });
  ring1Radius = Math.min(ring1Radius, 900);

  ring1Ids.forEach((id) => {
    const angle = ring1Angle.get(id) ?? 0;
    const rad = toRad(angle);
    positions.set(id, { cx: ring1Radius * Math.cos(rad), cy: ring1Radius * Math.sin(rad), angle, radius: ring1Radius });
  });

  // Risk satellites: orbit just outside whichever artifact they were raised
  // against, so "change -> affected area -> risk" reads as a single spoke.
  const riskIds = entries.filter((entry) => entry.data.nodeType === 'risk').map((entry) => entry.id);
  const riskGroups = new Map<string, string[]>();
  riskIds.forEach((id) => {
    const key = riskTargets.get(id)?.[0] ?? '__none__';
    if (!riskGroups.has(key)) riskGroups.set(key, []);
    riskGroups.get(key)!.push(id);
  });
  riskGroups.forEach((ids) => ids.sort());
  riskGroups.forEach((ids, targetId) => {
    const targetPos = targetId !== '__none__' ? positions.get(targetId) : undefined;
    const baseAngle = targetPos?.angle ?? -90;
    const baseRadius = targetPos?.radius ?? ring1Radius;
    const n = ids.length;
    ids.forEach((id, idx) => {
      const angle = baseAngle + (idx - (n - 1) / 2) * SIBLING_SPREAD_DEG;
      const radius = baseRadius + RISK_RING_GAP;
      const rad = toRad(angle);
      positions.set(id, { cx: radius * Math.cos(rad), cy: radius * Math.sin(rad), angle, radius });
    });
  });

  // Anything reached only transitively (depth >= 2, non-risk): satellite of
  // its own BFS discovery parent, one ring further out. Generalises to
  // graphs with real multi-hop chains without special-casing them.
  const deeperIds = entries
    .filter((entry) => entry.data.nodeType !== 'risk' && (depth.get(entry.id) ?? 0) >= 2)
    .map((entry) => entry.id)
    .sort((a, b) => (depth.get(a)! - depth.get(b)!) || a.localeCompare(b));
  const childrenByParent = new Map<string, string[]>();
  deeperIds.forEach((id) => {
    const parentId = parent.get(id)!;
    if (!childrenByParent.has(parentId)) childrenByParent.set(parentId, []);
    childrenByParent.get(parentId)!.push(id);
  });
  childrenByParent.forEach((ids) => ids.sort());
  deeperIds.forEach((id) => {
    const parentId = parent.get(id)!;
    const parentPos = positions.get(parentId);
    if (!parentPos) return;
    const siblings = childrenByParent.get(parentId)!;
    const idx = siblings.indexOf(id);
    const angle = parentPos.angle + (idx - (siblings.length - 1) / 2) * SIBLING_SPREAD_DEG;
    const radius = parentPos.radius + RING_GAP;
    const rad = toRad(angle);
    positions.set(id, { cx: radius * Math.cos(rad), cy: radius * Math.sin(rad), angle, radius });
  });

  // Safety net: anything still unplaced (e.g. a risk with no resolvable
  // target and no change node at all) gets a deterministic fallback ring.
  let fallbackIndex = 0;
  entries.forEach((entry) => {
    if (positions.has(entry.id)) return;
    const angle = (fallbackIndex * 47) % 360;
    const radius = MIN_RING_RADIUS + RING_GAP;
    fallbackIndex += 1;
    positions.set(entry.id, { cx: radius * Math.cos(toRad(angle)), cy: radius * Math.sin(toRad(angle)), angle, radius });
  });

  const nodes: Node[] = entries.map((entry) => {
    const { width, height } = dims.get(entry.id)!;
    const pos = positions.get(entry.id)!;
    return {
      id: entry.id,
      type: entry.data.nodeType === 'risk' ? 'risk' : entry.data.nodeType === 'change' ? 'change' : 'artifact',
      position: { x: pos.cx - width / 2, y: pos.cy - height / 2 },
      data: entry.data,
      className: `node-${entry.data.nodeType}`,
      draggable: true,
      measured: { width, height },
    };
  });

  const edges: Edge[] = graph.edges.map((edge) => {
    const relationship = edge.relationship ?? 'related_to';
    const style = relationshipStyles[relationship] ?? { color: '#a5b4fc', label: relationship };
    const isRiskEdge = relationship === 'has_risk' || relationship === 'risk_for';
    const sourcePos = positions.get(edge.source) ?? { cx: 0, cy: 0, angle: 0, radius: 0 };
    const targetPos = positions.get(edge.target) ?? { cx: 0, cy: 0, angle: 0, radius: 0 };
    const dx = targetPos.cx - sourcePos.cx;
    const dy = targetPos.cy - sourcePos.cy;
    const directionDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
    return {
      id: edge.id ?? `${edge.source}-${edge.target}-${relationship}`,
      source: edge.source,
      target: edge.target,
      sourceHandle: `source-${sideForAngleDeg(directionDeg)}`,
      targetHandle: `target-${sideForAngleDeg(directionDeg + 180)}`,
      label: style.label,
      type: 'straight',
      markerEnd: isRiskEdge ? { type: MarkerType.ArrowClosed, color: style.color } : undefined,
      style: { stroke: style.color, strokeWidth: 2 },
      labelStyle: { fill: '#dfeaff', fontSize: 11, fontWeight: 600 },
      labelBgStyle: { fill: 'rgba(11, 18, 31, 0.92)' },
      labelBgPadding: [6, 3] as [number, number],
      labelBgBorderRadius: 4,
      animated: isRiskEdge,
      data: {
        relationship,
        description: edge.description ?? '',
        evidence: edge.evidence ?? [],
        confidence: edge.confidence ?? 'confirmed',
      },
    };
  });

  return { nodes, edges };
}

// The radial layout connects nodes in every direction, not just left-to-right,
// so each node exposes a source+target handle pair on all four sides and the
// edge builder in `getGraphLayout` picks whichever pair actually faces the
// other endpoint. The handles themselves are invisible (see index.css) --
// nodesConnectable is false, so nothing is ever dragged from them.
function FloatingHandles() {
  return (
    <>
      <Handle type="target" position={Position.Top} id="target-top" />
      <Handle type="source" position={Position.Top} id="source-top" />
      <Handle type="target" position={Position.Right} id="target-right" />
      <Handle type="source" position={Position.Right} id="source-right" />
      <Handle type="target" position={Position.Bottom} id="target-bottom" />
      <Handle type="source" position={Position.Bottom} id="source-bottom" />
      <Handle type="target" position={Position.Left} id="target-left" />
      <Handle type="source" position={Position.Left} id="source-left" />
    </>
  );
}

function ChangeNode(props: NodeProps) {
  const { data, selected } = props;
  return (
    <div className={`flow-node change ${selected ? 'selected' : ''}`}>
      <FloatingHandles />
      <div className="node-header">
        <NodeIcon type="change" />
        <span>CHANGE</span>
      </div>
      <div className="node-body">
        <strong>{data.label}</strong>
        <small>{data.metadata?.repository_url || data.metadata?.name || 'Repository change'}</small>
      </div>
    </div>
  );
}

export function ArtifactNode(props: NodeProps) {
  const { data, selected } = props;
  // isDirectory/collapsed/onToggleCollapse are only ever set by
  // RepoGraphView (for directory/repository nodes) -- the Change Impact Map
  // never sets them, so this toggle simply never renders there.
  const isDirectory = Boolean((data as any).isDirectory);
  const collapsed = Boolean((data as any).collapsed);
  const childCount = (data as any).childCount as number | undefined;
  return (
    <div className={`flow-node artifact ${selected ? 'selected' : ''}`}>
      <FloatingHandles />
      <div className="node-header">
        <NodeIcon type={String(data.nodeType || 'artifact')} />
        <span>{String(data.nodeType || 'artifact').toUpperCase()}</span>
        {isDirectory && childCount ? (
          <button
            type="button"
            className="nodrag node-collapse-toggle"
            title={collapsed ? `Expand (${childCount} hidden)` : 'Collapse'}
            onClick={(event) => {
              event.stopPropagation();
              (data as any).onToggleCollapse?.();
            }}
          >
            {collapsed ? `+${childCount}` : '−'}
          </button>
        ) : null}
      </div>
      <div className="node-body">
        <strong className="node-label-mono">{data.label}</strong>
      </div>
    </div>
  );
}

function RiskNode(props: NodeProps) {
  const { data, selected } = props;
  return (
    <div className={`flow-node risk severity-${String(data.riskSeverity || 'medium').toLowerCase()} ${selected ? 'selected' : ''}`}>
      <FloatingHandles />
      <div className="risk-header">
        <NodeIcon type="risk" />
        <span>{(data.riskSeverity || 'MEDIUM').toUpperCase()} RISK</span>
      </div>
      <div className="node-body">
        <strong className="node-label-mono">{data.label}</strong>
      </div>
    </div>
  );
}

function AnalysisOverview({
  graph,
  report,
  error,
  onSelectGraphNode,
  onFocusRisks,
  onShowAll,
}: {
  graph: GraphData;
  report?: ReportData;
  error?: string;
  onSelectGraphNode?: (nodeId: string) => void;
  onFocusRisks?: () => void;
  onShowAll?: () => void;
}) {
  const riskCount = graph.nodes.filter((node) => (node.node_type || '').toLowerCase() === 'risk').length;
  const artifactCount = graph.nodes.filter((node) => {
    const type = (node.node_type || '').toLowerCase();
    return type !== 'change' && type !== 'risk';
  }).length;
  const highestRisk = graph.nodes
    .filter((node) => (node.node_type || '').toLowerCase() === 'risk')
    .map((node) => (node.risk_severity || 'medium').toLowerCase())
    .sort((a, b) => ['low', 'medium', 'high', 'critical'].indexOf(a) - ['low', 'medium', 'high', 'critical'].indexOf(b))
    .at(-1) ?? 'none';

  return (
    <aside className="sidebar">
      <div className="context-card">
        {graph.repository_url ? (
          <a className="context-repo" href={graph.repository_url} target="_blank" rel="noopener noreferrer">
            <NodeIcon type="repository" />
            {graph.owner || 'Repository'}/{graph.name || 'project'}
          </a>
        ) : (
          <div className="context-repo context-repo-plain">
            <NodeIcon type="repository" />
            {graph.owner || 'Repository'}/{graph.name || 'project'}
          </div>
        )}
        <p className="context-change">
          {error ? 'Unable to load Phase 6 graph data.' : (graph.change_summary || 'Change not available')}
        </p>
      </div>
      <div className="stat-hero">
        <div className="stat-card">
          <span className="stat-label">Impacted</span>
          <strong className="stat-value">{error ? 0 : artifactCount}</strong>
        </div>
        <div className={`stat-card ${!error && riskCount > 0 ? 'stat-card-risk' : ''}`}>
          <span className="stat-label">Risks</span>
          <strong className="stat-value">{error ? 0 : riskCount}</strong>
        </div>
        <div className={`stat-card stat-card-severity severity-${error ? 'none' : highestRisk}`}>
          <span className="stat-label">Highest</span>
          <strong className="stat-value">{error ? 'N/A' : highestRisk.toUpperCase()}</strong>
        </div>
      </div>
      {error ? (
        <div className="panel-block">
          <div className="panel-title">ERROR</div>
          <div className="summary-change">{error}</div>
        </div>
      ) : (
        <div className="panel-block sidebar-actions">
          <button type="button" onClick={onFocusRisks}>Focus Risks</button>
          <button type="button" onClick={onShowAll}>Show All</button>
        </div>
      )}
      {report && !error ? (
        <div className="sidebar-scroll">
          <ReportPanel report={report} onSelectGraphNode={onSelectGraphNode} />
        </div>
      ) : null}
    </aside>
  );
}

export function Inspector({
  selectedNode,
  selectedEdge,
  allNodes,
  allEdges,
  repoIndex,
  rankings,
  riskFindingIdByNode,
}: {
  selectedNode: Node | null;
  selectedEdge: Edge | null;
  allNodes: Node[];
  allEdges: Edge[];
  repoIndex?: RepoIndex;
  rankings?: Map<string, Ranking>;
  riskFindingIdByNode?: Map<string, string>;
}) {
  const nodeLookup = useMemo(() => new Map(allNodes.map((node) => [node.id, node])), [allNodes]);

  if (!selectedNode && !selectedEdge) {
    return (
      <aside className="inspector empty-state">
        <svg className="inspector-empty-icon" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.5" />
          <line x1="15.3" y1="15.3" x2="20.5" y2="20.5" />
        </svg>
        <div className="inspector-empty-title">Explore the repository</div>
        <p>Select a node or relationship to understand its impact.</p>
        <p className="inspector-hint">Double-click a node to focus its immediate connections.</p>
      </aside>
    );
  }

  if (selectedEdge) {
    const evidence = Array.isArray(selectedEdge.data?.evidence) ? selectedEdge.data.evidence : [];
    const sourceNode = nodeLookup.get(selectedEdge.source);
    const targetNode = nodeLookup.get(selectedEdge.target);

    return (
      <aside className="inspector">
        <div className="panel-title">RELATIONSHIP</div>
        <div className="inspector-section">
          <div className="field-label">Type</div>
          <div>{selectedEdge.data?.relationship || 'relationship'}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Source</div>
          <div className="mono-text">{sourceNode?.data?.label ?? selectedEdge.source}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Target</div>
          <div className="mono-text">{targetNode?.data?.label ?? selectedEdge.target}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Confidence</div>
          <div>{selectedEdge.data?.confidence || 'confirmed'}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Description</div>
          <div>{selectedEdge.data?.description || 'No description available.'}</div>
        </div>
        <CollapsibleEvidence evidence={evidence} />
      </aside>
    );
  }

  // Graph node metadata is an open, payload-defined bag, so it arrives as
  // `unknown`. Narrowing it once here keeps every read below type-safe instead
  // of casting at each use site.
  const metadata: Record<string, any> = (selectedNode?.data?.metadata as Record<string, any>) ?? {};
  const connectedEdges = allEdges.filter((edge) => edge.source === selectedNode!.id || edge.target === selectedNode!.id);
  const connectedTypes = new Set<string>();
  connectedEdges.forEach((edge) => {
    const otherId = edge.source === selectedNode!.id ? edge.target : edge.source;
    const otherNode = nodeLookup.get(otherId);
    const otherType = String(otherNode?.data?.nodeType ?? 'other');
    if (otherType) connectedTypes.add(otherType);
  });
  const evidence = Array.isArray(metadata.evidence)
    ? metadata.evidence
    : selectedNode?.data?.description
      ? [{ description: selectedNode.data.description, evidence_type: 'DIRECT' }]
      : [];

  // The repository-relative path this node stands for, when it has one. Graph
  // node ids are namespaced (`artifact:src/x.py`), so strip the namespace.
  const artifactPath =
    (typeof metadata.path === 'string' && metadata.path) ||
    (typeof selectedNode?.data?.label === 'string' && selectedNode.data.label.includes('/')
      ? String(selectedNode.data.label)
      : selectedNode?.id?.includes(':')
        ? selectedNode.id.split(':').slice(1).join(':')
        : '');

  const ranking =
    (rankings && selectedNode?.id ? rankings.get(selectedNode.id) : undefined) ?? null;

  return (
    <aside className="inspector">
      <div className="panel-title">{(selectedNode?.data?.nodeType || 'ARTIFACT').toUpperCase()}</div>
      <div className="inspector-section">
        <div className="field-label">Label</div>
        <div className="mono-text">{selectedNode?.data?.label || selectedNode?.id}</div>
      </div>
      <div className="inspector-section">
        <div className="field-label">Type</div>
        <div>{formatNodeType(selectedNode?.data?.nodeType)}</div>
      </div>
      <div className="inspector-section">
        <div className="field-label">Description</div>
        <div>{selectedNode?.data?.description || 'No description available.'}</div>
      </div>
      <div className="inspector-section">
        <div className="field-label">Relationship count</div>
        <div>{connectedEdges.length}</div>
      </div>
      <div className="inspector-section">
        <div className="field-label">Connected node types</div>
        <div>{connectedTypes.size ? Array.from(connectedTypes).map((type) => formatNodeType(type)).join(', ') : 'None'}</div>
      </div>
      {selectedNode?.data?.riskSeverity ? (
        <div className="inspector-section">
          <div className="field-label">Risk</div>
          <div>{selectedNode.data.riskSeverity.toUpperCase()}</div>
        </div>
      ) : null}
      {selectedNode?.data?.metadata?.commit_count || selectedNode?.data?.metadata?.latest_commit ? (
        <div className="inspector-section">
          <div className="field-label">Historical</div>
          <div>
            {selectedNode.data.metadata.commit_count ? `${selectedNode.data.metadata.commit_count} commits` : 'Git history linked'}
            {selectedNode.data.metadata.latest_commit ? ` · latest ${selectedNode.data.metadata.latest_commit}` : ''}
          </div>
        </div>
      ) : null}
      {/* Structural context, mirroring what `devflow explain` prints. Rendered
          only when the Repository Knowledge Graph actually contains this file,
          so nothing here is inferred from a filename. */}
      {artifactPath && repoIndex ? (
        <>
          <BlastRadius path={artifactPath} index={repoIndex} />
          <TestCoverage path={artifactPath} index={repoIndex} />
        </>
      ) : null}
      <RankingNote ranking={ranking} />
      {selectedNode?.data?.nodeType === 'risk' && riskFindingIdByNode?.has(selectedNode.id) ? (
        <ResolvePathway findingId={riskFindingIdByNode.get(selectedNode.id)!} />
      ) : null}
      <CollapsibleEvidence evidence={evidence} />
    </aside>
  );
}

function CollapsibleEvidence({ evidence }: { evidence: Array<Record<string, any>> }) {
  const [open, setOpen] = useState(evidence.length <= 2);
  return (
    <div className="insp-section">
      <button
        type="button"
        className="insp-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="insp-section-title-inline">Evidence</span>
        <span className="insp-toggle-count">{evidence.length}</span>
      </button>
      {open ? <EvidenceList evidence={evidence} /> : null}
    </div>
  );
}

function Legend() {
  return (
    <div className="legend-box">
      <div className="legend-header">LEGEND</div>
      <div className="legend-body">
        <div className="legend-group">
          <div className="legend-title">NODE TYPES</div>
          <div className="legend-items">
            {['Change', 'Source', 'Test', 'Documentation', 'Dependency', 'Configuration', 'Historical', 'Risk'].map((type) => (
              <div key={type} className="legend-item">
                <NodeIcon type={type.toLowerCase()} />
                {type}
              </div>
            ))}
          </div>
        </div>
        <div className="legend-group">
          <div className="legend-title">EVIDENCE</div>
          <div className="legend-items compact">
            <span className="legend-pill legend-pill-line solid">confirmed</span>
            <span className="legend-pill legend-pill-line dashed">likely</span>
            <span className="legend-pill legend-pill-line dotted">possible</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function App({ graph, report, error, active = true }: AppProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [riskFocus, setRiskFocus] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState<NodeTypeFilter>('all');
  const [relationshipFilter, setRelationshipFilter] = useState<string>('all');
  const [focusedNodeIds, setFocusedNodeIds] = useState<string[]>([]);
  const [focusedEdgeIds, setFocusedEdgeIds] = useState<string[]>([]);
  const [showMiniMap, setShowMiniMap] = useState(true);
  const [flashNodeId, setFlashNodeId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>('Change impact map loaded');

  // Structural evidence for the inspector: the import graph supplies blast
  // radius and test coverage, the report's prioritization supplies rank and
  // rationale. Both are optional; the inspector degrades without them.
  const repoIndex = useRepoIndex();
  const rankings = useMemo(() => {
    const byGraphNode = new Map<string, Ranking>();
    const entries = report?.prioritization?.rankings ?? [];
    const findingById = new Map(
      (report?.findings ?? []).map((finding: any) => [String(finding.id), finding]),
    );
    for (const entry of entries as Ranking[]) {
      const finding = findingById.get(String(entry.finding_id));
      const nodeId = finding?.graph_node_id;
      if (nodeId) byGraphNode.set(String(nodeId), entry);
    }
    return byGraphNode;
  }, [report]);

  // Maps a risk graph node to the finding id the resolution CLI expects, so
  // the inspector can offer the exact `devflow.resolution request` command
  // for the finding actually behind that node -- never invented.
  const riskFindingIdByNode = useMemo(() => {
    const map = new Map<string, string>();
    for (const finding of (report?.findings ?? []) as any[]) {
      if (finding.category === 'risk' && finding.graph_node_id) {
        map.set(String(finding.graph_node_id), String(finding.id));
      }
    }
    return map;
  }, [report]);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => getGraphLayout(graph), [graph]);

  // `nodes` holds live positions -- it is the ONLY state that changes on
  // drag (via onNodesChange) or on a fresh graph load (via the effect
  // below). Visual styling (selection/search/filter highlighting) is a pure
  // per-render derivation in `displayNodes`/`displayEdges` further down, so
  // it can never clobber a manually dragged position.
  const [nodes, setNodes] = useState<Node[]>(initialNodes);
  const [flowReady, setFlowReady] = useState(false);

  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const displayNodes = useMemo(() => {
    const activeNodeSet = new Set<string>();
    if (selectedNodeId) {
      activeNodeSet.add(selectedNodeId);
      initialEdges.forEach((edge) => {
        if (edge.source === selectedNodeId || edge.target === selectedNodeId) {
          activeNodeSet.add(edge.source);
          activeNodeSet.add(edge.target);
        }
      });
    }
    focusedNodeIds.forEach((id) => activeNodeSet.add(id));

    const searchText = searchTerm.trim().toLowerCase();
    const nodeMatchSet = new Set<string>();
    if (searchText) {
      nodes.forEach((node) => {
        const candidate = [node.data?.label, node.data?.nodeType, node.data?.description, node.data?.metadata?.path, node.data?.metadata?.artifact_kind]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (candidate.includes(searchText)) nodeMatchSet.add(node.id);
      });
    }

    return nodes.map((node) => {
      const nodeType = String(node.data?.nodeType ?? 'other');
      const isVisible = typeFilter === 'all' || nodeType === typeFilter;
      const isSelected = node.id === selectedNodeId;
      const isRelated = activeNodeSet.has(node.id);
      const isMatched = !searchText || nodeMatchSet.has(node.id);
      const isRisk = nodeType === 'risk';
      const shouldDim = selectedNodeId ? !isSelected && !isRelated && !isMatched && !isRisk : !isMatched && !isRisk && !!searchText;
      const shouldFilterDim = typeFilter !== 'all' && !isVisible && !isSelected;
      const opacity = shouldFilterDim || shouldDim ? 0.16 : isSelected || isRelated || isRisk || !searchText ? 1 : 0.72;
      const borderColor = isSelected ? '#f8fafc' : isRelated ? '#60a5fa' : isRisk ? undefined : undefined;
      const boxShadow = isSelected ? '0 0 0 2px rgba(96,165,250,.55), 0 16px 32px rgba(2,6,23,.55)' : isRelated ? '0 0 0 1px rgba(96,165,250,.4)' : undefined;
      const isFlashing = node.id === flashNodeId;
      return {
        ...node,
        className: [node.className, isFlashing ? 'node-flash' : ''].filter(Boolean).join(' '),
        style: {
          ...node.style,
          opacity,
          borderColor,
          boxShadow,
          borderStyle: confidenceBorderStyle(node.data?.metadata as Record<string, any> | undefined),
        },
      };
    });
  }, [nodes, initialEdges, flashNodeId, focusedNodeIds, searchTerm, selectedNodeId, typeFilter]);

  const displayEdges = useMemo(() => {
    const searchText = searchTerm.trim().toLowerCase();
    const edgeMatchSet = new Set<string>();
    if (searchText) {
      initialEdges.forEach((edge) => {
        const candidate = [edge.data?.relationship, edge.data?.description, edge.data?.confidence, edge.source, edge.target]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (candidate.includes(searchText)) edgeMatchSet.add(edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`);
      });
    }
    const relatedEdgeSet = new Set<string>();
    if (selectedNodeId) {
      initialEdges.forEach((edge) => {
        if (edge.source === selectedNodeId || edge.target === selectedNodeId) {
          relatedEdgeSet.add(edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`);
        }
      });
    }
    focusedEdgeIds.forEach((id) => relatedEdgeSet.add(id));

    return initialEdges.map((edge) => {
      const edgeId = edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`;
      const relationship = String(edge.data?.relationship ?? 'related_to');
      const isSelected = edgeId === selectedEdgeId;
      const isRelated = relatedEdgeSet.has(edgeId);
      const isVisible = relationshipFilter === 'all' || relationship === relationshipFilter;
      const isMatched = !searchText || edgeMatchSet.has(edgeId);
      const isRiskEdge = relationship === 'has_risk' || relationship === 'risk_for';
      const dim = !isVisible || (!isSelected && !isRelated && !isMatched && !!searchText && !riskFocus);
      const opacity = dim ? 0.15 : isSelected || isRelated || isRiskEdge || riskFocus ? 1 : 0.55;
      const stroke = relationshipStyles[relationship]?.color ?? '#a5b4fc';
      return {
        ...edge,
        style: { stroke, strokeWidth: isSelected ? 3.5 : isRiskEdge ? 2.6 : 1.5, opacity },
        // Animation is reserved for what actually matters: a selected edge,
        // or the risk path itself. Everything else stays static so motion
        // keeps meaning something instead of becoming background noise.
        animated: isSelected || isRiskEdge,
        label: isVisible ? relationshipStyles[relationship]?.label ?? relationship : '',
      };
    });
  }, [initialEdges, focusedEdgeIds, relationshipFilter, riskFocus, searchTerm, selectedEdgeId, selectedNodeId]);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedEdge = displayEdges.find((edge) => edge.id === selectedEdgeId) ?? null;

  const handleFit = useCallback(() => {
    if (!flowReady) return;
    const flow = (window as any).__DEVFLOW_INSTANCE__;
    if (!flow) return;
    if (focusedNodeIds.length) {
      // An explicit focus set (Focus Risks, Explore Connections): frame
      // exactly that set with a bounding-box fit -- these are deliberately
      // an area of the map, not a single point.
      const focusedNodes = nodes.filter((node) => focusedNodeIds.includes(node.id) || node.id === selectedNodeId);
      const padding = graph.nodes.length > 100 ? 0.18 : 0.22;
      flow.fitView({ padding, duration: 220, maxZoom: READABLE_MAX_ZOOM, nodes: focusedNodes.length ? focusedNodes : undefined });
      return;
    }
    if (selectedNodeId) {
      // A plain selection: centre directly on the node rather than fitting a
      // bounding box of it plus its graph-neighbours. In this radial layout
      // almost every node's neighbour set includes the change node at the
      // far centre, so that bounding box is nearly as wide as the whole
      // graph -- fitting it would barely zoom in at all.
      const node = nodes.find((candidate) => candidate.id === selectedNodeId);
      if (node) {
        const width = Number(node.measured?.width ?? minNodeWidth);
        const height = Number(node.measured?.height ?? nodeHeight);
        flow.setCenter(node.position.x + width / 2, node.position.y + height / 2, { zoom: 1.05, duration: 220 });
        return;
      }
    }
    const padding = graph.nodes.length > 100 ? 0.18 : 0.22;
    flow.fitView({ padding, duration: 220, maxZoom: READABLE_MAX_ZOOM });
  }, [flowReady, focusedNodeIds, graph.nodes.length, nodes, selectedNodeId]);

  // Recentre whenever selection/focus actually changes -- as its own effect
  // rather than a `setTimeout(handleFit, 0)` scattered into every setter
  // call, so it always reads this render's fresh state instead of whatever
  // was captured in the closure that scheduled the timeout. Deliberately NOT
  // keyed on `nodes`, so dragging a node (which also changes `nodes`) never
  // yanks the viewport back to a recenter mid-drag.
  useEffect(() => {
    handleFit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeId, focusedNodeIds, riskFocus]);

  // Both views stay mounted (see main.tsx) so search/filter/selection/drag
  // state survives switching tabs -- but React Flow computes fitView against
  // whatever size its container had at init, which is zero while its pane is
  // hidden. Re-fit once whenever this pane actually becomes visible -- wait
  // two animation frames so the browser has actually completed the
  // hidden->visible layout reflow (a bare setTimeout(0) can still land
  // before that reflow, which is what produced the NaN viewport in the
  // first place).
  //
  // The very first time this pane becomes visible we open on the change node
  // rather than fitting, so the hero node is centred and legible immediately.
  // Later activations re-fit, because by then the developer has a selection
  // or focus worth framing.
  const hasOpened = useRef(false);
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (cancelled) return;
        const flow = (window as any).__DEVFLOW_INSTANCE__;
        if (!hasOpened.current && flow) {
          hasOpened.current = true;
          openAtChangeNode(flow, nodes);
          return;
        }
        handleFit();
      });
    });
    return () => {
      cancelled = true;
    };
  }, [active]);

  const resetGraph = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setRiskFocus(false);
    setSearchTerm('');
    setTypeFilter('all');
    setRelationshipFilter('all');
    setFocusedNodeIds([]);
    setFocusedEdgeIds([]);
    setStatusMessage('Graph reset');
    setNodes(initialNodes);
    // Show All must always reframe the whole graph, even when there was no
    // selection/focus to clear (e.g. after manually panning around) -- so it
    // fits directly rather than relying on the selection-change effect,
    // which wouldn't fire if selection was already empty.
    if (flowReady) {
      const flow = (window as any).__DEVFLOW_INSTANCE__;
      flow?.fitView?.({ padding: graph.nodes.length > 100 ? 0.18 : 0.22, duration: 220, maxZoom: READABLE_MAX_ZOOM });
    }
    document.querySelector('.sidebar-scroll')?.scrollTo({ top: 0 });
  }, [flowReady, graph.nodes.length, initialNodes]);

  const handleFocusRisks = useCallback(() => {
    const riskIds = new Set(nodes.filter((node) => node.data?.nodeType === 'risk').map((node) => node.id));
    if (!riskIds.size) {
      setRiskFocus(false);
      setStatusMessage('No risk findings found for this change.');
      return;
    }

    const relatedIds = new Set<string>();
    initialEdges.forEach((edge) => {
      if (riskIds.has(edge.source) || riskIds.has(edge.target)) {
        relatedIds.add(edge.source);
        relatedIds.add(edge.target);
      }
    });

    setRiskFocus(true);
    setFocusedNodeIds(Array.from(relatedIds));
    setFocusedEdgeIds([]);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setStatusMessage('Risk-focused view');
  }, [initialEdges, nodes]);

  const focusNeighborhood = useCallback(
    (nodeId: string) => {
      const neighborIds = new Set<string>();
      const neighborEdgeIds = new Set<string>();
      initialEdges.forEach((edge) => {
        if (edge.source === nodeId || edge.target === nodeId) {
          neighborIds.add(edge.source);
          neighborIds.add(edge.target);
          neighborEdgeIds.add(edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`);
        }
      });
      setFocusedNodeIds(Array.from(neighborIds));
      setFocusedEdgeIds(Array.from(neighborEdgeIds));
      setStatusMessage('Exploring local neighborhood');
    },
    [initialEdges],
  );

  const handleExploreConnections = useCallback(() => {
    if (!selectedNodeId) {
      setStatusMessage('Select a node to explore its neighborhood.');
      return;
    }
    focusNeighborhood(selectedNodeId);
  }, [focusNeighborhood, selectedNodeId]);

  const focusSelectedNode = useCallback(() => {
    if (!selectedNodeId) return;
    setStatusMessage('Focused on selected node');
    // Selection hasn't changed here, so the selection-change effect above
    // won't fire on its own -- this is an explicit "redo the fit" action.
    handleFit();
  }, [handleFit, selectedNodeId]);

  const handleReportNodeSelect = useCallback(
    (nodeId: string) => {
      setSelectedEdgeId(null);
      setSelectedNodeId(nodeId);
      setFocusedNodeIds([]);
      setFocusedEdgeIds([]);
      setRiskFocus(false);
      const label = nodes.find((node) => node.id === nodeId)?.data?.label ?? nodeId;
      setStatusMessage(`Report linked to ${label}`);
      setFlashNodeId(nodeId);
      setTimeout(() => setFlashNodeId(null), 900);
    },
    [nodes],
  );

  const onNodeClick = useCallback(
    (_event: any, node: Node) => {
      setSelectedEdgeId(null);
      setSelectedNodeId(node.id);
      setFocusedNodeIds([]);
      setFocusedEdgeIds([]);
      setRiskFocus(false);
      setStatusMessage(`${node.data?.label ?? node.id} selected`);
      // Recentring happens in the selection-change effect above, once this
      // selection actually lands in state.
    },
    [],
  );

  const onNodeDoubleClick = useCallback(
    (_event: any, node: Node) => {
      setSelectedEdgeId(null);
      setSelectedNodeId(node.id);
      setRiskFocus(false);
      focusNeighborhood(node.id);
    },
    [focusNeighborhood],
  );

  const onEdgeClick = useCallback(
    (_event: any, edge: Edge) => {
      setSelectedNodeId(null);
      setSelectedEdgeId(edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`);
      setFocusedNodeIds([]);
      setFocusedEdgeIds([]);
      setRiskFocus(false);
      setStatusMessage(`${edge.data?.relationship ?? 'relationship'} selected`);
    },
    [],
  );

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setFocusedNodeIds([]);
    setFocusedEdgeIds([]);
    setRiskFocus(false);
    setStatusMessage('Graph view restored');
  }, []);

  const onInit = useCallback(
    (instance: any) => {
      (window as any).__DEVFLOW_INSTANCE__ = instance;
      setFlowReady(true);
      // Both views stay mounted (see main.tsx); a pane that starts hidden
      // has a zero-size container, and fitting against that produces NaN
      // viewport values (breaks the <Background> pattern). Skip the initial
      // fit while hidden -- the become-active effect below fits for real
      // once this pane is actually visible.
      if (!active) return;
      openAtChangeNode(instance, nodes);
    },
    [active, nodes],
  );

  if (error && graph.nodes.length === 0) {
    return (
      <div className="app-shell">
        <aside className="sidebar">
          <div className="panel-block">
            <div className="panel-title">STATUS</div>
            <div className="summary-change">NO ANALYSIS LOADED</div>
          </div>
          <div className="panel-block">
            <div className="panel-title">CLI</div>
            <div className="summary-change">Run: python -m devflow</div>
          </div>
        </aside>
        <div className="graph-panel error-panel">
          <div className="error-message">NO ANALYSIS LOADED</div>
          <div className="error-detail">Run: python -m devflow to generate a Change Impact Map.</div>
        </div>
        <Inspector selectedNode={null} selectedEdge={null} allNodes={[]} allEdges={[]} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="app-shell">
        <AnalysisOverview graph={graph} report={report} error={error} onSelectGraphNode={handleReportNodeSelect} />
        <div className="graph-panel error-panel">
          <div className="error-message">Unable to load Phase 6 graph data.</div>
          <div className="error-detail">{error}</div>
        </div>
        <Inspector selectedNode={null} selectedEdge={null} allNodes={[]} allEdges={[]} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <AnalysisOverview
        graph={graph}
        report={report}
        error={error}
        onSelectGraphNode={handleReportNodeSelect}
        onFocusRisks={handleFocusRisks}
        onShowAll={resetGraph}
      />
      <div className="graph-panel">
        <div className="toolbar toolbar-compact">
          <div className="toolbar-search-box">
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search nodes, paths, relationships..."
              aria-label="Search graph"
            />
          </div>
          <button type="button" onClick={handleFit}>Fit</button>
          <button type="button" className={riskFocus ? 'active' : ''} onClick={handleFocusRisks}>Focus Risks</button>
          <Dropdown label="Filter" active={typeFilter !== 'all'}>
            <div className="dropdown-list">
              {nodeTypeOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={typeFilter === option.value ? 'active' : ''}
                  onClick={() => setTypeFilter(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </Dropdown>
          <Dropdown label="View" align="right" active={relationshipFilter !== 'all'}>
            {(close) => (
              <div className="dropdown-list">
                <div className="dropdown-group-title">Relationships</div>
                <button
                  type="button"
                  className={relationshipFilter === 'all' ? 'active' : ''}
                  onClick={() => setRelationshipFilter('all')}
                >
                  All relationships
                </button>
                {Object.keys(relationshipStyles).map((key) => (
                  <button
                    key={key}
                    type="button"
                    className={relationshipFilter === key ? 'active' : ''}
                    onClick={() => setRelationshipFilter(key)}
                  >
                    {key.replace(/_/g, ' ')}
                  </button>
                ))}
                <div className="dropdown-group-title">Focus</div>
                <button type="button" disabled={!selectedNodeId} onClick={() => { focusSelectedNode(); close(); }}>
                  Focus Node
                </button>
                <button type="button" disabled={!selectedNodeId} onClick={() => { handleExploreConnections(); close(); }}>
                  Explore Connections
                </button>
                <button type="button" onClick={() => { resetGraph(); close(); }}>
                  Reset / Show All
                </button>
                <div className="dropdown-group-title">Display</div>
                <label className="dropdown-checkbox">
                  <input type="checkbox" checked={showMiniMap} onChange={(event) => setShowMiniMap(event.target.checked)} />
                  Minimap
                </label>
              </div>
            )}
          </Dropdown>
        </div>
        {statusMessage ? <div className="graph-status">{statusMessage}</div> : null}
        <ReactFlowProvider>
          <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            onNodesChange={onNodesChange}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick}
            onInit={onInit}
            fitView={false}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
            minZoom={0.2}
            maxZoom={2.2}
            defaultViewport={{ x: 0, y: 0, zoom: 1 }}
            nodeTypes={{ change: ChangeNode, artifact: ArtifactNode, risk: RiskNode }}
            className="devflow-reactflow"
            panOnScroll
          >
            <Background color="#1f2a3c" gap={16} />
            <Controls showInteractive={false} />
            {showMiniMap ? (
              <MiniMap
                position="bottom-left"
                pannable
                zoomable
                nodeColor={(node) => typePalette[String(node.data?.nodeType ?? 'other')] ?? '#64748b'}
                nodeStrokeWidth={0}
                maskColor="rgba(6,11,20,0.75)"
                style={{ background: 'rgba(13,20,34,0.92)' }}
              />
            ) : null}
          </ReactFlow>
        </ReactFlowProvider>
        <Legend />
      </div>
      <Inspector
        selectedNode={selectedNode}
        selectedEdge={selectedEdge}
        allNodes={nodes}
        allEdges={displayEdges}
        repoIndex={repoIndex}
        rankings={rankings}
        riskFindingIdByNode={riskFindingIdByNode}
      />
    </div>
  );
}

export default function AppRoot({ graph, report, error, active }: AppProps) {
  return <App graph={graph} report={report} error={error} active={active} />;
}
