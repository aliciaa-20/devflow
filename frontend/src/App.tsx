import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  ReactFlowProvider,
} from '@xyflow/react';
import dagre from '@dagrejs/dagre';

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

type AppProps = { graph: GraphData; error?: string };
type NodeTypeFilter = 'all' | 'change' | 'source' | 'test' | 'documentation' | 'dependency' | 'configuration' | 'historical' | 'risk';

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
  { value: 'all', label: 'All' },
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

const formatNodeType = (value?: string): string => {
  const normalized = deriveNodeType(value);
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
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

function ArtifactNode(props: NodeProps) {
  const { data, selected } = props;
  return (
    <div className={`flow-node artifact ${selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-header">{String(data.nodeType || 'artifact').toUpperCase()}</div>
      <div className="node-body">
        <strong>{data.label}</strong>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function RiskNode(props: NodeProps) {
  const { data, selected } = props;
  return (
    <div className={`flow-node risk ${selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <div className="risk-header">{(data.riskSeverity || 'MEDIUM').toUpperCase()} RISK</div>
      <div className="node-body">
        <strong>{data.label}</strong>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function AnalysisOverview({ graph, error }: { graph: GraphData; error?: string }) {
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
        <div><span>RISKS</span><strong>{error ? 0 : riskCount}</strong></div>
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
            <button type="button">Focus Risks</button>
            <button type="button">Show All</button>
          </div>
        </div>
      )}
    </aside>
  );
}

function Inspector({
  selectedNode,
  selectedEdge,
  allNodes,
  allEdges,
}: {
  selectedNode: Node | null;
  selectedEdge: Edge | null;
  allNodes: Node[];
  allEdges: Edge[];
}) {
  const nodeLookup = useMemo(() => new Map(allNodes.map((node) => [node.id, node])), [allNodes]);

  if (!selectedNode && !selectedEdge) {
    return (
      <aside className="inspector empty-state">
        <div className="panel-title">INSPECT</div>
        <p>Select a node or relationship to inspect impact, evidence and risk.</p>
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
          <div>{sourceNode?.data?.label ?? selectedEdge.source}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Target</div>
          <div>{targetNode?.data?.label ?? selectedEdge.target}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Confidence</div>
          <div>{selectedEdge.data?.confidence || 'confirmed'}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Description</div>
          <div>{selectedEdge.data?.description || 'No description available.'}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Evidence</div>
          {(evidence.length ? evidence : [{ description: 'No direct evidence available.' }]).map((item: any, index: number) => (
            <div key={`${item.description}-${index}`} className="evidence-row">
              <span className="evidence-pill">{(item.evidence_type || item.evidenceType || 'DIRECT').toUpperCase()}</span>
              <div>{item.description || 'Evidence unavailable.'}</div>
            </div>
          ))}
        </div>
      </aside>
    );
  }

  const metadata = selectedNode?.data?.metadata ?? {};
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

  return (
    <aside className="inspector">
      <div className="panel-title">{(selectedNode?.data?.nodeType || 'ARTIFACT').toUpperCase()}</div>
      <div className="inspector-section">
        <div className="field-label">Label</div>
        <div>{selectedNode?.data?.label || selectedNode?.id}</div>
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
      <div className="inspector-section">
        <div className="field-label">Evidence</div>
        {(evidence.length ? evidence : [{ description: 'No evidence attached.' }]).map((item: any, index: number) => (
          <div key={`${item.description}-${index}`} className="evidence-row">
            <span className="evidence-pill">{(item.evidence_type || item.evidenceType || 'DIRECT').toUpperCase()}</span>
            <div>{item.description || 'Evidence unavailable.'}</div>
          </div>
        ))}
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
          <div className="legend-title">RELATIONSHIPS</div>
          <div className="legend-items compact">
            {['modifies', 'impacts', 'tested_by', 'depends_on', 'documented_by', 'historically_changed_with', 'has_risk'].map((rel) => (
              <span key={rel} className="legend-pill">{rel}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function App({ graph, error }: AppProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [riskFocus, setRiskFocus] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState<NodeTypeFilter>('all');
  const [relationshipFilter, setRelationshipFilter] = useState<string>('all');
  const [focusedNodeIds, setFocusedNodeIds] = useState<string[]>([]);
  const [focusedEdgeIds, setFocusedEdgeIds] = useState<string[]>([]);
  const [statusMessage, setStatusMessage] = useState<string | null>('Change impact map loaded');
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => getGraphLayout(graph), [graph]);
  const [nodes, setNodes] = useState<Node[]>(initialNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);
  const [flowReady, setFlowReady] = useState(false);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId) ?? null;

  const applyVisualState = useCallback(() => {
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

    const relatedEdgeSet = new Set<string>();
    if (selectedNodeId) {
      initialEdges.forEach((edge) => {
        if (edge.source === selectedNodeId || edge.target === selectedNodeId) {
          relatedEdgeSet.add(edge.id ?? `${edge.source}-${edge.target}-${edge.relationship ?? 'related'}`);
        }
      });
    }
    focusedEdgeIds.forEach((id) => relatedEdgeSet.add(id));

    const searchText = searchTerm.trim().toLowerCase();
    const nodeMatchSet = new Set<string>();
    const edgeMatchSet = new Set<string>();
    if (searchText) {
      initialNodes.forEach((node) => {
        const candidate = [node.data?.label, node.data?.nodeType, node.data?.description, node.data?.metadata?.path, node.data?.metadata?.artifact_kind]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (candidate.includes(searchText)) nodeMatchSet.add(node.id);
      });
      initialEdges.forEach((edge) => {
        const candidate = [edge.data?.relationship, edge.data?.description, edge.data?.confidence, edge.source, edge.target]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (candidate.includes(searchText)) edgeMatchSet.add(edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`);
      });
    }

    setNodes(
      initialNodes.map((node) => {
        const nodeType = String(node.data?.nodeType ?? 'other');
        const isVisible = typeFilter === 'all' || nodeType === typeFilter;
        const isSelected = node.id === selectedNodeId;
        const isRelated = activeNodeSet.has(node.id);
        const isMatched = !searchText || nodeMatchSet.has(node.id);
        const isRisk = nodeType === 'risk';
        const shouldDim = selectedNodeId ? !isSelected && !isRelated && !isMatched && !isRisk : !isMatched && !isRisk && !!searchText;
        const shouldFilterDim = typeFilter !== 'all' && !isVisible && !isSelected;
        const opacity = shouldFilterDim || shouldDim ? 0.16 : isSelected || isRelated || isRisk || !searchText ? 1 : 0.72;
        const borderColor = isSelected ? '#f8fafc' : isRelated ? '#60a5fa' : isRisk ? '#f87171' : undefined;
        const boxShadow = isSelected ? '0 0 0 2px rgba(96,165,250,.5)' : isRelated ? '0 0 0 1px rgba(96,165,250,.4)' : 'none';
        return {
          ...node,
          style: {
            ...node.style,
            opacity,
            borderColor,
            boxShadow,
          },
        };
      }),
    );

    setEdges(
      initialEdges.map((edge) => {
        const edgeId = edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`;
        const relationship = String(edge.data?.relationship ?? 'related_to');
        const isSelected = edgeId === selectedEdgeId;
        const isRelated = selectedNodeId ? edge.source === selectedNodeId || edge.target === selectedNodeId : false;
        const isVisible = relationshipFilter === 'all' || relationship === relationshipFilter;
        const isMatched = !searchText || edgeMatchSet.has(edgeId);
        const isRiskEdge = relationship === 'has_risk' || relationship === 'risk_for';
        const dim = !isVisible || (!isSelected && !isRelated && !isMatched && !!searchText && !riskFocus);
        const opacity = dim ? 0.2 : isSelected || isRelated || isRiskEdge || riskFocus ? 1 : 0.72;
        const stroke = relationshipStyles[relationship]?.color ?? '#a5b4fc';
        return {
          ...edge,
          style: { stroke, strokeWidth: isSelected ? 3.5 : isRiskEdge ? 3 : 2, opacity },
          animated: isSelected || (riskFocus && isRiskEdge),
          label: isVisible ? relationshipStyles[relationship]?.label ?? relationship : '',
        };
      }),
    );
  }, [focusedEdgeIds, focusedNodeIds, initialEdges, initialNodes, relationshipFilter, riskFocus, searchTerm, selectedEdgeId, selectedNodeId, typeFilter]);

  const handleFit = useCallback(() => {
    if (!flowReady) return;
    const flow = (window as any).__DEVFLOW_INSTANCE__;
    if (!flow) return;
    const focusedNodes = selectedNodeId
      ? initialNodes.filter((node) => node.id === selectedNodeId || focusedNodeIds.includes(node.id))
      : initialNodes;
    const padding = graph.nodes.length > 100 ? 0.18 : 0.22;
    flow.fitView({ padding, duration: 220, nodes: focusedNodes.length ? focusedNodes : undefined });
  }, [flowReady, focusedNodeIds, graph.nodes.length, initialNodes, selectedNodeId]);

  useEffect(() => {
    applyVisualState();
  }, [applyVisualState]);

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
    setEdges(initialEdges);
    setTimeout(() => handleFit(), 0);
  }, [handleFit, initialEdges, initialNodes]);

  const handleFocusRisks = useCallback(() => {
    const riskIds = new Set(initialNodes.filter((node) => node.data?.nodeType === 'risk').map((node) => node.id));
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
  }, [handleFit, initialEdges, initialNodes]);

  const handleExploreConnections = useCallback(() => {
    if (!selectedNodeId) {
      setStatusMessage('Select a node to explore its neighborhood.');
      return;
    }

    const neighborIds = new Set<string>();
    const neighborEdgeIds = new Set<string>();
    initialEdges.forEach((edge) => {
      if (edge.source === selectedNodeId || edge.target === selectedNodeId) {
        neighborIds.add(edge.source);
        neighborIds.add(edge.target);
        neighborEdgeIds.add(edge.id ?? `${edge.source}-${edge.target}-${edge.data?.relationship ?? 'related'}`);
      }
    });
    setFocusedNodeIds(Array.from(neighborIds));
    setFocusedEdgeIds(Array.from(neighborEdgeIds));
    setStatusMessage('Exploring local neighborhood');
    setTimeout(() => handleFit(), 0);
  }, [handleFit, initialEdges, selectedNodeId]);

  const focusSelectedNode = useCallback(() => {
    if (!selectedNodeId) return;
    setStatusMessage('Focused on selected node');
    setTimeout(() => handleFit(), 0);
  }, [handleFit, selectedNodeId]);

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
      const padding = graph.nodes.length > 100 ? 0.18 : 0.24;
      instance.fitView({ padding, duration: 180 });
    },
    [graph.nodes.length],
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
        <AnalysisOverview graph={graph} error={error} />
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
      <AnalysisOverview graph={graph} error={error} />
      <div className="graph-panel">
        <div className="toolbar toolbar-advanced">
          <div className="toolbar-search-box">
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search nodes, paths, relationships..."
              aria-label="Search graph"
            />
          </div>
          <div className="toolbar-actions">
            <button type="button" onClick={focusSelectedNode} disabled={!selectedNodeId}>Focus Node</button>
            <button type="button" onClick={handleExploreConnections} disabled={!selectedNodeId}>Explore Connections</button>
            <button type="button" onClick={handleFit}>Fit</button>
            <button type="button" onClick={resetGraph}>Reset</button>
            <button type="button" onClick={handleFocusRisks}>Focus Risks</button>
            <button type="button" onClick={resetGraph}>Show All</button>
          </div>
          <div className="toolbar-filter-group">
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
          <div className="toolbar-relationship-filter">
            <select value={relationshipFilter} onChange={(event) => setRelationshipFilter(event.target.value)} aria-label="Relationship filter">
              <option value="all">All relationships</option>
              {Object.keys(relationshipStyles).map((key) => (
                <option key={key} value={key}>{key}</option>
              ))}
            </select>
          </div>
        </div>
        {statusMessage ? <div className="graph-status">{statusMessage}</div> : null}
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={onNodeClick}
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
          </ReactFlow>
        </ReactFlowProvider>
        <Legend />
      </div>
      <Inspector selectedNode={selectedNode} selectedEdge={selectedEdge} allNodes={initialNodes} allEdges={initialEdges} />
    </div>
  );
}

export default function AppRoot({ graph, error }: AppProps) {
  return <App graph={graph} error={error} />;
}
