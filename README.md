# DevFlow

**From unfamiliar code to confident change.**

DevFlow is a context-aware code review and change-impact assistant for
developers working in unfamiliar or evolving repositories.

Before making or reviewing a change in a codebase you don't know, you have to
reconstruct context by hand: which files matter, what imports what, which tests
cover it, what the history says, what might break. That work is slow,
fragmented, and easy to get wrong.

DevFlow reconstructs that context from the repository itself and turns it into
an evidence-backed **Change Impact Map**, a prioritized **Developer Report**,
and a human-gated resolution workflow.

> Built for the IBM TechXchange 2026 Pre-conference Dev Day Hackathon.

---

## The one idea

Most AI review tools ask you to trust a model's opinion about your code.

**DevFlow doesn't tell you what an AI thinks. It shows you what your repository
proves — then lets an agent fix it under supervision, and verifies the fix
itself.**

Three things follow from that, and they are enforced in code rather than by
prompt wording:

1. **Every repository fact is deterministic.** File classification, import
   edges, test associations, git history, and test execution are computed by
   Python. No language model writes into any of them.
2. **The model's authority is bounded.** IBM watsonx.ai ranks findings DevFlow
   already produced. It cannot add one, remove one, or change a severity.
3. **The tool can contradict the agent.** When IBM Bob reports `RESOLVED`,
   DevFlow runs the tests itself and reports the real exit code. Both the claim
   and the verified result are recorded.

---

## Quick start

```bash
pip install -e ".[dev]"

devflow analyze https://github.com/pallets/flask "Refactor request context handling."
devflow findings --top 5
devflow explain risk:0:code
```

No IBM credentials required to run — prioritization falls back to deterministic
ordering and says so.

---

## The developer CLI

DevFlow is terminal-first. The web UI is an optional exploration surface, not
the product.

| Command | Purpose |
|---|---|
| `devflow analyze <repo-url> "<change>"` | Reconstruct context, build the map and report |
| `devflow findings [--top N] [--json]` | Findings in priority order, with rationale |
| `devflow explain <finding-id>` | Why one finding is risky: blast radius, evidence, history, coverage |
| `devflow status` | Where the change stands: gates, verification, resolved vs remaining |
| `devflow resolve <finding-id>` | Open a resolution — **human gate 1** |
| `devflow apply <resolution-id> <bob-output.md>` | Ingest Bob's proposal — **human gate 2** |
| `devflow validate <resolution-id> ...` | Run the tests yourself, verify the claim |

Useful flags: `--serve` (open the interactive map), `--no-watsonx` (force
deterministic prioritization), `--json` (machine-readable output).

`python -m devflow [url] "[change]"` still works.

### What `devflow explain` shows

```
-- risk:0:code -----------------------------------------------------------
  HIGH     code risk
           src/flask/ctx.py

WHY THIS MATTERS
  'src/flask/ctx.py' was identified as relevant to the requested change and
  is present in the repository's import graph. 21 file(s) depend on it
  through real import edges, so a behavioral change here is not locally
  contained. Any behavioral consequence requires review; no defect is
  established.

BLAST RADIUS
  exposure    21 file(s) reach it (5 directly)

  src/flask/ctx.py
  |- src/flask/app.py       direct import
  |  |- src/flask/cli.py
  |  `- src/flask/testing.py
  `- src/flask/globals.py   direct import
     |- src/flask/helpers.py
     `- src/flask/templating.py

EVIDENCE
  key: * observed fact | o derived | ? interpretation

  *  observed fact
      21 file(s) reach 'src/flask/ctx.py' through static import edges parsed
      from repository source.

TEST COVERAGE
  covered  tests/test_appctx.py
  covered  tests/test_reqctx.py

CONFIDENCE
  evidence strength   likely
  claim type          interpretation - not an established defect
  ranked #1 by        IBM watsonx.ai judgment
    High code risk due to wide import-proven blast radius of 21 files.
```

Every marker is meaningful: `*` is something the repository proves, `o` is
something DevFlow derived, `?` is interpretation.

---

## How it works

```text
repository + change description
        |
        v
  clone once, walk, classify
        |
        +--> AST import parsing --> Repository Knowledge Graph
        |                            (what exists)
        v
  relevance selection
        |
        v
  impact analysis  <--- real IMPORTS / IMPORTED_BY / TESTED_BY edges
        |
        v
  risk analysis    <--- severity scaled by transitive blast radius
        |
        v
  Change Impact Map + Developer Report
        |
        v
  IBM watsonx.ai ranks the findings   (bounded, verifiable)
        |
        v
  ===== HUMAN GATE 1 =====
        |
        v
  IBM Bob investigates and proposes
        |
        v
  ===== HUMAN GATE 2 =====
        |
        v
  Bob implements
        |
        v
  DevFlow runs the tests ITSELF and reconciles against Bob's claim
        |
        v
  verified outcome / remaining risks
```

### Two graphs, deliberately separate

**Repository Knowledge Graph** answers *what exists in this codebase?* — an
orientation view of structure, imports, tests, docs, and dependencies.

**Change Impact Map** answers *what does my change affect, and what could go
wrong?* — the primary output.

They are not merged. The knowledge graph supplies structural evidence to the
impact analysis; it does not become it.

---

## Evidence model

Every finding is labelled by how firmly the repository supports it.

| Label | Meaning | Example |
|---|---|---|
| `DIRECT_EVIDENCE` | Parsed from the repository | an `import` statement, a git commit |
| `DERIVED_RELATIONSHIP` | Structurally inferred | a test filename mirroring a module name |
| `INFERENCE` | Interpretation | "changing this may affect its callers" |

DevFlow never fabricates commits, issues, pull requests, tests, test results,
dependencies, relationships, or security findings. When evidence is
unavailable, it says so.

---

## IBM technology map

Each technology owns one responsibility. Nothing is included for branding.

### DevFlow (deterministic Python) — owns every fact

Cloning, classification, AST import parsing, transitive dependents, test
association, git history, impact and risk findings, the graph, the report, the
approval-gate state machine, test execution, `git diff`, and outcome
reconciliation.

### IBM Bob — owns the code change

Bob enters at resolution, not analysis. Approving a finding generates
`bob_sessions/<id>/bob_prompt.md` from the finding's own evidence, so the
developer never has to restate the problem. Using the `resolver` mode in
`.bob/custom_modes.yaml`, Bob investigates in parallel via the four skills in
`.bob/skills/`, proposes a focused fix, and implements it only after a second
human approval. Bob also writes and updates tests.

Bob task-session evidence lives in `bob_sessions/`.

### IBM watsonx.ai / Granite — owns one judgment call

**The problem.** DevFlow can produce dozens of evidence-backed findings.
Severity alone doesn't answer *"which do I investigate first, and why?"* —
comparing across categories is judgment, not computation.

**What it receives.** Only DevFlow's structured findings: ids, categories,
severities, evidence types and counts, affected artifacts. Never source code.
Never asked for a fact.

**What it returns.** A ranking with a one-sentence rationale each, as JSON.

**How its authority is bounded:**

| Guarantee | Mechanism |
|---|---|
| Cannot invent a finding | Returned ids must be a subset of DevFlow's; unknown ids are discarded **and recorded** |
| Cannot hide a finding | Omissions are appended in deterministic order |
| Cannot restate a fact | Severity and title always come from DevFlow |
| Cannot be silently trusted | Every entry is labelled `watsonx` or `deterministic` |
| Cannot break the pipeline | Any failure falls back to deterministic ordering and reports why |
| Cannot use an out-of-scope model | The three models the hackathon guide excludes are refused |

Model: `ibm/granite-4-h-small` via the watsonx.ai chat endpoint (Dallas).

### watsonx Orchestrate — deliberately not used

DevFlow's orchestration is a deterministic pipeline plus two human gates.
Repository facts must be reproducible, so moving that control flow into a
hosted workflow engine would add latency and failure modes while removing
nothing. Evaluated and rejected on that basis.

---

## Configuration

```bash
cp .env.example .env
```

| Variable | Purpose |
|---|---|
| `DEVFLOW_WATSONX_APIKEY` | IBM Cloud API key |
| `DEVFLOW_WATSONX_PROJECT_ID` | watsonx.ai project id |
| `DEVFLOW_WATSONX_URL` | Regional endpoint (Dallas by default) |
| `DEVFLOW_WATSONX_MODEL` | Optional; defaults to a Granite instruct model |
| `DEVFLOW_WATSONX_CACHE` | Optional; record/replay responses for offline demos |
| `DEVFLOW_WATSONX_DISABLE` | Optional; force deterministic prioritization |

`.env` is gitignored. Real environment variables take precedence over the file.
Credentials are never logged: the loader returns variable *names*, and the
"not configured" message names only the missing variable.

---

## Implementation status

| Phase | Area | Status |
|---|---|---|
| 0-7 | Foundation through Developer Report | Complete |
| 8 | Bob Resolution (human-gated) | Complete |
| 9 | Deterministic Validation | Complete |
| 10 | Multi-step agentic investigation | Partial — Bob modes and skills in place |
| 11 | watsonx.ai prioritization | Complete, live |
| 12-14 | Measurement, demo, submission | In progress |

### Known limitations

- Impact seeding still begins from keyword relevance; the import graph expands
  and justifies that seed but does not yet replace how it is chosen.
- Import parsing is implemented for Python; other languages fall back to
  structural evidence only.
- The web UI has not been reworked to match the CLI's presentation quality.

---

## Testing

```bash
pytest
```

443 tests pass in the current repository state. Every test runs offline: the
watsonx tests inject a fake transport, so none requires credentials or makes a
network call.

---

## Repository layout

```
src/devflow/
  input.py            repository + change validation
  context/            retrieval, inspection, relevance
  knowledge_graph.py  AST import parsing -> Repository Knowledge Graph
  graph_index.py      structural lookups (imports, dependents, blast radius)
  history/            git history
  impact/             impact findings
  risk/               risk findings
  map/                Change Impact Map
  report/             Developer Report
  watsonx/            IBM watsonx.ai priority judge
  resolution/         Phase 8 gates, Bob prompt, validation
  explain.py          devflow explain
  status.py           devflow status
  render.py           terminal presentation
  cli.py              devflow command
frontend/             React exploration UI
.bob/                 Bob custom modes and skills
bob_sessions/         Bob task-session evidence
```

---

## License

Developed as part of the DevFlow implementation.
