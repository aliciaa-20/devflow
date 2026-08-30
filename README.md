# DevFlow

**From unfamiliar code to confident change.**

DevFlow is an agentic, context-aware code review assistant for developers working in unfamiliar or evolving codebases.

The core problem is simple: before making or reviewing a change in an unfamiliar repository, developers must manually gather context across source files, tests, documentation, dependencies, and repository history. That workflow is slow, fragmented, and easy to get wrong.

DevFlow addresses that by accepting a repository and a developer change, reconstructing relevant context, and presenting the most important relationships and risks as a structured, evidence-backed Change Impact Map.

---

## What DevFlow does

DevFlow helps a developer answer:

- What is changing?
- What else in the repository is relevant?
- What is likely affected?
- What historical or structural context matters?
- What risks are supported by evidence?

The system is intentionally repository-agnostic and does not depend on a specific codebase, language, or framework.

---

## Core workflow

1. Accept a public GitHub repository URL
2. Accept a developer change description
3. Reconstruct repository context from the repo itself
4. Gather relevant Git history when available
5. Assess likely impact from structured repository evidence
6. Identify risk findings tied to evidence
7. Produce a Change Impact Map as the primary output
8. Generate a concise Developer Report alongside the map

---

## Primary product output

### CHANGE IMPACT MAP
PRIMARY PRODUCT OUTPUT

The Change Impact Map is the main experience. It is designed to show the relationship between a proposed change and the repository artifacts, tests, dependencies, and risks relevant to that change.

### Repository Knowledge Graph
OPTIONAL REPOSITORY ORIENTATION FEATURE

A Repository Knowledge Graph is a separate concept: it helps a developer orient themselves in an unfamiliar codebase by exploring the repository structure and important artifacts. It is optional and is not the primary DevFlow output.

The current implementation builds a real Repository Knowledge Graph (file/directory structure, static import relationships, tests, documentation, configuration, and dependencies) for every analyzed repository and renders it in an "Explore Repository" tab alongside the Change Impact Map. It is a separate view with its own payload (`devflow-repo-graph.json`) and is not merged into the Change Impact Map.

---

## Current implementation status

The implementation is currently in the following state:

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Foundation | IMPLEMENTED |
| 1 | Repository + Change Input | IMPLEMENTED |
| 2 | Repository Ingestion + Context Reconstruction | IMPLEMENTED |
| 3 | Historical Context | IMPLEMENTED |
| 4 | Impact Analysis | IMPLEMENTED |
| 5 | Risk Analysis | IMPLEMENTED |
| 6 | Change Impact Map | IMPLEMENTED |
| 7 | Developer Report | IMPLEMENTED |
| 8 | Bob Resolution (human-gated vertical slice) | IMPLEMENTED |
| 9 | Deterministic Validation | IMPLEMENTED |
| 11 | watsonx.ai Finding Prioritization | IMPLEMENTED |
| 10, 12-14 | Extended agentic workflow, Measurement, Demo, Submission | IN PROGRESS |

What is currently working:

- acceptance and normalization of a public GitHub repository URL
- validation and normalization of the developer change description
- repository retrieval and temporary local inspection
- file classification and relevance selection
- structured repository context objects with evidence and reasons
- commit history extraction for relevant artifacts
- evidence-backed impact findings
- evidence-backed risk findings
- structured graph generation and HTML export for a Change Impact Map
- deterministic Developer Report synthesis with evidence, recommendations, and graph node linking
- Repository Knowledge Graph generation (structure, static imports, tests, docs, configuration, dependencies) with a dedicated "Explore Repository" interactive view
- **structural impact analysis driven by real static import edges**, so impact and risk are justified by parsed `import` statements rather than filename overlap
- **blast-radius risk severity**: how many files transitively import a changed file, counted from the import graph
- **IBM watsonx.ai / Granite finding prioritization**, constrained so the model can only reorder and explain DevFlow's own findings
- **human-gated IBM Bob resolution** with two explicit approval boundaries
- **deterministic validation** that runs the tests itself and can contradict Bob's claimed status

Current limitations:

- The extended multi-step agentic workflow (Phase 10) is not implemented.
- Measurement (Phase 12) is partial.
- Impact seeding still begins from Phase 2 keyword relevance; the import graph
  expands and justifies that seed but does not yet replace how it is chosen.

---

## How to run DevFlow

### Requirements

- Python 3.11+
- Git available on PATH for repository inspection and history retrieval

### Install

```bash
pip install -e ".[dev]"
```

### The `devflow` command

Installing the package provides a `devflow` command covering the full journey:

```bash
devflow analyze <repo-url> "<change description>"   # change     -> understand
devflow findings [--top 5] [--json]                 # understand -> prioritize
devflow resolve  <finding-id>                       # HUMAN GATE 1
devflow apply    <resolution-id> <bob-output.md>    # HUMAN GATE 2
devflow validate <resolution-id> --local-path <dir> \
    --result <bob-result.md> --test-command "<cmd>" # verify, independently
```

Worked example:

```bash
devflow analyze https://github.com/pallets/flask "Refactor request context handling."
devflow findings --top 5
devflow resolve risk:0:code
```

Add `--serve` to `analyze` to open the interactive Change Impact Map, and
`--no-watsonx` to force deterministic prioritization.

`python -m devflow [url] "[change]"` continues to work unchanged.

### Configuring IBM watsonx.ai (optional)

Copy `.env.example` to `.env` and fill in your IBM Cloud values:

```bash
cp .env.example .env
```

`.env` is gitignored and must never be committed. Real environment variables
always take precedence over the file. **Without credentials DevFlow still
runs**: prioritization falls back to deterministic severity/evidence ordering
and reports that it did so.

---

## How to provide a repository and developer change

DevFlow accepts:

- a public GitHub repository URL
- a short developer change description
- optional changed files if the developer already knows them

Example:

```python
from devflow.input import accept_input

repo, change = accept_input(
    "https://github.com/example/project",
    "Refactor authentication session handling.",
    ["src/auth/session.py", "tests/test_session.py"],
)

print(repo.owner, repo.name)
print(change.description)
```

The repository and change are normalized into structured internal models before downstream analysis.

---

## Current testing status

The current project test suite is passing.

```bash
pytest
```

Validated result:

- 407 tests passed in the current repository state

Every test runs offline. The watsonx tests inject a fake transport, so no test
requires credentials or makes a network call.

---

## High-level architecture

The implementation today follows a deterministic pipeline:

Repository Input
    |
    v
Repository Context Reconstruction
    |
    v
Historical Context
    |
    v
Impact Analysis
    |
    v
Risk Analysis
    |
    v
Change Impact Map

The structure is intentionally modular:

- src/devflow/input.py — repository/change input validation
- src/devflow/context/ — repository retrieval and relevance analysis
- src/devflow/history/ — Git-based historical context
- src/devflow/impact/ — structured impact findings
- src/devflow/risk/ — evidence-based risk findings
- src/devflow/map/ — graph construction and HTML export
- src/devflow/models/ — shared structured models

---

## IBM technology map

Each technology owns one responsibility. Nothing is included for branding.

### DevFlow (deterministic Python) — owns every fact

Cloning, file classification, AST import parsing, transitive dependents, test
association, git history, impact findings, risk findings, the graph, the
report, the approval-gate state machine, test execution, `git diff`, and
outcome reconciliation. **No language model writes into any of these.**

### IBM Bob — owns the code change

Bob enters at resolution, not analysis. Using the `resolver` custom mode in
`.bob/custom_modes.yaml`, Bob investigates an approved finding, proposes a
focused fix, and implements it after a second human approval. DevFlow owns the
gates and the verification on either side.

Bob task-session evidence is preserved under `bob_sessions/`.

### IBM watsonx.ai / Granite — owns one judgment call

**Problem it solves.** DevFlow can produce dozens of evidence-backed findings.
Severity alone does not answer *"which do I investigate first, and why?"* —
cross-category comparison is a judgment task, not a deterministic one.

**What it receives.** Only DevFlow's own structured findings: identifiers,
categories, severities, evidence types and counts, affected artifacts. It never
receives repository source code and is never asked to state a fact.

**What it returns.** A ranking of those findings with a one-sentence rationale
each, as strict JSON.

**How its authority is bounded** — enforced in code, not by prompt wording:

| Guarantee | Mechanism |
|---|---|
| Cannot invent a finding | Returned IDs must be a subset of DevFlow's; unknown IDs are discarded **and recorded** |
| Cannot hide a finding | Anything the model omits is appended in deterministic order |
| Cannot restate a fact | Severity and title are always taken from DevFlow, never from the response |
| Cannot be silently trusted | Every entry is labelled `watsonx` or `deterministic` |
| Cannot break the pipeline | Any failure falls back to deterministic ordering and says why |
| Cannot use an out-of-scope model | The three models the hackathon guide excludes are refused |

Model: `ibm/granite-4-h-small` via the watsonx.ai chat endpoint (Dallas).
Credentials come from environment variables or a gitignored `.env`.

### watsonx Orchestrate — deliberately not used

DevFlow's orchestration is a deterministic five-stage pipeline plus two human
approval gates. Repository facts must be reproducible, so moving that control
flow into a hosted workflow engine would add latency and failure modes while
removing nothing. Orchestrate was evaluated and rejected on that basis.

---

## Product direction

DevFlow is currently positioned as a focused, evidence-backed change-review assistant with a strong emphasis on:

- repository-agnostic analysis
- traceable evidence
- structured impact and risk findings
- a readable primary Change Impact Map experience

The near-term goal is to complete the developer report and human-approved resolution flow, then validate the workflow end-to-end with a concise demo.

---

## License

This project is developed as part of the DevFlow implementation.
