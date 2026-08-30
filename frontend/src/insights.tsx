/**
 * Shared inspection widgets: evidence, blast radius, ranking attribution.
 *
 * These mirror what `devflow explain` renders in the terminal, so the same
 * vocabulary means the same thing in both surfaces. A filled green dot is
 * something the repository proves, a blue dot is something DevFlow derived,
 * and a hollow amber ring is interpretation.
 */

import { useEffect, useMemo, useState } from 'react';

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------

export type EvidenceItem = {
  artifact?: string;
  description?: string;
  evidence_type?: string;
  evidenceType?: string;
  confidence?: string;
};

const EVIDENCE_KIND: Record<string, { cls: string; label: string }> = {
  DIRECT_EVIDENCE: { cls: 'direct', label: 'observed fact' },
  DIRECT: { cls: 'direct', label: 'observed fact' },
  DIRECT_FILESYSTEM: { cls: 'direct', label: 'observed fact' },
  DIRECT_STATIC_IMPORT: { cls: 'direct', label: 'observed fact' },
  DERIVED_RELATIONSHIP: { cls: 'derived', label: 'derived relationship' },
  INFERENCE: { cls: 'inference', label: 'interpretation' },
};

function evidenceKind(raw?: string) {
  const key = String(raw ?? '').toUpperCase();
  return EVIDENCE_KIND[key] ?? { cls: 'derived', label: key ? key.toLowerCase().replace(/_/g, ' ') : 'unclassified' };
}

export function EvidenceLegend() {
  return (
    <div className="ev-legend">
      <span><i className="ev-dot direct" /> observed fact</span>
      <span><i className="ev-dot derived" /> derived</span>
      <span><i className="ev-dot inference" /> interpretation</span>
    </div>
  );
}

export function EvidenceList({ evidence }: { evidence: EvidenceItem[] }) {
  if (!evidence.length) {
    return <div className="ev-text">No evidence recorded for this item.</div>;
  }
  return (
    <>
      <EvidenceLegend />
      {evidence.map((item, index) => {
        const kind = evidenceKind(item.evidence_type ?? item.evidenceType);
        return (
          <div className="ev-row" key={`${item.description ?? 'e'}-${index}`}>
            <i className={`ev-dot ${kind.cls}`} />
            <div>
              <div className="ev-kind">{kind.label}</div>
              <div className="ev-text">{item.description || 'Evidence unavailable.'}</div>
            </div>
          </div>
        );
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Repository graph index (blast radius)
// ---------------------------------------------------------------------------

type RepoGraphPayload = {
  nodes?: Array<{ id: string; node_type?: string; path?: string; metadata?: Record<string, unknown> }>;
  edges?: Array<{ source: string; target: string; relationship?: string }>;
  error?: string | null;
};

const FILE_NODE_TYPES = new Set([
  'source_file',
  'test_file',
  'documentation_file',
  'configuration_file',
  'dependency_manifest',
  'entry_point',
  'generated_file',
  'other_file',
]);

export type RepoIndex = {
  available: boolean;
  hasFile: (path: string) => boolean;
  importedBy: (path: string) => string[];
  testsFor: (path: string) => string[];
  dependents: (path: string, maxDepth?: number) => string[];
};

const EMPTY_INDEX: RepoIndex = {
  available: false,
  hasFile: () => false,
  importedBy: () => [],
  testsFor: () => [],
  dependents: () => [],
};

function normalise(path: string) {
  return (path || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
}

function buildIndex(payload: RepoGraphPayload | null): RepoIndex {
  if (!payload || payload.error) return EMPTY_INDEX;

  const pathById = new Map<string, string>();
  for (const node of payload.nodes ?? []) {
    if (!FILE_NODE_TYPES.has(String(node.node_type))) continue;
    const raw = node.path ?? (node.metadata?.path as string | undefined) ?? node.id.split(':').slice(1).join(':');
    if (raw) pathById.set(node.id, normalise(String(raw)));
  }

  const importedBy = new Map<string, Set<string>>();
  const testedBy = new Map<string, Set<string>>();
  const add = (map: Map<string, Set<string>>, key: string, value: string) => {
    if (!map.has(key)) map.set(key, new Set());
    map.get(key)!.add(value);
  };

  for (const edge of payload.edges ?? []) {
    const source = pathById.get(edge.source);
    const target = pathById.get(edge.target);
    if (!source || !target) continue;
    if (edge.relationship === 'imports') add(importedBy, target, source);
    else if (edge.relationship === 'imported_by') add(importedBy, source, target);
    else if (edge.relationship === 'tested_by') add(testedBy, source, target);
  }

  const files = new Set(pathById.values());

  const dependents = (path: string, maxDepth = 2) => {
    const start = normalise(path);
    if (!files.has(start)) return [];
    const seen = new Set([start]);
    const out: string[] = [];
    let frontier = [start];
    for (let depth = 0; depth < maxDepth; depth += 1) {
      const next: string[] = [];
      for (const node of frontier) {
        for (const dep of importedBy.get(node) ?? []) {
          if (seen.has(dep)) continue;
          seen.add(dep);
          out.push(dep);
          next.push(dep);
        }
      }
      frontier = next;
      if (!frontier.length) break;
    }
    return out.sort();
  };

  return {
    available: files.size > 0,
    hasFile: (path) => files.has(normalise(path)),
    importedBy: (path) => Array.from(importedBy.get(normalise(path)) ?? []).sort(),
    testsFor: (path) => Array.from(testedBy.get(normalise(path)) ?? []).sort(),
    dependents,
  };
}

/** Load the Repository Knowledge Graph once and expose structural lookups. */
export function useRepoIndex(url = '/devflow-repo-graph.json'): RepoIndex {
  const [payload, setPayload] = useState<RepoGraphPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch(() => {
        // The repository graph is optional: without it the inspector simply
        // omits blast radius rather than failing.
        if (!cancelled) setPayload(null);
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return useMemo(() => buildIndex(payload), [payload]);
}

// ---------------------------------------------------------------------------
// Blast radius
// ---------------------------------------------------------------------------

const MAX_TREE_CHILDREN = 6;

export function BlastRadius({ path, index }: { path: string; index: RepoIndex }) {
  const direct = useMemo(() => new Set(index.importedBy(path)), [index, path]);
  const all = useMemo(() => index.dependents(path), [index, path]);

  if (!index.available || !index.hasFile(path)) return null;

  if (!all.length) {
    return (
      <div className="insp-section">
        <div className="insp-section-title">Blast radius</div>
        <div className="ev-text">
          No file in the analyzed import graph imports this. Its exposure appears locally contained.
        </div>
      </div>
    );
  }

  const shown = Array.from(direct).slice(0, MAX_TREE_CHILDREN);
  const hiddenDirect = direct.size - shown.length;

  return (
    <div className="insp-section">
      <div className="insp-section-title">Blast radius</div>
      <div className="blast-summary">
        <span className="blast-count">{all.length}</span>
        <span className="blast-label">
          file{all.length === 1 ? '' : 's'} reach it &middot; {direct.size} direct
        </span>
      </div>
      <div className="blast-tree">
        <div className="bt-root">{path}</div>
        {shown.map((child, index_) => {
          const last = index_ === shown.length - 1 && hiddenDirect === 0;
          const grandchildren = index.importedBy(child).filter((c) => c !== path).slice(0, 3);
          return (
            <div key={child}>
              <div>
                <span className="bt-glyph">{last ? '`- ' : '|- '}</span>
                {child} <span className="bt-direct">direct</span>
              </div>
              {grandchildren.map((grand, gi) => (
                <div key={grand}>
                  <span className="bt-glyph">
                    {last ? '   ' : '|  '}
                    {gi === grandchildren.length - 1 ? '`- ' : '|- '}
                  </span>
                  {grand}
                </div>
              ))}
            </div>
          );
        })}
        {hiddenDirect > 0 ? (
          <div className="bt-glyph">{`\`- ... ${hiddenDirect} more direct importer(s)`}</div>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Test coverage
// ---------------------------------------------------------------------------

export function TestCoverage({ path, index }: { path: string; index: RepoIndex }) {
  if (!index.available || !index.hasFile(path)) return null;
  const tests = index.testsFor(path);
  return (
    <div className="insp-section">
      <div className="insp-section-title">Test coverage</div>
      {tests.length ? (
        tests.map((test) => (
          <div className="ev-row" key={test}>
            <i className="ev-dot direct" />
            <div className="mono-path">{test}</div>
          </div>
        ))
      ) : (
        <div className="ev-text">
          No test is structurally associated with this file. Coverage may need manual confirmation.
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ranking attribution
// ---------------------------------------------------------------------------

export type Ranking = {
  finding_id: string;
  rank: number;
  rationale?: string;
  severity?: string | null;
  source?: string;
};

export function RankingNote({ ranking }: { ranking: Ranking | null }) {
  if (!ranking) return null;
  const fromWatsonx = ranking.source === 'watsonx';
  return (
    <div className="insp-section">
      <div className="insp-section-title">Priority</div>
      <dl className="insp-kv">
        <dt>rank</dt>
        <dd>#{ranking.rank}</dd>
        <dt>ranked by</dt>
        <dd>
          <span className={`chip ${fromWatsonx ? 'watsonx' : ''}`}>
            {fromWatsonx ? 'IBM watsonx.ai' : 'deterministic'}
          </span>
        </dd>
      </dl>
      {ranking.rationale ? <div className="insp-rationale">{ranking.rationale}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Resolution pathway
// ---------------------------------------------------------------------------

/**
 * Phase 8 resolution is CLI-only (`devflow.resolution request/ingest-fix/validate`
 * driven by Bob's `resolver` custom mode) -- there is no invented HTTP/API
 * bridge here, just the exact command a developer runs next, with the real
 * finding id filled in.
 */
export function ResolvePathway({ findingId }: { findingId: string }) {
  const [copied, setCopied] = useState(false);
  const command = `python -m devflow.resolution request ${findingId}`;

  return (
    <div className="insp-section">
      <div className="insp-section-title">Resolution</div>
      <div className="ev-text">Hand this finding to IBM Bob's investigation and resolution workflow.</div>
      <div className="resolve-command">
        <code>{command}</code>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard?.writeText(command).catch(() => {});
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          }}
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}

export function SeverityChip({ severity }: { severity?: string | null }) {
  if (!severity) return null;
  const key = String(severity).toLowerCase();
  return <span className={`chip ${key}`}>{key}</span>;
}
