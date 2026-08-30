# Setup

The shortest working path to running DevFlow locally.

## Prerequisites

- Python 3.11+
- Node.js (for the optional frontend; version not pinned in the repository —
  a current LTS release works with the `vite`/`react` versions in
  `frontend/package.json`)
- `git`

## Python Setup

```bash
pip install -e ".[dev]"
```

This installs DevFlow itself (`pyproject.toml`: no runtime third-party
dependencies) and the `devflow` console script, plus `pytest` for the `dev`
extra.

## Environment Variables

```bash
cp .env.example .env
```

DevFlow runs without any of these set — finding prioritization falls back to
deterministic severity/evidence ordering and says so. They are only needed
for live IBM watsonx.ai prioritization:

| Variable | Purpose |
|---|---|
| `DEVFLOW_WATSONX_APIKEY` | IBM Cloud API key |
| `DEVFLOW_WATSONX_PROJECT_ID` | watsonx.ai project id |
| `DEVFLOW_WATSONX_URL` | Regional endpoint (defaults to Dallas) |
| `DEVFLOW_WATSONX_MODEL` | Optional; defaults to a Granite instruct model |
| `DEVFLOW_WATSONX_CACHE` | Optional; record/replay responses for offline use |
| `DEVFLOW_WATSONX_TIMEOUT` | Optional; seconds before falling back (default 30) |
| `DEVFLOW_WATSONX_DISABLE` | Optional; set to `1` to force deterministic mode |

`.env` is gitignored and must never be committed. Never put real credential
values in any committed file.

## Running DevFlow

```bash
devflow analyze https://github.com/pallets/flask "Refactor request context handling."
devflow findings --top 5
devflow explain <finding-id>
devflow status
```

`python -m devflow <repo-url> "<change>"` is equivalent to `devflow analyze`.

Useful flags: `--serve` (open the interactive frontend map), `--no-watsonx`
(force deterministic prioritization), `--json` (machine-readable output).

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend reads the generated JSON payloads in `frontend/public/`
(`devflow-graph.json`, `devflow-repo-graph.json`, `devflow-report.json`),
which `devflow analyze` produces. `devflow analyze --serve` starts DevFlow's
own local HTTP bridge (`src/devflow/server.py`) instead of running the Vite
dev server separately.

## Existing Report / Demo Data

`frontend/public/devflow-*.json` already contain a generated analysis (from
running `devflow analyze` against the Flask repository) and can be inspected
without re-running analysis.

## Bob Handoff

1. `devflow resolve <finding_id>` — select and approve a finding for
   investigation (gate 1). This writes `bob_sessions/<id>/bob_prompt.md`.
2. Run Bob's `resolver` custom mode (`.bob/custom_modes.yaml`) yourself,
   against your own local checkout, using that prompt file as input.
3. Save Bob's "Propose the Fix" output to a file, then:
   `python -m devflow.resolution ingest-fix <resolution_id> <bob_output.md>`
   — approve applying it (gate 2).
4. Let Bob implement the fix locally, save its closing "Resolution Summary"
   to a file, then:
   `python -m devflow.resolution validate <resolution_id> --local-path <path> --result <bob_result.md> --test-command "<your test command>"`

See `docs/IBM_USAGE.md` for the full mechanism and its current limitations.

## Validation

```bash
pytest
```

Run this yourself to see the current pass count for this checkout; do not
assume a previously recorded number still holds. See `docs/LIMITATIONS.md`
for what test execution does and does not cover.
