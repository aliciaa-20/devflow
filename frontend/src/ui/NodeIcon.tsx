/**
 * Small hand-rolled line icons for graph node types.
 *
 * Deliberately not an icon-library dependency: the vocabulary is small
 * (~11 kinds) and both graphs (Change Impact Map + Repository Knowledge
 * Graph) use slightly different type strings for the same concept, so the
 * mapping lives here once and both `App.tsx` and `RepoGraphView.tsx` (via
 * the shared `ArtifactNode`) get it for free.
 */

const COLORS: Record<string, string> = {
  change: '#a78bfa',
  source: '#60a5fa',
  test: '#34d399',
  documentation: '#fbbf24',
  dependency: '#f472b6',
  configuration: '#a78bfa',
  historical: '#f59e0b',
  risk: '#ef4444',
  directory: '#7c93b8',
  repository: '#8b5cf6',
  entrypoint: '#22d3ee',
  other: '#94a3b8',
};

function normalizeType(raw?: string): keyof typeof COLORS {
  const t = (raw ?? '').toLowerCase();
  if (t === 'source' || t === 'source_file') return 'source';
  if (t === 'test' || t === 'test_file') return 'test';
  if (t === 'documentation' || t === 'documentation_file') return 'documentation';
  if (t === 'dependency' || t === 'dependency_manifest' || t === 'external_dependency') return 'dependency';
  if (t === 'configuration' || t === 'configuration_file') return 'configuration';
  if (t === 'historical') return 'historical';
  if (t === 'risk') return 'risk';
  if (t === 'change') return 'change';
  if (t === 'directory') return 'directory';
  if (t === 'repository') return 'repository';
  if (t === 'entry_point') return 'entrypoint';
  return 'other';
}

const PATHS: Record<keyof typeof COLORS, JSX.Element> = {
  change: (
    <>
      <circle cx="12" cy="12" r="3" />
      <line x1="3" y1="12" x2="8.2" y2="12" />
      <line x1="15.8" y1="12" x2="21" y2="12" />
    </>
  ),
  source: (
    <>
      <polyline points="9 6 3.5 12 9 18" />
      <polyline points="15 6 20.5 12 15 18" />
    </>
  ),
  test: (
    <>
      <circle cx="12" cy="12" r="9" />
      <polyline points="7.7 12.3 10.5 15 16.3 9" />
    </>
  ),
  documentation: (
    <>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <line x1="8" y1="8" x2="16" y2="8" />
      <line x1="8" y1="12" x2="16" y2="12" />
      <line x1="8" y1="16" x2="12.5" y2="16" />
    </>
  ),
  dependency: (
    <>
      <path d="M12 3 3.8 7.5 12 12l8.2-4.5Z" />
      <path d="M3.8 7.5v9L12 21l8.2-4.5v-9" />
      <line x1="12" y1="12" x2="12" y2="21" />
    </>
  ),
  configuration: (
    <>
      <circle cx="12" cy="12" r="3.1" />
      <path d="M12 3.6v2.3M12 18.1v2.3M4.9 6.9l1.9 1.3M17.2 15.8l1.9 1.3M3.6 12h2.3M18.1 12h2.3M6.8 17.2l-1.9 1.9M17.2 6.8l1.9-1.9" />
    </>
  ),
  historical: (
    <>
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.3 13.8" />
    </>
  ),
  risk: (
    <>
      <path d="M12 3 22 20H2Z" />
      <line x1="12" y1="9.5" x2="12" y2="14" />
      <line x1="12" y1="16.6" x2="12" y2="16.7" />
    </>
  ),
  directory: <path d="M3.5 6.2a1.7 1.7 0 0 1 1.7-1.7h3.4l1.7 1.7h8.2a1.7 1.7 0 0 1 1.7 1.7v8.1a1.7 1.7 0 0 1-1.7 1.7H5.2a1.7 1.7 0 0 1-1.7-1.7Z" />,
  repository: (
    <>
      <path d="M3.5 6.2a1.7 1.7 0 0 1 1.7-1.7h3.4l1.7 1.7h8.2a1.7 1.7 0 0 1 1.7 1.7v8.1a1.7 1.7 0 0 1-1.7 1.7H5.2a1.7 1.7 0 0 1-1.7-1.7Z" />
      <circle cx="12" cy="11.5" r="1.7" />
    </>
  ),
  entrypoint: (
    <>
      <circle cx="12" cy="12" r="9" />
      <polygon points="10 8 16.5 12 10 16" />
    </>
  ),
  other: <path d="M6.5 2.5h7l4 4v14.5h-11Z" />,
};

export default function NodeIcon({ type, className }: { type?: string; className?: string }) {
  const kind = normalizeType(type);
  const color = kind === 'risk' ? undefined : COLORS[kind];
  return (
    <svg
      className={`node-icon${className ? ` ${className}` : ''}`}
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color ?? 'currentColor'}
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[kind]}
    </svg>
  );
}
