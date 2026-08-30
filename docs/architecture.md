# Architecture

This describes the actual current implementation, not aspirational design.
Package paths refer to `src/devflow/` unless noted.

## Pipeline

```
Developer Change (repo URL + description)
        |
        v
Repository Ingestion            context/retriever.py, context/inspector.py
        |
        v
Context Reconstruction          context/_build.py, context/relevance.py
        |                       + knowledge_graph.py (AST import parsing)
        |                         -> Repository Knowledge Graph
        v
Historical Context               history/_build.py, history/git_log.py
        |
        v
Impact Analysis                  impact/_build.py
        |                       <- graph_index.py (import/dependent lookups
        |                          over the Repository Knowledge Graph)
        v
Risk Analysis                    risk/_build.py
        |
        v
Change Impact Map                map/_build.py, map/_ids.py
        |
        v
Developer Report                 report/_build.py
        |                       <- watsonx/_judge.py (finding ranking)
        v
===== HUMAN DECISION =====        devflow resolve <finding_id>
        |
        v
Resolution Request               resolution/_build.py: create_resolution_request
        |
===== HUMAN GATE 1 (investigate) =====
        |
        v
IBM Bob (external, developer-run)  resolution/_prompt.py generates bob_prompt.md;
        |                          Bob's `resolver` custom mode runs outside DevFlow
        v
Proposed Fix                      resolution/_ingest.py: parse_proposed_fix
        |
===== HUMAN GATE 2 (apply) =====
        |
        v
Bob implements (external)
        |
        v
Validation                        resolution/_build.py: run_validation
        |                          - real test command via subprocess
        |                          - real `git diff --name-only`
        |                          - reconciled against Bob's claimed status
        v
Updated Finding / Final Status     devflow status, devflow explain
```

## Two Graphs, Deliberately Separate

**Repository Knowledge Graph** (`knowledge_graph.py`, `models/repository_graph.py`)
answers "what exists in this codebase?" — files, classification, and real
static import edges parsed via Python's `ast` module. It is an
orientation/exploration structure, surfaced in the frontend's repository
graph view.

**Change Impact Map** (`map/_build.py`, `models/graph.py`) answers "what does
this change affect, and what could go wrong?" — the primary product output,
built from impact and risk findings.

They are not merged. `graph_index.py` is the read-only adapter between them:
it exposes fast lookups (imports, dependents, transitive blast radius, test
association) over the Repository Knowledge Graph so `impact/_build.py` and
`risk/_build.py` can reason over real import edges instead of filename-token
overlap alone. It never mutates the knowledge graph and never writes into the
Change Impact Map directly.

## What Belongs to Whom

### DevFlow (deterministic Python)

- Repository cloning, walking, and file classification
  (`context/retriever.py`, `context/inspector.py`)
- Relevance selection from the change description (`context/relevance.py`)
- Static import-graph construction (`knowledge_graph.py`)
- Git history (`history/git_log.py`)
- Impact and risk findings, each carrying typed evidence
  (`impact/_build.py`, `risk/_build.py`, `models/impact.py`, `models/risk.py`)
- Change Impact Map and Developer Report synthesis (`map/`, `report/`)
- The two-gate approval state machine, prompt generation, Bob-output
  ingestion, and validation (`resolution/`)
- Real test execution and `git diff` during validation — never simulated
- Terminal presentation (`render.py`) and CLI (`cli.py`,
  `resolution/cli.py`, `explain.py`, `status.py`)
- Local HTTP server bridging generated JSON to the frontend (`server.py`)

### IBM Bob

- Investigation of an approved finding, using the `resolver` custom mode
  (`.bob/custom_modes.yaml`) and four skills (`.bob/skills/`)
- Proposing a minimal fix (structured markdown, parsed by
  `resolution/_ingest.py`)
- Implementing the approved fix and adding/updating tests, run by the
  developer in their own editor against their own local checkout — not
  invoked programmatically by this codebase

### Human

- Selecting which finding to resolve (`devflow resolve`)
- Approving or rejecting investigation (gate 1)
- Approving or rejecting applying Bob's proposed fix (gate 2)
- Supplying the real local checkout path and test command for validation

### watsonx

- **Implemented:** watsonx.ai / Granite finding-ranking judge
  (`watsonx/_client.py`, `watsonx/_judge.py`), wired into
  `report/_build.py`. Receives only structured finding metadata, returns a
  ranking with per-finding rationale, and falls back to deterministic
  ordering on any failure. See `docs/IBM_USAGE.md` for the full bounded-
  authority contract.
- **Not implemented:** watsonx Orchestrate. DevFlow's orchestration is the
  deterministic pipeline above plus the two human gates; no workflow engine
  is used.

## Models

Structured data types live under `models/`: `change.py`, `context.py`,
`history.py`, `impact.py`, `risk.py`, `graph.py`, `repository.py`,
`repository_graph.py`, `report.py`, `prioritization.py` (watsonx ranking
types), and `resolution.py` (Phase 8 request/gate/outcome types).

## Frontend

`frontend/src/App.tsx` is the main graph exploration UI (React + TypeScript +
Vite, `@xyflow/react` + `@dagrejs/dagre` for layout). It reads the generated
`frontend/public/devflow-graph.json`, `devflow-repo-graph.json`, and
`devflow-report.json` payloads. `ReportPanel.tsx` presents the Developer
Report; `insights.tsx` adds inspector/finding-detail presentation. The
frontend is an optional exploration surface; the CLI is the primary product
interface (see `README.md`).

## Not Yet Implemented / Deferred

- No programmatic Bob API — by design; see `docs/IBM_USAGE.md`.
- No batch resolution across multiple findings in one session.
- No automatic re-run of Phases 4-7 after a resolution is validated; the
  Developer Report is not regenerated to reflect a fixed finding.
- No HTTP endpoints for the resolution workflow — it is CLI-driven only.
- Import parsing (`knowledge_graph.py`) is implemented for Python; other
  languages fall back to structural evidence without import-graph edges.
