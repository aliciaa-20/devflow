import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import App, { type GraphData } from './App';
import RepoGraphView, { type RepoGraphData } from './RepoGraphView';
import { type ReportData } from './ReportPanel';
import './index.css';
import '@xyflow/react/dist/style.css';

const emptyGraph: GraphData = {
  nodes: [],
  edges: [],
};

const emptyReport: ReportData = {
  findings: [],
  next_actions: [],
  evidence_gaps: [],
};

const emptyRepoGraph: RepoGraphData = {
  nodes: [],
  edges: [],
};

type View = 'change' | 'repo';

function LoadingScreen() {
  return (
    <div className="loading-container">
      <div className="loading-screen">
        <div className="loading-header">
          <h2>DEVFLOW</h2>
          <p className="loading-repo">Loading analysis...</p>
        </div>
        <div className="loading-stages">
          <div className="stage">Fetching Change Impact Map</div>
          <div className="stage">Fetching Repository Knowledge Graph</div>
          <div className="stage">Fetching Developer Report</div>
        </div>
        <div className="loading-spinner">
          <span className="spinner" />
        </div>
      </div>
    </div>
  );
}

function ViewTabs({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <div className="view-tabs" role="tablist" aria-label="DevFlow view">
      <button
        type="button"
        role="tab"
        aria-selected={view === 'repo'}
        className={view === 'repo' ? 'active' : ''}
        onClick={() => onChange('repo')}
      >
        Explore Repository
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={view === 'change'}
        className={view === 'change' ? 'active' : ''}
        onClick={() => onChange('change')}
      >
        Change Impact Map
      </button>
    </div>
  );
}

function TopBar({
  view,
  onChange,
  graph,
  repoGraph,
}: {
  view: View;
  onChange: (view: View) => void;
  graph: GraphData | null;
  repoGraph: RepoGraphData | null;
}) {
  const owner = graph?.owner ?? repoGraph?.owner;
  const name = graph?.name ?? repoGraph?.name;
  const repoLabel = owner || name ? `${owner || 'repository'}/${name || 'project'}` : null;

  return (
    <header className="top-bar">
      <div className="brand"><span className="brand-mark" /> DEVFLOW</div>
      <div className="top-bar-context">
        {repoLabel ? <span className="top-bar-repo">{repoLabel}</span> : null}
        {graph?.change_summary ? (
          <>
            {repoLabel ? <span className="top-bar-sep">&middot;</span> : null}
            <span className="top-bar-change" title={graph.change_summary}>{graph.change_summary}</span>
          </>
        ) : null}
      </div>
      <ViewTabs view={view} onChange={onChange} />
    </header>
  );
}

function Boot() {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [report, setReport] = useState<ReportData | null>(null);
  const [repoGraph, setRepoGraph] = useState<RepoGraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>('change');

  useEffect(() => {
    let active = true;

    Promise.all([
      fetch('/devflow-graph.json').then((response) => {
        if (!response.ok) {
          throw new Error('NO ANALYSIS LOADED');
        }
        return response.json() as Promise<GraphData>;
      }),
      fetch('/devflow-report.json')
        .then((response) => (response.ok ? (response.json() as Promise<ReportData>) : emptyReport))
        .catch(() => emptyReport),
      fetch('/devflow-repo-graph.json')
        .then((response) => (response.ok ? (response.json() as Promise<RepoGraphData>) : emptyRepoGraph))
        .catch(() => emptyRepoGraph),
    ])
      .then(([graphPayload, reportPayload, repoGraphPayload]) => {
        if (!active) return;
        setGraph(graphPayload);
        setReport(reportPayload);
        setRepoGraph(repoGraphPayload);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setGraph(emptyGraph);
        setReport(emptyReport);
        setRepoGraph(emptyRepoGraph);
        setError(err instanceof Error ? err.message : 'NO ANALYSIS LOADED');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <LoadingScreen />;
  }

  return (
    <div className="devflow-root">
      <TopBar view={view} onChange={setView} graph={graph} repoGraph={repoGraph} />
      {/* Both views stay mounted (hidden via CSS, not unmounted) so each
          keeps its own search/filter/selection/drag state across tab
          switches within this session. */}
      <div className="view-pane" hidden={view !== 'repo'}>
        <RepoGraphView graph={repoGraph ?? emptyRepoGraph} active={view === 'repo'} />
      </div>
      <div className="view-pane" hidden={view !== 'change'}>
        <App graph={graph ?? emptyGraph} report={report ?? emptyReport} error={error ?? undefined} active={view === 'change'} />
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Boot />
  </React.StrictMode>,
);
