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
import dagre from '@dagrejs/dagre';
import ReportPanel, { type ReportData } from './ReportPanel';
import Dropdown from './ui/Dropdown';
import {
  BlastRadius,
  EvidenceList,
  RankingNote,
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

// A wide, star-shaped graph (one change node, many impacted files) fits only
// by zooming until every label is unreadable. Cap the zoom so the initial
// view stays legible; the minimap and panning cover the rest.
const READABLE_MAX_ZOOM = 0.85;

/**
 * Open the map centred on the change itself, at a readable zoom.
 *
 * A change with many impacted files lays out as an extremely wide ribbon --
 * roughly 8000px across and 700px tall on the Flask sample. Fitting that into
 * a viewport means scaling to ~0.2, where every label is an illegible smear.
 * Landing on the change node instead shows the developer what they asked about
 * and its nearest neighbours at full size; Fit, the minimap and panning are
 * still there for the overview.
 */
function openAtChangeNode(instance: any, nodes: Node[]) {
  const change =
    nodes.find((node) => String(node.data?.nodeType) === 'change') ?? nodes[0];
  if (!change || !instance?.setCenter) {
    instance?.fitView?.({ padding: 0.24, duration: 180, maxZoom: READABLE_MAX_ZOOM });
    return;
  }
  const width = Number(change.measured?.width ?? minNodeWidth);
  instance.setCenter(
    change.position.x + width / 2,
    change.position.y + nodeHeight / 2,
    { zoom: READABLE_MAX_ZOOM, duration: 220 },
  );
}

const nodeHeight = 92;
const minNodeWidth = 170;
const maxNodeWidth = 280;

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
  const baseWidth = nodeType === 'change' ? 220 : 180;
  const width = baseWidth + Math.min(120, Math.max(0, charCount - 16) * 7);
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

function getGraphLayout(graph: GraphData) {
  const largeGraph = graph.nodes.length > 40 || graph.edges.length > 80;
  const changeNode = graph.nodes.find((node) => deriveNodeType(node.node_type) === 'change');
  const rootId = changeNode?.id ?? graph.nodes[0]?.id ?? null;

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: largeGraph ? 'LR' : 'TB',
    align: 'UL',
    nodesep: largeGraph ? 60 : 70,
    ranksep: largeGraph ? 120 : 150,
    marginx: 80,
    marginy: 70,
    acyclicer: true,
  });

  const nodes: Node[] = graph.nodes.map((node) => {
    const data = makeNodeData(node);
    const width = estimateNodeWidth(node.label, data.nodeType);
    return {
      id: node.id,
      type: data.nodeType === 'risk' ? 'risk' : data.nodeType === 'change' ? 'change' : 'artifact',
      position: { x: 0, y: 0 },
      data,
      className: `node-${data.nodeType}`,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: true,
      measured: { width, height: nodeHeight },
    };
  });

  nodes.forEach((node) => {
    const width =
      typeof node.measured?.width === 'number'
        ? node.measured.width
        : estimateNodeWidth(String(node.data?.label ?? ''), String(node.data?.nodeType ?? 'artifact'));
    dagreGraph.setNode(node.id, { width, height: nodeHeight });
  });

  const edges: Edge[] = graph.edges.map((edge) => {
    const relationship = edge.relationship ?? 'related_to';
    const style = relationshipStyles[relationship] ?? { color: '#a5b4fc', label: relationship };
    return {
      id: edge.id ?? `${edge.source}-${edge.target}-${relationship}`,
      source: edge.source,
      target: edge.target,
      label: style.label,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, color: style.color },
      style: { stroke: style.color, strokeWidth: 2 },
      labelStyle: { fill: '#dfeaff', fontSize: 11, fontWeight: 600 },
      labelBgStyle: { fill: 'rgba(11, 18, 31, 0.92)' },
      labelBgPadding: [6, 3] as [number, number],
      labelBgBorderRadius: 4,
      animated: false,
      data: {
        relationship,
        description: edge.description ?? '',
        evidence: edge.evidence ?? [],
        confidence: edge.confidence ?? 'confirmed',
      },
    };
  });

  edges.forEach((edge) => dagreGraph.setEdge(edge.source, edge.target));
  dagre.layout(dagreGraph);

  const rootNode = rootId ? dagreGraph.node(rootId) : null;
  const translateX = rootNode?.x ?? 0;
  const translateY = rootNode?.y ?? 0;

  const laidOutNodes = nodes.map((node) => {
    const gnode = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: gnode.x - translateX,
        y: gnode.y - translateY,
      },
    };
  });

  return { nodes: laidOutNodes, edges };
}

function ChangeNode(props: NodeProps) {
  const { data, selected } = props;
  return (
    <div className={`flow-node change ${selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-header">CHANGE</div>
      <div className="node-body">
        <strong>{data.label}</strong>
        <small>{data.metadata?.repository_url || data.metadata?.name || 'Repository change'}</small>
      </div>
      <Handle type="source" position={Position.Right} />
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
      <Handle type="target" position={Position.Left} />
      <div className="node-header">
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
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function RiskNode(props: NodeProps) {
  const { data, selected } = props;
  return (
    <div className={`flow-node risk severity-${String(data.riskSeverity || 'medium').toLowerCase()} ${selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <div className="risk-header">{(data.riskSeverity || 'MEDIUM').toUpperCase()} RISK</div>
      <div className="node-body">
        <strong className="node-label-mono">{data.label}</strong>
      </div>
      <Handle type="source" position={Position.Right} />
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
      <div className="brand"><span className="brand-mark" /> DEVFLOW</div>
      <div className="view-kicker view-kicker-change">Change Impact Map</div>
      <div className="panel-block">
        <div className="panel-title">CHANGE</div>
        <div className="summary-change">{error ? 'Unable to load Phase 6 graph data.' : (graph.change_summary || 'Change not available')}</div>
      </div>
      {graph.repository_url && (
        <div className="panel-block">
          <div className="panel-title">REPOSITORY</div>
          <div className="repo-link">
            <a href={graph.repository_url} target="_blank" rel="noopener noreferrer">
              {graph.owner || 'Repository'}/{graph.name || 'project'}
            </a>
          </div>
        </div>
      )}
      <div className="panel-block compact-metrics">
        <div><span>IMPACT</span><strong>{error ? 0 : artifactCount}</strong></div>
        <div className={!error && riskCount > 0 ? 'metric-risk' : ''}><span>RISKS</span><strong>{error ? 0 : riskCount}</strong></div>
        <div><span>HIGHEST</span><strong>{error ? 'N/A' : highestRisk.toUpperCase()}</strong></div>
      </div>
      {error ? (
        <div className="panel-block">
          <div className="panel-title">ERROR</div>
          <div className="summary-change">{error}</div>
        </div>
      ) : (
        <div className="panel-block">
          <div className="panel-title">ACTIONS</div>
          <div className="toolbar-stack">
            <button type="button" onClick={onFocusRisks}>Focus Risks</button>
            <button type="button" onClick={onShowAll}>Show All</button>
          </div>
        </div>
      )}
      {report && !error ? <ReportPanel report={report} onSelectGraphNode={onSelectGraphNode} /> : null}
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
}: {
  selectedNode: Node | null;
  selectedEdge: Edge | null;
  allNodes: Node[];
  allEdges: Edge[];
  repoIndex?: RepoIndex;
  rankings?: Map<string, Ranking>;
}) {
  const nodeLookup = useMemo(() => new Map(allNodes.map((node) => [node.id, node])), [allNodes]);

  if (!selectedNode && !selectedEdge) {
    return (
      <aside className="inspector empty-state">
        <div className="panel-title">INSPECT</div>
        <p>Select a node or relationship to inspect impact, evidence and risk.</p>
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
        <div className="insp-section">
          <div className="insp-section-title">Evidence</div>
          <EvidenceList evidence={evidence} />
        </div>
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
      <div className="insp-section">
        <div className="insp-section-title">Evidence</div>
        <EvidenceList evidence={evidence} />
      </div>
    </aside>
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
                <span className={`legend-swatch ${type.toLowerCase()}`} />
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
        animated: isSelected || (riskFocus && isRiskEdge),
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
    const focusedNodes = selectedNodeId
      ? nodes.filter((node) => node.id === selectedNodeId || focusedNodeIds.includes(node.id))
      : nodes;
    const padding = graph.nodes.length > 100 ? 0.18 : 0.22;
    flow.fitView({ padding, duration: 220, maxZoom: READABLE_MAX_ZOOM, nodes: focusedNodes.length ? focusedNodes : undefined });
  }, [flowReady, focusedNodeIds, graph.nodes.length, nodes, selectedNodeId]);

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
  // rather than fitting: fitting an 8000px-wide ribbon scales it to ~0.2 and
  // nothing is readable. Later activations re-fit, because by then the
  // developer has a selection or focus worth framing.
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
    setTimeout(() => handleFit(), 0);
  }, [handleFit, initialNodes]);

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
    setTimeout(() => handleFit(), 0);
  }, [handleFit, initialEdges, nodes]);

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
      setTimeout(() => handleFit(), 0);
    },
    [handleFit, initialEdges],
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
    setTimeout(() => handleFit(), 0);
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
      setTimeout(() => handleFit(), 0);
    },
    [handleFit, nodes],
  );

  const onNodeClick = useCallback(
    (_event: any, node: Node) => {
      setSelectedEdgeId(null);
      setSelectedNodeId(node.id);
      setFocusedNodeIds([]);
      setFocusedEdgeIds([]);
      setRiskFocus(false);
      setStatusMessage(`${node.data?.label ?? node.id} selected`);
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
    setTimeout(() => handleFit(), 0);
  }, [handleFit]);

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
          <div className="brand"><span className="brand-mark" /> DEVFLOW</div>
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
          <Dropdown label="Relationships" active={relationshipFilter !== 'all'}>
            <div className="dropdown-list">
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
            </div>
          </Dropdown>
          <Dropdown label="Focus">
            {(close) => (
              <div className="dropdown-list">
                <button type="button" disabled={!selectedNodeId} onClick={() => { focusSelectedNode(); close(); }}>
                  Focus Node
                </button>
                <button type="button" disabled={!selectedNodeId} onClick={() => { handleExploreConnections(); close(); }}>
                  Explore Connections
                </button>
                <button type="button" onClick={() => { resetGraph(); close(); }}>
                  Reset / Show All
                </button>
              </div>
            )}
          </Dropdown>
          <Dropdown label="Display" align="right">
            <div className="dropdown-list">
              <label className="dropdown-checkbox">
                <input type="checkbox" checked={showMiniMap} onChange={(event) => setShowMiniMap(event.target.checked)} />
                Minimap
              </label>
            </div>
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
      />
    </div>
  );
}

export default function AppRoot({ graph, report, error, active }: AppProps) {
  return <App graph={graph} report={report} error={error} active={active} />;
}
