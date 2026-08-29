import { useCallback, useMemo, useState } from 'react';
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

const deriveNodeType = (value?: string): string => {
  const normalized = (value ?? 'other').toLowerCase();
  if (normalized in typePalette) return normalized;
  return 'other';
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
    ranksep: largeGraph ? 130 : 150,
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
    const width = typeof node.measured?.width === 'number' ? node.measured.width : estimateNodeWidth(String(node.data?.label ?? ''), String(node.data?.nodeType ?? 'artifact'));
    dagreGraph.setNode(node.id, { width, height: nodeHeight });
  });

  const edges: Edge[] = graph.edges.map((edge) => {
    const relationship = edge.relationship ?? 'related_to';
    const style = relationshipStyles[relationship] ?? {
      color: '#a5b4fc',
      label: relationship,
    };
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

function Inspector({ selectedNode, selectedEdge }: { selectedNode: any; selectedEdge: any }) {
  if (!selectedNode && !selectedEdge) {
    return (
      <aside className="inspector empty-state">
        <div className="panel-title">INSPECT</div>
        <p>Select a node or relationship to inspect impact, evidence and risk.</p>
      </aside>
    );
  }

  if (selectedEdge) {
    const evidence = selectedEdge.data?.evidence ?? [];
    return (
      <aside className="inspector">
        <div className="panel-title">RELATIONSHIP</div>
        <div className="inspector-section">
          <div className="field-label">Type</div>
          <div>{selectedEdge.data?.relationship || 'relationship'}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Source</div>
          <div>{selectedEdge.source}</div>
        </div>
        <div className="inspector-section">
          <div className="field-label">Target</div>
          <div>{selectedEdge.target}</div>
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
  const evidence = metadata.evidence ?? selectedNode?.data?.description ? [{ description: selectedNode.data.description }] : [];

  return (
    <aside className="inspector">
      <div className="panel-title">{(selectedNode.data?.nodeType || 'ARTIFACT').toUpperCase()}</div>
      <div className="inspector-section">
        <div className="field-label">Label</div>
        <div>{selectedNode.data?.label || selectedNode.id}</div>
      </div>
      <div className="inspector-section">
        <div className="field-label">Description</div>
        <div>{selectedNode.data?.description || 'No description available.'}</div>
      </div>
      {selectedNode.data?.riskSeverity ? (
        <div className="inspector-section">
          <div className="field-label">Risk</div>
          <div>{selectedNode.data.riskSeverity.toUpperCase()}</div>
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
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => getGraphLayout(graph), [graph]);
  const [nodes, setNodes] = useState<Node[]>(initialNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);
  const [flowReady, setFlowReady] = useState(false);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId) ?? null;

  const handleFit = useCallback(() => {
    if (flowReady) {
      const flow = (window as any).__DEVFLOW_INSTANCE__;
      if (flow) {
        const padding = graph.nodes.length > 100 ? 0.18 : 0.22;
        flow.fitView({ padding, duration: 220 });
      }
    }
  }, [flowReady, graph.nodes.length]);

  const resetGraph = useCallback(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setRiskFocus(false);
    setStatusMessage(null);
    handleFit();
  }, [handleFit, initialEdges, initialNodes]);

  const handleFocusRisks = useCallback(() => {
    const riskIds = new Set(
      initialNodes.filter((node) => node.data?.nodeType === 'risk').map((node) => node.id),
    );

    if (!riskIds.size) {
      setRiskFocus(false);
      setStatusMessage('No risk findings found for this change.');
      return;
    }

    setRiskFocus(true);
    setStatusMessage(null);
    const relatedIds = new Set<string>();
    initialEdges.forEach((edge) => {
      if (riskIds.has(edge.source) || riskIds.has(edge.target)) {
        relatedIds.add(edge.source);
        relatedIds.add(edge.target);
      }
    });
    setNodes((current) =>
      current.map((node) => {
        const isRisk = riskIds.has(node.id);
        const isRelated = relatedIds.has(node.id);
        const opacity = isRisk || isRelated || !selectedNodeId ? 1 : 0.2;
        return { ...node, style: { ...node.style, opacity } };
      }),
    );
    setEdges((current) =>
      current.map((edge) => {
        const shouldHighlight = riskIds.has(edge.source) || riskIds.has(edge.target);
        return {
          ...edge,
          style: { ...edge.style, opacity: shouldHighlight ? 1 : 0.25 },
          animated: shouldHighlight,
        };
      }),
    );
  }, [initialEdges, initialNodes, selectedNodeId]);

  const onNodeClick = useCallback((_event: any, node: Node) => {
    setSelectedEdgeId(null);
    setSelectedNodeId(node.id);
    setRiskFocus(false);
    setStatusMessage(null);
    setNodes((current) =>
      current.map((item) => ({
        ...item,
        style: {
          ...item.style,
          opacity: item.id === node.id || item.id === selectedNodeId ? 1 : 0.6,
        },
      })),
    );
    setEdges((current) =>
      current.map((edge) => {
        const isConnected = edge.source === node.id || edge.target === node.id;
        return {
          ...edge,
          style: { ...edge.style, opacity: isConnected ? 1 : 0.35 },
          animated: isConnected,
        };
      }),
    );
  }, [selectedNodeId]);

  const onEdgeClick = useCallback((_event: any, edge: Edge) => {
    setSelectedNodeId(null);
    setSelectedEdgeId(edge.id);
    setRiskFocus(false);
    setStatusMessage(null);
    setEdges((current) =>
      current.map((item) => ({
        ...item,
        style: {
          ...item.style,
          opacity: item.id === edge.id ? 1 : 0.4,
        },
      })),
    );
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setRiskFocus(false);
    setStatusMessage(null);
    resetGraph();
  }, [resetGraph]);

  const onInit = useCallback((instance: any) => {
    (window as any).__DEVFLOW_INSTANCE__ = instance;
    setFlowReady(true);
    const padding = graph.nodes.length > 100 ? 0.18 : 0.24;
    instance.fitView({ padding, duration: 180 });
  }, [graph.nodes.length]);

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
        <Inspector selectedNode={null} selectedEdge={null} />
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
        <Inspector selectedNode={null} selectedEdge={null} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <AnalysisOverview graph={graph} error={error} />
      <div className="graph-panel">
        <div className="toolbar">
          <button type="button" onClick={handleFit}>Fit</button>
          <button type="button" onClick={resetGraph}>Reset</button>
          <button type="button" onClick={handleFocusRisks}>Focus Risks</button>
          <button type="button" onClick={resetGraph}>Show All</button>
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
      <Inspector selectedNode={selectedNode} selectedEdge={selectedEdge} />
    </div>
  );
}

export default function AppRoot({ graph, error }: AppProps) {
  return <App graph={graph} error={error} />;
}
