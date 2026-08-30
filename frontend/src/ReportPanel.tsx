import { useMemo, useState } from 'react';
import { ResolvePathway } from './insights';

export type ReportEvidence = {
  artifact: string;
  description: string;
  evidence_type: string;
  confidence?: string;
};

export type ReportFinding = {
  id: string;
  category: string;
  title: string;
  description: string;
  affected_artifacts?: string[];
  relationship?: string | null;
  potential_impact?: string | null;
  severity?: string | null;
  evidence?: ReportEvidence[];
  evidence_strength?: string | null;
  is_inference?: boolean;
  recommendation?: string | null;
  graph_node_id?: string | null;
};

export type ReportAction = {
  priority: number;
  action: string;
  source_finding_id: string;
  severity: string;
  graph_node_id?: string | null;
};

export type ReportEvidenceGap = {
  description: string;
  affected_artifact?: string | null;
};

export type ReportData = {
  repository_url?: string;
  owner?: string;
  name?: string;
  change_summary?: string;
  changed_files?: string[];
  error?: string | null;
  generated_at?: string;
  sections?: {
    change?: { summary?: string; changed_files?: string[] };
    context?: { artifact_count?: number; findings?: ReportFinding[] };
    impact?: { finding_count?: number; findings?: ReportFinding[] };
    history?: { finding_count?: number; findings?: ReportFinding[] };
    risk?: { finding_count?: number; highest_severity?: string | null; findings?: ReportFinding[] };
  };
  findings?: ReportFinding[];
  next_actions?: ReportAction[];
  evidence_gaps?: ReportEvidenceGap[];
  /**
   * Attached after report synthesis. `source` records whether the ordering came
   * from IBM watsonx.ai or from DevFlow's deterministic fallback, and
   * `discarded_finding_ids` records identifiers the model returned that DevFlow
   * does not recognise.
   */
  prioritization?: {
    source?: string;
    model_id?: string | null;
    from_cache?: boolean;
    error?: string | null;
    discarded_finding_ids?: string[];
    appended_finding_ids?: string[];
    rankings?: Array<{
      finding_id: string;
      rank: number;
      rationale?: string;
      severity?: string | null;
      title?: string | null;
      source?: string;
    }>;
  };
};

const severityClass = (severity?: string | null) => {
  const normalized = (severity || 'low').toLowerCase();
  return `severity-${normalized}`;
};

const evidenceLabel = (evidenceType?: string) => {
  const normalized = (evidenceType || '').toUpperCase();
  if (normalized.includes('DIRECT')) return 'Confirmed';
  if (normalized.includes('DERIVED')) return 'Derived';
  if (normalized.includes('INFERENCE')) return 'Inference';
  return normalized || 'Evidence';
};

const evidencePillClass = (evidenceType?: string) => {
  const label = evidenceLabel(evidenceType).toLowerCase();
  if (label === 'confirmed') return 'confirmed';
  if (label === 'derived') return 'derived';
  return 'inference';
};

const formatRelationship = (value?: string | null) => (value || 'related').replace(/_/g, ' ');

const formatStrength = (value?: string | null) => (value || 'unknown').toUpperCase();

function artifactPath(finding: ReportFinding): string {
  return finding.affected_artifacts?.[0] ?? finding.title;
}

function impactExplanation(finding: ReportFinding): string {
  return finding.potential_impact || finding.description;
}

function compactHistoryLine(historyFinding?: ReportFinding): string | null {
  if (!historyFinding) return null;
  const match = historyFinding.description.match(/^(\d+ relevant commit\(s\))/);
  if (match) {
    const commitEvidence = (historyFinding.evidence ?? []).filter((item) => /:/.test(item.description));
    const latest = commitEvidence[0]?.description?.split(':')[0]?.trim();
    return latest ? `${match[1]} · latest ${latest}` : match[1];
  }
  if (!historyFinding.description) return null;
  const firstLine = historyFinding.description.split(';')[0]?.trim();
  if (!firstLine) return null;
  return firstLine.length > 72 ? `${firstLine.slice(0, 69)}…` : firstLine;
}

function collectEvidence(...groups: Array<ReportEvidence[] | undefined>): ReportEvidence[] {
  const seen = new Set<string>();
  const items: ReportEvidence[] = [];
  for (const group of groups) {
    for (const item of group ?? []) {
      const key = `${item.artifact}|${item.description}|${item.evidence_type}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push(item);
    }
  }
  return items;
}

type ReportPanelProps = {
  report: ReportData;
  onSelectGraphNode?: (nodeId: string) => void;
};

function EvidenceDetails({ items }: { items: ReportEvidence[] }) {
  if (!items.length) {
    return <div className="report-evidence-empty">No detailed evidence recorded.</div>;
  }

  return (
    <div className="report-evidence-list">
      {items.map((item, index) => (
        <div key={`${item.artifact}-${index}`} className="report-evidence-item">
          <span className={`evidence-pill ${evidencePillClass(item.evidence_type)}`}>
            {evidenceLabel(item.evidence_type)}
          </span>
          <div className="report-evidence-copy">
            <strong>{item.artifact}</strong>
            <span>{item.description}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function ImpactCard({
  finding,
  historyFinding,
  contextFinding,
  onSelectGraphNode,
}: {
  finding: ReportFinding;
  historyFinding?: ReportFinding;
  contextFinding?: ReportFinding;
  onSelectGraphNode?: (nodeId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const clickable = Boolean(finding.graph_node_id && onSelectGraphNode);
  const path = artifactPath(finding);
  const historyLine = compactHistoryLine(historyFinding);
  const evidenceItems = collectEvidence(finding.evidence, historyFinding?.evidence, contextFinding?.evidence);

  return (
    <article className="report-impact-card">
      <button
        type="button"
        className={`report-card-main ${clickable ? 'clickable' : ''}`}
        onClick={() => {
          if (finding.graph_node_id && onSelectGraphNode) {
            onSelectGraphNode(finding.graph_node_id);
          }
        }}
        disabled={!clickable}
      >
        <div className="report-card-top">
          <span className="report-artifact" title={path}>{path}</span>
          <span className="report-strength-pill">{formatStrength(finding.evidence_strength)}</span>
        </div>
        <div className="report-card-meta">
          <span className="report-meta-pill">{formatRelationship(finding.relationship)}</span>
          {finding.is_inference ? <span className="report-inference">Inference</span> : null}
        </div>
        <p className="report-card-impact">{impactExplanation(finding)}</p>
        {historyLine ? <p className="report-card-history">{historyLine}</p> : null}
      </button>
      <button
        type="button"
        className="report-expand"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? 'Hide evidence' : `View evidence (${evidenceItems.length})`}
      </button>
      {expanded ? <EvidenceDetails items={evidenceItems} /> : null}
    </article>
  );
}

function RiskCard({
  finding,
  onSelectGraphNode,
}: {
  finding: ReportFinding;
  onSelectGraphNode?: (nodeId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const clickable = Boolean(finding.graph_node_id && onSelectGraphNode);
  const evidenceItems = finding.evidence ?? [];

  return (
    <article className={`report-risk-card ${severityClass(finding.severity)}`}>
      <button
        type="button"
        className={`report-card-main ${clickable ? 'clickable' : ''}`}
        onClick={() => {
          if (finding.graph_node_id && onSelectGraphNode) {
            onSelectGraphNode(finding.graph_node_id);
          }
        }}
        disabled={!clickable}
      >
        <div className="report-card-top">
          <span className={`report-severity ${severityClass(finding.severity)}`}>
            {(finding.severity || 'risk').toUpperCase()}
          </span>
          <span className="report-meta-pill">{finding.title.replace(/ risk$/i, '')}</span>
        </div>
        <p className="report-card-impact">{finding.description}</p>
        {finding.recommendation ? (
          <p className="report-card-recommendation">{finding.recommendation}</p>
        ) : null}
        {finding.is_inference ? <span className="report-inference">Inference-based assessment</span> : null}
      </button>
      <div className="report-risk-resolve">
        <ResolvePathway findingId={finding.id} />
      </div>
      <button
        type="button"
        className="report-expand"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? 'Hide evidence' : `View evidence (${evidenceItems.length})`}
      </button>
      {expanded ? <EvidenceDetails items={evidenceItems} /> : null}
    </article>
  );
}

export default function ReportPanel({ report, onSelectGraphNode }: ReportPanelProps) {
  const [showGaps, setShowGaps] = useState(false);

  const allFindings = report.findings ?? [];
  const riskFindings = (report.sections?.risk?.findings ?? allFindings).filter((f) => f.category === 'risk');
  const impactFindings = (report.sections?.impact?.findings ?? allFindings).filter(
    (f) => f.category === 'impact' && f.relationship !== 'historically_changed_with',
  );
  const historyFindings = (report.sections?.history?.findings ?? allFindings).filter((f) => f.category === 'historical');
  const contextFindings = (report.sections?.context?.findings ?? allFindings).filter((f) => f.category === 'context');
  const nextActions = report.next_actions ?? [];
  const evidenceGaps = report.evidence_gaps ?? [];

  const historyByArtifact = useMemo(() => {
    const map = new Map<string, ReportFinding>();
    for (const finding of historyFindings) {
      const path = artifactPath(finding);
      map.set(path, finding);
    }
    return map;
  }, [historyFindings]);

  const contextByArtifact = useMemo(() => {
    const map = new Map<string, ReportFinding>();
    for (const finding of contextFindings) {
      map.set(artifactPath(finding), finding);
    }
    return map;
  }, [contextFindings]);

  return (
    <div className="report-panel">
      <div className="panel-title">DEVELOPER REPORT</div>

      {report.error ? <div className="report-error">{report.error}</div> : null}

      {report.changed_files?.length ? (
        <p className="report-summary-meta report-summary-meta-standalone">
          <span>Changed files</span>
          <span>{report.changed_files.join(', ')}</span>
        </p>
      ) : null}

      {impactFindings.length ? (
        <section className="report-section">
          <div className="report-section-title">Impact</div>
          {impactFindings.map((finding) => {
            const path = artifactPath(finding);
            return (
              <ImpactCard
                key={finding.id}
                finding={finding}
                historyFinding={historyByArtifact.get(path)}
                contextFinding={contextByArtifact.get(path)}
                onSelectGraphNode={onSelectGraphNode}
              />
            );
          })}
        </section>
      ) : null}

      <section className="report-section report-section-risks">
        <div className="report-section-title">Risks</div>
        {riskFindings.length ? (
          riskFindings.map((finding) => (
            <RiskCard key={finding.id} finding={finding} onSelectGraphNode={onSelectGraphNode} />
          ))
        ) : (
          <div className="report-empty-state">
            <strong>No significant risks identified</strong>
            <span>Risk analysis did not produce any risk findings for this change.</span>
          </div>
        )}
      </section>

      {nextActions.length ? (
        <section className="report-section">
          <div className="report-section-title">Next actions</div>
          <ol className="report-action-list">
            {nextActions.map((action) => (
              <li key={`${action.priority}-${action.source_finding_id}`}>
                <button
                  type="button"
                  className={`report-action ${severityClass(action.severity)}`}
                  onClick={() => {
                    if (action.graph_node_id && onSelectGraphNode) {
                      onSelectGraphNode(action.graph_node_id);
                    }
                  }}
                  disabled={!action.graph_node_id || !onSelectGraphNode}
                >
                  <span className="report-action-priority">{action.priority}</span>
                  <span>{action.action}</span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {evidenceGaps.length ? (
        <section className="report-section report-section-secondary">
          <button
            type="button"
            className="report-section-toggle"
            aria-expanded={showGaps}
            onClick={() => setShowGaps((value) => !value)}
          >
            Evidence notes ({evidenceGaps.length})
          </button>
          {showGaps ? (
            <div className="report-gap-list">
              {evidenceGaps.map((gap, index) => (
                <div key={`${gap.description}-${index}`} className="report-gap">
                  {gap.affected_artifact ? <strong>{gap.affected_artifact}</strong> : null}
                  <span>{gap.description}</span>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
