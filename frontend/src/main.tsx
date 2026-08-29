import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import App, { type GraphData } from './App';
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

function Boot() {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [report, setReport] = useState<ReportData | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        .then((response) => (response.ok ? response.json() as Promise<ReportData> : emptyReport))
        .catch(() => emptyReport),
    ])
      .then(([graphPayload, reportPayload]) => {
        if (!active) return;
        setGraph(graphPayload);
        setReport(reportPayload);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setGraph(emptyGraph);
        setReport(emptyReport);
        setError(err instanceof Error ? err.message : 'NO ANALYSIS LOADED');
      });

    return () => {
      active = false;
    };
  }, []);

  return <App graph={graph ?? emptyGraph} report={report ?? emptyReport} error={error ?? undefined} />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Boot />
  </React.StrictMode>,
);
