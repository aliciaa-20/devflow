# Limitations

Genuine current limitations of the submitted build, based on inspection of
the repository.

## IBM Bob Runtime

- Bob is not invoked programmatically by this codebase. There is no Bob API
  or SDK call anywhere in `src/devflow/`. Bob's investigation and code
  changes happen entirely outside this process, in the developer's own
  editor/session, against their own local checkout.
- DevFlow can only ingest what the developer chooses to save from Bob's
  session (`bob_investigation.md`, `bob_result.md`) — it has no visibility
  into Bob's actual reasoning, tool calls, or intermediate steps.
- Ingestion (`resolution/_ingest.py`) depends on Bob following the
  `resolver` mode's requested output structure. It has only been exercised
  against the sessions recorded in `bob_sessions/`, not stress-tested
  against arbitrary output shapes.
- Of the five sessions recorded in `bob_sessions/`, only one completed the
  full gate-to-validation cycle, and that session's validation test command
  was a placeholder (`python3 -c "import sys; sys.exit(0)"`), not a real
  project test run. See `docs/IBM_USAGE.md` for the full accounting.

## watsonx Status

- Only watsonx.ai / Granite finding-ranking is implemented. watsonx
  Orchestrate is not used; DevFlow's orchestration is a deterministic
  pipeline plus two human approval gates.
- watsonx never sees repository source and is never asked for a fact; it can
  only reorder findings DevFlow already produced. This bounds its blast
  radius but also means it cannot surface anything DevFlow's deterministic
  analysis missed.
- Live calls require IBM Cloud credentials in `.env`; without them,
  prioritization silently falls back to deterministic ordering (by design,
  but it means a demo or evaluation run without credentials is not exercising
  the watsonx code path at all).

## Repository / Language Assumptions

- Static import-graph parsing (`knowledge_graph.py`) uses Python's `ast`
  module and is implemented for Python source only. Other languages are
  still classified and included in the Repository Knowledge Graph, but
  without import-edge evidence — impact and risk findings for non-Python
  repositories fall back to structural/keyword evidence, which is weaker.
- Impact seeding still begins from keyword relevance matching between the
  change description and file paths/contents; the import graph expands and
  justifies that seed but does not yet replace how candidate files are
  initially chosen. A change description that shares no keywords with the
  actually-affected files may be under-seeded.

## Graph / Static-Analysis Limitations

- Import edges are static (parsed from source), not dynamic — they will
  miss runtime-only relationships such as dynamic imports, reflection,
  dependency injection wiring, or plugin discovery.
- Blast radius is computed over the import graph only; it does not account
  for non-code coupling (shared database schemas, network contracts,
  configuration coupling) unless that coupling happens to be visible as a
  documented or configuration artifact DevFlow already classifies.

## Local Checkout Requirement for Validation

- `devflow validate` requires a real local checkout path and a real test
  command supplied by the developer; DevFlow does not clone or manage this
  checkout itself for the validation step, and cannot validate a resolution
  without one.

## Findings Are Not Established Defects

- Risk and impact findings, including `INFERENCE`-labelled ones, describe
  potential exposure derived from repository structure — wide blast radius,
  missing test coverage, keyword relevance — not confirmed defects. The
  Developer Report and CLI output label evidence strength explicitly, but a
  `HIGH` severity finding is a prioritization signal, not proof of a bug.

## Human Approval Requirement

- The resolution workflow requires two explicit human approvals
  (investigate, apply) and cannot proceed automatically. This is a
  deliberate safety property, not an oversight, but it does mean DevFlow
  cannot demonstrate a fully unattended resolution flow.

## Validation / Test Limitations

- DevFlow's validation step runs whatever test command the developer
  supplies; it does not independently determine which tests are relevant to
  the resolved finding, and a developer-supplied command that doesn't
  actually exercise the changed code will produce a misleadingly clean
  validation result.
- Test-count parsing (`resolution/_build.py: _parse_test_counts`) is
  best-effort regex matching against pytest/unittest summary lines; output
  from other test runners, or reformatted output, may not parse and will
  report counts of `-1` (explicitly "not determinable") rather than a
  fabricated number.
- The project's own test-suite pass count is not independently re-verified
  in this document; run `pytest` yourself per `docs/SETUP.md` rather than
  trusting a previously recorded figure.

## Frontend

- The frontend exploration UI has not been reworked to match the CLI's
  presentation quality or its evidence-labelling detail; the CLI (`devflow
  findings`, `devflow explain`, `devflow status`) is the primary,
  best-supported interface.
