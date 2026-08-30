# IBM Bob + watsonx Usage

This document describes only what actually happened and what actually exists
in this repository, based on `.bob/`, `bob_sessions/`, and the source under
`src/devflow/`.

---

## Claude-Assisted Development

Claude Code was the primary implementation agent for DevFlow. It implemented
the deterministic pipeline (repository ingestion, context reconstruction,
historical context, impact analysis, risk analysis, the Change Impact Map,
the Developer Report), the Repository Knowledge Graph and import-graph index
(`src/devflow/knowledge_graph.py`, `src/devflow/graph_index.py`), the Phase 8
Bob-resolution vertical slice (`src/devflow/resolution/`), the watsonx.ai
priority judge (`src/devflow/watsonx/`), the terminal CLI and presentation
layer (`cli.py`, `render.py`, `explain.py`, `status.py`), the frontend
exploration UI, and the project's test suite. It also debugged live
watsonx.ai TLS/endpoint issues and CLI edge cases across the session history
recorded in this repository's commits.

## IBM Bob-Assisted Development

Bob's project-specific configuration lives in `.bob/custom_modes.yaml`, which
defines three DevFlow-specific custom modes:

- **`architect`** (read-only) — plans DevFlow tasks without modifying files.
- **`investigator`** (read-only) — investigates a change across code, tests,
  docs, dependencies, and git history, producing evidence-backed context
  without modifying files.
- **`resolver`** (read, edit, command) — the mode actually used for
  resolution: investigates an approved finding, proposes a minimal fix,
  waits for explicit human approval, implements only after approval, adds or
  updates tests, and validates.

Four supporting skills exist under `.bob/skills/`: `change-context`,
`impact-analysis`, `historical-context`, and `evidence-report`. The
`resolver` mode's prompt (see `bob_sessions/*/bob_prompt.md`) directs Bob to
use these as parallel investigation perspectives before proposing a fix.

**Bob evidence in the repository:** `bob_sessions/` contains five recorded
resolution sessions:

- `res_20260829T205404Z_impact-src-flask-ctx-py-impacts` — a **complete**
  cycle: investigation approved, Bob's investigation output ingested
  (`bob_investigation.md`), a proposed fix parsed, the apply gate approved,
  Bob's closing report ingested (`bob_result.md`), and DevFlow's own
  validation run recorded (`test_run.txt`, final status `RESOLVED`). The test
  command executed for this session's validation step was
  `python3 -c "import sys; sys.exit(0)"` — a placeholder command, not a real
  project test run — so this session demonstrates the full gated workflow
  mechanically but its recorded validation is not evidence of a real bug fix
  being test-verified.
- `res_20260830T065053Z_risk-0-code`,
  `res_20260830T095403Z_risk-0-code`,
  `res_20260830T102213Z_risk-0-code` — investigation approved and
  `bob_prompt.md` generated, but no Bob investigation output was ingested
  for these sessions (status `investigation_approved`, no `outcome`).
- `res_20260830T080953Z_risk-0-code` — rejected before investigation
  (status `rejected_before_investigation`).

## IBM Bob Runtime

There is no programmatic Bob API or SDK invoked from this codebase. Bob is a
developer-driven, human-in-the-loop workflow, implemented as follows
(`src/devflow/resolution/_build.py`, `_prompt.py`, `_ingest.py`, `cli.py`):

1. A developer runs `devflow resolve <finding_id>`, selects an approved
   Developer Report finding, and explicitly approves it for investigation —
   **human gate 1**.
2. DevFlow generates `bob_sessions/<id>/bob_prompt.md` from the finding's own
   evidence (severity, affected artifacts, import-graph evidence, git
   history) — the developer never restates the problem by hand.
3. The developer runs Bob's `resolver` custom mode themselves, in their own
   editor, against their own local checkout, pointed at that prompt.
4. The developer saves Bob's "Propose the Fix" output to a file and runs
   `devflow apply` to ingest it. DevFlow parses the structured proposal and
   asks for a second explicit approval before any file may be modified —
   **human gate 2**.
5. Only after that approval does the developer let Bob implement the fix
   locally, then saves Bob's closing "Resolution Summary" to a file.
6. `devflow validate` runs the real, developer-specified test command and a
   real `git diff` against the local checkout — never simulated. If Bob's
   closing report claims `RESOLVED` or `PARTIALLY_RESOLVED` but the actual
   test run fails, DevFlow overrides the recorded final status to
   `VALIDATION_FAILED`.

**Why this is meaningful to DevFlow:** Bob is the only component with edit
authority over the target repository in the resolution workflow, and it acts
only within a scope DevFlow already proved with evidence, gated by two
explicit human decisions, and checked afterward by a real test run DevFlow
runs itself.

**Current Bob integration limitations:**

- Bob's investigation and fix implementation happen outside this process
  (in the developer's own Bob session); DevFlow cannot invoke Bob
  programmatically or capture its reasoning beyond the markdown the
  developer chooses to save.
- Ingestion of Bob's output depends on Bob following the `resolver` mode's
  requested output format; `_ingest.py` parses that structured markdown and
  the code was not stress-tested against arbitrary Bob output shapes beyond
  what is recorded in `bob_sessions/`.
- Only one of the five recorded sessions completed the full cycle through
  validation, and its test command was a placeholder rather than the
  project's real test suite.

---

## watsonx

watsonx.ai / Granite prioritization is implemented in
`src/devflow/watsonx/` (`_client.py`, `_judge.py`) and wired into
`src/devflow/report/_build.py`. It ranks the findings DevFlow's deterministic
pipeline already produced, via the `ibm/granite-4-h-small` model on the
watsonx.ai chat endpoint. It receives only structured finding metadata (ids,
categories, severities, evidence types/counts, affected artifacts) — never
source code — and returns a ranking with a one-sentence rationale per
finding, as JSON. Any returned id not in DevFlow's own finding set is
discarded; any omitted finding is appended in deterministic order; every
result entry is labelled `watsonx` or `deterministic`; and any failure
(unconfigured, offline, timeout, malformed response, out-of-scope model)
falls back to deterministic severity/evidence ordering. Configuration is via
`.env` (`DEVFLOW_WATSONX_APIKEY`, `DEVFLOW_WATSONX_PROJECT_ID`,
`DEVFLOW_WATSONX_URL`, optional `DEVFLOW_WATSONX_MODEL`/`_CACHE`/`_DISABLE`),
never hard-coded, and `.env` is gitignored.

watsonx Orchestrate is not implemented; DevFlow's orchestration is the
deterministic pipeline plus the two human approval gates described above.
