# DevFlow

**From unfamiliar code to confident change.**

DevFlow is a context-aware code review and change-impact assistant for
developers working in unfamiliar or evolving repositories.

> Built for the IBM TechXchange 2026 Pre-conference Dev Day Hackathon.

## The Problem

Before making or reviewing a change in a codebase you don't know, you have to
reconstruct context by hand: which files matter, what imports what, which
tests cover it, what the history says, what might break. That work is slow,
fragmented, and easy to get wrong. Most AI review tools compress this into an
unverifiable opinion — a model reads a diff and tells you what it thinks,
with no way to check its reasoning against the actual repository.

## The Solution

DevFlow reconstructs that context from the repository itself and turns it
into an evidence-backed **Change Impact Map**, a prioritized **Developer
Report**, and a human-gated resolution workflow. Full detail:
[`docs/PROBLEM_SOLUTION.md`](docs/PROBLEM_SOLUTION.md).

```bash
pip install -e ".[dev]"

devflow analyze https://github.com/pallets/flask "Refactor request context handling."
devflow findings --top 5
devflow explain risk:0:code
```

No IBM credentials required to run — prioritization falls back to
deterministic ordering and says so.

## Why DevFlow is Different

Three properties are enforced in code, not by prompt wording:

1. **Every repository fact is deterministic.** File classification, import
   edges, test associations, git history, and test execution are computed by
   Python. No language model writes into any of them.
2. **The model's authority is bounded.** IBM watsonx.ai ranks findings
   DevFlow already produced. It cannot add one, remove one, or change a
   severity.
3. **The tool can contradict the agent.** When IBM Bob reports `RESOLVED`,
   DevFlow runs the tests itself and reports the real exit code. Both the
   claim and the verified result are recorded.

## How It Works

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

Full architecture, module-by-module: [`docs/architecture.md`](docs/architecture.md).

## Change Impact Map

Answers *what does my change affect, and what could go wrong?* — the primary
product output, distinct from the Repository Knowledge Graph (*what exists in
this codebase?*). They are not merged; the knowledge graph supplies
structural evidence to impact analysis, it does not become it.

Every finding is labelled by how firmly the repository supports it:

| Label | Meaning | Example |
|---|---|---|
| `DIRECT_EVIDENCE` | Parsed from the repository | an `import` statement, a git commit |
| `DERIVED_RELATIONSHIP` | Structurally inferred | a test filename mirroring a module name |
| `INFERENCE` | Interpretation | "changing this may affect its callers" |

DevFlow never fabricates commits, issues, pull requests, tests, test results,
dependencies, relationships, or security findings. When evidence is
unavailable, it says so.

```bash
devflow explain risk:0:code
```

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

EVIDENCE
  key: * observed fact | o derived | ? interpretation

  *  observed fact
      21 file(s) reach 'src/flask/ctx.py' through static import edges parsed
      from repository source.

TEST COVERAGE
  covered  tests/test_appctx.py
  covered  tests/test_reqctx.py
```

## Finding Resolution

A developer selects one finding and DevFlow gates the rest of the workflow
behind two explicit human approvals:

| Command | Purpose |
|---|---|
| `devflow resolve <finding-id>` | Open a resolution — **human gate 1** |
| `devflow apply <resolution-id> <bob-output.md>` | Ingest Bob's proposal — **human gate 2** |
| `devflow validate <resolution-id> ...` | Run the tests yourself, verify the claim |
| `devflow status` | Where the change stands: gates, verification, resolved vs remaining |

Bob's investigation and code changes happen outside this process, in the
developer's own editor; DevFlow's job is the two gates, deterministic
ingestion of Bob's structured markdown output, and running the one thing it
can verify for real — the actual test command and a real `git diff` — rather
than trusting a claimed outcome.

## IBM Bob

Bob enters at resolution, not analysis. Approving a finding generates
`bob_sessions/<id>/bob_prompt.md` from the finding's own evidence, so the
developer never has to restate the problem. Using the `resolver` custom mode
in `.bob/custom_modes.yaml`, Bob investigates via the four skills in
`.bob/skills/`, proposes a focused fix, and implements it only after a second
human approval. Bob also writes and updates tests.

Bob task-session evidence lives in `bob_sessions/`. There is no programmatic
Bob API in this codebase — Bob is invoked by the developer, in their own
session, against their own local checkout. Full accounting of what Bob
actually did in development and what evidence exists:
[`docs/IBM_USAGE.md`](docs/IBM_USAGE.md).

## IBM watsonx

**IBM watsonx.ai / Granite** — implemented and live. DevFlow can produce
dozens of evidence-backed findings; severity alone doesn't answer "which do I
investigate first, and why?" watsonx.ai receives only DevFlow's structured
findings (ids, categories, severities, evidence types/counts, affected
artifacts) — never source code — and returns a ranking with a one-sentence
rationale each. Its authority is bounded structurally:

| Guarantee | Mechanism |
|---|---|
| Cannot invent a finding | Returned ids must be a subset of DevFlow's; unknown ids are discarded **and recorded** |
| Cannot hide a finding | Omissions are appended in deterministic order |
| Cannot restate a fact | Severity and title always come from DevFlow |
| Cannot be silently trusted | Every entry is labelled `watsonx` or `deterministic` |
| Cannot break the pipeline | Any failure falls back to deterministic ordering and reports why |
| Cannot use an out-of-scope model | The three models the hackathon guide excludes are refused |

Model: `ibm/granite-4-h-small` via the watsonx.ai chat endpoint (Dallas).

**watsonx Orchestrate — not implemented.** DevFlow's orchestration is a
deterministic pipeline plus two human gates; see
[`docs/IBM_USAGE.md`](docs/IBM_USAGE.md) for the reasoning.

## Validation

`devflow validate` runs the developer-specified test command and a real
`git diff` against the local checkout — never simulated. If Bob's closing
report claims `RESOLVED` or `PARTIALLY_RESOLVED` but the actual test run
fails, DevFlow overrides the recorded final status to `VALIDATION_FAILED`.
Test-count parsing is best-effort; when it can't determine a count it reports
`-1` rather than a fabricated number. See
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for what this does and does not
cover.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full pipeline,
module map, and what belongs to DevFlow vs. Bob vs. the human vs. watsonx.

## Getting Started

See [`docs/SETUP.md`](docs/SETUP.md) for the shortest working setup
(prerequisites, environment variables, frontend, Bob handoff).

## Running DevFlow

DevFlow is terminal-first. The web UI is an optional exploration surface, not
the product.

| Command | Purpose |
|---|---|
| `devflow analyze <repo-url> "<change>"` | Reconstruct context, build the map and report |
| `devflow findings [--top N] [--json]` | Findings in priority order, with rationale |
| `devflow explain <finding-id>` | Why one finding is risky: blast radius, evidence, history, coverage |
| `devflow status` | Where the change stands: gates, verification, resolved vs remaining |
| `devflow resolve <finding-id>` | Open a resolution — human gate 1 |
| `devflow apply <resolution-id> <bob-output.md>` | Ingest Bob's proposal — human gate 2 |
| `devflow validate <resolution-id> ...` | Run the tests yourself, verify the claim |

Useful flags: `--serve` (open the interactive map), `--no-watsonx` (force
deterministic prioritization), `--json` (machine-readable output).
`python -m devflow [url] "[change]"` also works.

## Repository Structure

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
docs/                 problem/solution, IBM usage, architecture, setup,
                       evaluation, limitations
```

## Evaluation

See [`docs/EVALUATION.md`](docs/EVALUATION.md) for the evaluation
methodology (no experiments have been run yet; results are marked
`[TO BE MEASURED]`).

## Limitations

See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for the full list. In
short: import-graph evidence is Python-only today, impact seeding still
starts from keyword relevance, Bob's runtime is developer-driven with no
programmatic API, and only one recorded Bob session completed the full
resolution cycle (with a placeholder validation command, not a real test
run).

## Security

Never commit IBM credentials, API keys, access tokens, or other secrets.
Configuration is read from `.env` (gitignored; see `.env.example`), and real
environment variables always take precedence over the file. Credentials are
never logged: the config loader returns variable *names* only, and a
"not configured" message names only the missing variable.

## Testing

```bash
pytest
```

Run this yourself to see the current pass count for this checkout — see
[`docs/SETUP.md`](docs/SETUP.md) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).
