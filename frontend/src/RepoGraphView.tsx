import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  applyNodeChanges,
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  ReactFlowProvider,
} from '@xyflow/react';
import dagre from '@dagrejs/dagre';
import { ArtifactNode, Inspector } from './App';
import Dropdown from './ui/Dropdown';
import NodeIcon from './ui/NodeIcon';

// A wide, star-shaped graph (one change node, many impacted files) fits only
// by zooming until every label is unreadable. Cap the zoom so the initial
// view stays legible; the minimap and panning cover the rest.
const READABLE_MAX_ZOOM = 0.85;

/**
 * Open the repository graph on its root at a readable zoom.
 *
 * Fitting a 456-node repository scales it to roughly 0.05, which shows only a
 * grey haze. Landing on the repository root keeps labels legible; Fit, the
 * minimap and the type filters are there for the wider shape.
 */
function openAtRoot(instance: any, nodes: Node[]) {
  const root =
    nodes.find((node) => String(node.data?.nodeType) === 'repository') ?? nodes[0];
  if (!root || !instance?.setCenter) {
    instance?.fitView?.({ padding: 0.2, duration: 180, maxZoom: READABLE_MAX_ZOOM });
    return;
  }
  const width = Number(root.measured?.width ?? 200);
  const height = Number(root.measured?.height ?? 90);
  instance.setCenter(root.position.x + width / 2, root.position.y + height / 2, {
    zoom: READABLE_MAX_ZOOM,
    duration: 220,
  });
}


// Repository Knowledge Graph: a distinct product from the Change Impact Map.
// It answers "what exists in this codebase?" (orientation), not "what does
// this change affect?" -- so it gets its own payload, its own node/relationship
// vocabulary (matching devflow.models.repository_graph exactly), and its own
// simple view, per the project's explicit rule not to merge the two graph
// concepts.
export type RepoGraphData = {
  repository_url?: string;
  owner?: string;
  name?: string;
  error?: string | null;
  nodes: Array<{
    id: string;
    label: string;
    node_type?: string;
    path?: string | null;
    description?: string;
    metadata?: Record<string, any>;
    evidence?: Array<Record<string, any>>;
    confidence?: string;
  }>;
  edges: Array<{
    id?: string;
    source: string;
    target: string;
    relationship?: string;
    description?: string;
    evidence?: Array<Record<string, any>>;
    confidence?: string;
  }>;
};

const nodeHeight = 84;
const structuralNodeHeight = 68;
const minNodeWidth = 160;
const maxNodeWidth = 260;

const repoTypePalette: Record<string, string> = {
  repository: '#8b5cf6',
  directory: '#7c93b8',
  source_file: '#60a5fa',
  test_file: '#34d399',
  documentation_file: '#fbbf24',
  configuration_file: '#a78bfa',
  dependency_manifest: '#f97316',
  external_dependency: '#f472b6',
  entry_point: '#22d3ee',
  generated_file: '#94a3b8',
  other_file: '#94a3b8',
};

const repoRelationshipStyles: Record<string, { color: string; label: string }> = {
  contains: { color: '#64748b', label: 'contains' },
  imports: { color: '#60a5fa', label: 'imports' },
  imported_by: { color: '#60a5fa', label: 'imported_by' },
  depends_on: { color: '#f472b6', label: 'depends_on' },
  declares_dependency: { color: '#f97316', label: 'declares_dependency' },
  tested_by: { color: '#34d399', label: 'tested_by' },
  configured_by: { color: '#a78bfa', label: 'configured_by' },
  documented_by: { color: '#fbbf24', label: 'documented_by' },
  entry_point_for: { color: '#22d3ee', label: 'entry_point_for' },
  references: { color: '#9ca3af', label: 'references' },
};

const repoNodeTypeOptions = [
  { value: 'source_file', label: 'Source' },
  { value: 'test_file', label: 'Test' },
  { value: 'documentation_file', label: 'Docs' },
  { value: 'configuration_file', label: 'Config' },
  { value: 'dependency_manifest', label: 'Manifest' },
  { value: 'external_dependency', label: 'Dependency' },
  { value: 'directory', label: 'Directory' },
];

// Real repositories are dominated by external-dependency nodes (e.g. 214 of
// 456 nodes on the Flask sample) which add the least orientation value on
// first view. Hidden by default, one click away in the Filter dropdown --
// nothing is removed from the underlying graph, only from the initial view.
const DEFAULT_HIDDEN_TYPES = new Set<string>(['external_dependency']);

const isStructuralType = (nodeType: string) => nodeType === 'repository' || nodeType === 'directory';

const deriveRepoNodeType = (value?: string): string => {
  const normalized = (value ?? 'other_file').toLowerCase();
  if (normalized in repoTypePalette) return normalized;
  return 'other_file';
};

function nodeDimensions(nodeType: string, label: string) {
  const structural = isStructuralType(nodeType);
  const charCount = Math.max(label.length, 12);
  const base = structural ? 200 : 170;
  const cap = structural ? 320 : maxNodeWidth;
  const width = Math.min(cap, Math.max(structural ? 200 : minNodeWidth, base + Math.min(110, Math.max(0, charCount - 16) * 7)));
  return { width, height: structural ? structuralNodeHeight : nodeHeight };
}

function getRepoGraphLayout(graph: RepoGraphData) {
  const largeGraph = graph.nodes.length > 60 || graph.edges.length > 120;
  const rootNode = graph.nodes.find((node) => deriveRepoNodeType(node.node_type) === 'repository');
  const rootId = rootNode?.id ?? graph.nodes[0]?.id ?? null;

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: largeGraph ? 'LR' : 'TB',
    align: 'UL',
    nodesep: largeGraph ? 50 : 60,
    ranksep: largeGraph ? 100 : 130,
    marginx: 80,
    marginy: 70,
    acyclicer: true,
  });

  const nodes: Node[] = graph.nodes.map((node) => {
    const nodeType = deriveRepoNodeType(node.node_type);
    const { width, height } = nodeDimensions(nodeType, node.label);
    return {
      id: node.id,
      type: 'artifact',
      position: { x: 0, y: 0 },
      data: {
        id: node.id,
        label: node.label,
        nodeType,
        description: node.description ?? '',
        metadata: { ...(node.metadata ?? {}), path: node.path, evidence: node.evidence ?? [] },
      },
      className: `node-${nodeType} ${isStructuralType(nodeType) ? 'node-structural' : ''}`,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: true,
      measured: { width, height },
      style: { borderColor: repoTypePalette[nodeType] },
    };
  });

  nodes.forEach((node) => {
    const width = typeof node.measured?.width === 'number' ? node.measured.width : minNodeWidth;
    const height = typeof node.measured?.height === 'number' ? node.measured.height : nodeHeight;
    dagreGraph.setNode(node.id, { width, height });
  });

  const edges: Edge[] = graph.edges.map((edge) => {
    const relationship = edge.relationship ?? 'references';
    const style = repoRelationshipStyles[relationship] ?? { color: '#a5b4fc', label: relationship };
    return {
      id: edge.id ?? `${edge.source}-${edge.target}-${relationship}`,
      source: edge.source,
      target: edge.target,
      label: style.label,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, color: style.color },
      style: { stroke: style.color, strokeWidth: 1.4 },
      labelStyle: { fill: '#dfeaff', fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: 'rgba(11, 18, 31, 0.92)' },
      labelBgPadding: [5, 2] as [number, number],
      labelBgBorderRadius: 4,
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

  const rootPos = rootId ? dagreGraph.node(rootId) : null;
  const translateX = rootPos?.x ?? 0;
  const translateY = rootPos?.y ?? 0;

  const laidOutNodes = nodes.map((node) => {
    const gnode = dagreGraph.node(node.id);
    return { ...node, position: { x: gnode.x - translateX, y: gnode.y - translateY } };
  });

  return { nodes: laidOutNodes, edges };
}

export default function RepoGraphView({ graph, active = true }: { graph: RepoGraphData; active?: boolean }) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(() => new Set(DEFAULT_HIDDEN_TYPES));
  const [focusedNodeIds, setFocusedNodeIds] = useState<string[]>([]);
  const [focusedEdgeIds, setFocusedEdgeIds] = useState<string[]>([]);
  const [showMiniMap, setShowMiniMap] = useState(true);
  const [statusMessage, setStatusMessage] = useState<string | null>('Repository graph loaded');
  const [flowReady, setFlowReady] = useState(false);
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => getRepoGraphLayout(graph), [graph]);

  // Same live-position / derived-style separation as App.tsx: `nodes` only
  // changes via drag (onNodesChange) or a fresh graph load, so a manually
  // dragged position survives selection, search, and filter changes.
  const [nodes, setNodes] = useState<Node[]>(initialNodes);

  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const toggleType = useCallback((value: string) => {
    setHiddenTypes((current) => {
      const next = new Set(current);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }, []);

  // Directory collapse/expand: uses the real `contains` edges the backend
  // already produces (directory -> child file/directory) -- no invented
  // hierarchy, just an interaction layer on top of existing relationships.
  const [collapsedDirectories, setCollapsedDirectories] = useState<Set<string>>(new Set());

  const childrenByParent = useMemo(() => {
    const map = new Map<string, string[]>();
    initialEdges.forEach((edge) => {
      if (edge.data?.relationship !== 'contains') return;
      const list = map.get(edge.source) ?? [];
      list.push(edge.target);
      map.set(edge.source, list);
    });
    return map;
  }, [initialEdges]);

  const collapsedDescendantIds = useMemo(() => {
    const hidden = new Set<string>();
    const visit = (id: string) => {
      (childrenByParent.get(id) ?? []).forEach((childId) => {
        if (hidden.has(childId)) return;
        hidden.add(childId);
        visit(childId);
      });
    };
    collapsedDirectories.forEach((id) => visit(id));
    return hidden;
  }, [collapsedDirectories, childrenByParent]);

  const toggleDirectory = useCallback((nodeId: string) => {
    setCollapsedDirectories((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }, []);

  const searchText = searchTerm.trim().toLowerCase();

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

    const nodeMatchSet = new Set<string>();
    if (searchText) {
      nodes.forEach((node) => {
        const candidate = [node.data?.label, node.data?.nodeType, node.data?.description, (node.data?.metadata as any)?.path]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (candidate.includes(searchText)) nodeMatchSet.add(node.id);
      });
    }

    return nodes
      .filter((node) => !collapsedDescendantIds.has(node.id))
      .map((node) => {
        const nodeType = String(node.data?.nodeType ?? 'other_file');
        const isHiddenByFilter = hiddenTypes.has(nodeType);
        const isSelected = node.id === selectedNodeId;
        const isRelated = activeNodeSet.has(node.id);
        const isMatched = !searchText || nodeMatchSet.has(node.id);
        const shouldFilterDim = isHiddenByFilter && !isSelected && !isRelated;
        const shouldSearchDim = !!searchText && !isMatched && !isSelected && !isRelated;
        const opacity = shouldFilterDim ? 0.08 : shouldSearchDim ? 0.16 : isSelected || isRelated || !searchText ? 1 : 0.72;
        const isDirectory = isStructuralType(nodeType);
        const collapsed = collapsedDirectories.has(node.id);
        return {
          ...node,
          data: isDirectory
            ? {
                ...node.data,
                isDirectory: true,
                collapsed,
                childCount: (childrenByParent.get(node.id) ?? []).length,
                onToggleCollapse: () => toggleDirectory(node.id),
              }
            : node.data,
          style: {
            ...node.style,
            opacity,
            boxShadow: isSelected
              ? '0 0 0 2px rgba(96,165,250,.55), 0 16px 32px rgba(2,6,23,.55)'
              : isRelated
                ? '0 0 0 1px rgba(96,165,250,.4)'
                : undefined,
          },
        };
      });
  }, [nodes, initialEdges, childrenByParent, collapsedDescendantIds, collapsedDirectories, focusedNodeIds, hiddenTypes, searchText, selectedNodeId, toggleDirectory]);

  const displayEdges = useMemo(() => {
    const relatedEdgeSet = new Set<string>();
    if (selectedNodeId) {
      initialEdges.forEach((edge) => {
        if (edge.source === selectedNodeId || edge.target === selectedNodeId) {
          relatedEdgeSet.add(edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`);
        }
      });
    }
    focusedEdgeIds.forEach((id) => relatedEdgeSet.add(id));

    return initialEdges
      .filter((edge) => !collapsedDescendantIds.has(edge.source) && !collapsedDescendantIds.has(edge.target))
      .map((edge) => {
        const edgeId = edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`;
        const isSelected = edgeId === selectedEdgeId;
        const isRelated = relatedEdgeSet.has(edgeId);
        const sourceHidden = hiddenTypes.has(String(nodes.find((n) => n.id === edge.source)?.data?.nodeType));
        const targetHidden = hiddenTypes.has(String(nodes.find((n) => n.id === edge.target)?.data?.nodeType));
        const dim = (sourceHidden || targetHidden) && !isSelected && !isRelated;
        return {
          ...edge,
          style: {
            ...edge.style,
            strokeWidth: isSelected ? 3 : isRelated ? 2.2 : 1.4,
            opacity: dim ? 0.08 : isSelected || isRelated ? 1 : 0.5,
          },
        };
      });
  }, [initialEdges, collapsedDescendantIds, focusedEdgeIds, hiddenTypes, nodes, selectedEdgeId, selectedNodeId]);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedEdge = displayEdges.find((edge) => edge.id === selectedEdgeId) ?? null;

  const handleFit = useCallback(() => {
    if (!flowReady) return;
    const flow = (window as any).__DEVFLOW_REPO_INSTANCE__;
    if (!flow) return;
    const focusedNodes = selectedNodeId
      ? nodes.filter((node) => node.id === selectedNodeId || focusedNodeIds.includes(node.id))
      : nodes;
    const padding = graph.nodes.length > 150 ? 0.15 : 0.22;
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
  // First activation opens on the repository root rather than fitting the
  // whole graph, for the same legibility reason as the Change Impact Map.
  const hasOpened = useRef(false);
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (cancelled) return;
        const flow = (window as any).__DEVFLOW_REPO_INSTANCE__;
        if (!hasOpened.current && flow) {
          hasOpened.current = true;
          openAtRoot(flow, nodes);
          return;
        }
        handleFit();
      });
    });
    return () => {
      cancelled = true;
    };
  }, [active]);

  const resetView = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setSearchTerm('');
    setHiddenTypes(new Set(DEFAULT_HIDDEN_TYPES));
    setCollapsedDirectories(new Set());
    setFocusedNodeIds([]);
    setFocusedEdgeIds([]);
    setStatusMessage('View reset');
    setNodes(initialNodes);
    setTimeout(() => handleFit(), 0);
  }, [handleFit, initialNodes]);

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

  const onInit = useCallback(
    (instance: any) => {
      (window as any).__DEVFLOW_REPO_INSTANCE__ = instance;
      setFlowReady(true);
      // Both views stay mounted (see main.tsx); a pane that starts hidden
      // has a zero-size container, and fitting against that produces NaN
      // viewport values (breaks the <Background> pattern). Skip the initial
      // fit while hidden -- the become-active effect below fits for real
      // once this pane is actually visible.
      if (!active) return;
      openAtRoot(instance, nodes);
    },
    [active, nodes],
  );

  const onNodeClick = useCallback((_event: any, node: Node) => {
    setSelectedEdgeId(null);
    setSelectedNodeId(node.id);
    setFocusedNodeIds([]);
    setFocusedEdgeIds([]);
    setStatusMessage(`${node.data?.label ?? node.id} selected`);
  }, []);

  const onNodeDoubleClick = useCallback(
    (_event: any, node: Node) => {
      setSelectedEdgeId(null);
      setSelectedNodeId(node.id);
      focusNeighborhood(node.id);
    },
    [focusNeighborhood],
  );

  const onEdgeClick = useCallback((_event: any, edge: Edge) => {
    setSelectedNodeId(null);
    setSelectedEdgeId(edge.id ?? null);
    setStatusMessage(`${edge.data?.relationship ?? 'relationship'} selected`);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setFocusedNodeIds([]);
    setFocusedEdgeIds([]);
    setStatusMessage('Graph view restored');
    setTimeout(() => handleFit(), 0);
  }, [handleFit]);

  if (graph.error || graph.nodes.length === 0) {
    return (
      <div className="app-shell">
        <aside className="sidebar">
          <div className="panel-block">
            <div className="panel-title">STATUS</div>
            <div className="summary-change">NO REPOSITORY GRAPH LOADED</div>
          </div>
          <div className="panel-block">
            <div className="panel-title">CLI</div>
            <div className="summary-change">Run: python -m devflow</div>
          </div>
        </aside>
        <div className="graph-panel error-panel">
          <div className="error-message">NO REPOSITORY GRAPH LOADED</div>
          <div className="error-detail">
            {graph.error || 'Run: python -m devflow to explore this repository.'}
          </div>
        </div>
        <Inspector selectedNode={null} selectedEdge={null} allNodes={[]} allEdges={[]} />
      </div>
    );
  }

  const hiddenCount = nodes.filter(
    (node) => hiddenTypes.has(String(node.data?.nodeType)) || collapsedDescendantIds.has(node.id),
  ).length;

  return (
    <div className="app-shell">
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
        </div>
        <div className="stat-hero">
          <div className="stat-card">
            <span className="stat-label">Files</span>
            <strong className="stat-value">{graph.nodes.length}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">Links</span>
            <strong className="stat-value">{graph.edges.length}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-label">Hidden</span>
            <strong className="stat-value">{hiddenCount}</strong>
          </div>
        </div>
        <div className="panel-block">
          <div className="panel-title">ABOUT</div>
          <div className="summary-change">
            Orientation view of what exists in this repository -- files, tests,
            docs, configuration, and dependencies -- independent of any
            proposed change.
          </div>
        </div>
        <div className="panel-block">
          <div className="panel-title">HOW TO EXPLORE</div>
          <div className="summary-hint">
            Click a node to inspect it. Double-click to focus its immediate
            connections. Drag to rearrange. Use Filter to hide node types.
            Click the − on a directory to collapse its contents.
          </div>
        </div>
      </aside>
      <div className="graph-panel">
        <div className="toolbar toolbar-compact">
          <div className="toolbar-search-box">
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search files, paths, dependencies..."
              aria-label="Search repository graph"
            />
          </div>
          <button type="button" onClick={handleFit}>Fit</button>
          <Dropdown label="Filter" active={hiddenTypes.size > 0}>
            <div className="dropdown-list">
              {repoNodeTypeOptions.map((option) => (
                <label key={option.value} className="dropdown-checkbox">
                  <input
                    type="checkbox"
                    checked={!hiddenTypes.has(option.value)}
                    onChange={() => toggleType(option.value)}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          </Dropdown>
          <Dropdown label="Focus">
            {(close) => (
              <div className="dropdown-list">
                <button type="button" disabled={!selectedNodeId} onClick={() => { handleExploreConnections(); close(); }}>
                  Explore Connections
                </button>
                <button type="button" onClick={() => { resetView(); close(); }}>
                  Reset View
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
            minZoom={0.1}
            maxZoom={2.2}
            defaultViewport={{ x: 0, y: 0, zoom: 1 }}
            nodeTypes={{ artifact: ArtifactNode }}
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
                nodeColor={(node) => repoTypePalette[String(node.data?.nodeType ?? 'other_file')] ?? '#64748b'}
                nodeStrokeWidth={0}
                maskColor="rgba(6,11,20,0.75)"
                style={{ background: 'rgba(13,20,34,0.92)' }}
              />
            ) : null}
          </ReactFlow>
        </ReactFlowProvider>
      </div>
      <Inspector selectedNode={selectedNode} selectedEdge={selectedEdge} allNodes={nodes} allEdges={displayEdges} />
    </div>
  );
}
