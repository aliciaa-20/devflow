import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import App, { type GraphData } from './App';
import './index.css';
import '@xyflow/react/dist/style.css';

const emptyGraph: GraphData = {
  nodes: [],
  edges: [],
};

function Boot() {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    fetch('/devflow-graph.json')
      .then((response) => {
        if (!response.ok) {
          throw new Error('NO ANALYSIS LOADED');
        }
        return response.json() as Promise<GraphData>;
      })
      .then((payload) => {
        if (!active) return;
        setGraph(payload);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setGraph(emptyGraph);
        setError(err instanceof Error ? err.message : 'NO ANALYSIS LOADED');
      });

    return () => {
      active = false;
    };
  }, []);

  return <App graph={graph ?? emptyGraph} error={error ?? undefined} />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Boot />
  </React.StrictMode>,
);
