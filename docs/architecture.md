# DevFlow Architecture

## Overview

DevFlow is an agentic, context-aware code review assistant.

It accepts a public GitHub repository URL and a developer change description, reconstructs the relevant technical and historical context, and presents it as a visual, evidence-backed Change Impact Map.

DevFlow is repository-agnostic. It contains no hard-coded assumptions about any specific project, technology stack, or repository structure.

---

## Technology Stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| Packaging | pyproject.toml (setuptools, src layout) |
| Testing | pytest |
| Runtime dependencies | None (Phase 0) |

---

## Directory Structure

```
devflow/                        # repository root
├── pyproject.toml              # project metadata, dev dependencies, test config
├── README.md                   # quickstart and project overview
├── TASKS.md                    # development phases and acceptance criteria
├── AGENTS.md                   # agent implementation rules
│
├── src/
│   └── devflow/                # application package
│       ├── __init__.py         # package version
│       ├── __main__.py         # entry point: python -m devflow
│       ├── config.py           # environment-based configuration
│       └── pipeline/           # future pipeline stage modules
│           └── __init__.py     # stub; populated in Phase 1–9
│
├── tests/
│   ├── __init__.py
│   └── test_entry.py           # Phase 0 smoke tests
│
└── docs/
    └── architecture.md         # this document
```

---

## Conceptual Layers

The following layers map to TASKS.md phases. Only the foundation exists in Phase 0.

| Layer | Phase | Responsibility |
|-------|-------|----------------|
| Change Input | 1 | Accept repository URL + developer change description |
| Repository Ingestion | 2 | Clone or retrieve the repository; build file index |
| Context Reconstruction | 2 | Identify relevant source, tests, docs, config |
| Historical Context | 3 | Inspect Git history, commits, issues, pull requests |
| Impact Analysis | 4 | Determine what the change affects |
| Risk Analysis | 5 | Identify and prioritize risks with supporting evidence |
| Change Impact Map | 6 | Visual graph generated from structured pipeline data |
| Developer Report | 7 | Concise finding → evidence → impact → recommendation |
| Bob Resolution | 8 | Agentic fix with human approval and validation |
| Validation | 9 | Test execution and final status reporting |

---

## Configuration

Configuration is environment-based. No credentials are required in Phase 0.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEVFLOW_LOG_LEVEL` | `INFO` | Log verbosity |

Future phases will introduce optional environment variables (e.g. `DEVFLOW_GITHUB_TOKEN`) for authenticated repository access. These will always be optional for public repositories.

---

## Entry Point

```bash
python -m devflow
```

Invokes [`src/devflow/__main__.py`](../src/devflow/__main__.py) → `main()`.

---

## Evidence Principles

DevFlow distinguishes between:

- **DIRECT** — observed in repository artifacts
- **DERIVED** — reasonably inferred from multiple artifacts
- **INFERENCE** — AI interpretation not directly established by evidence
- **NOT_FOUND** — evidence could not be located

The system must not fabricate repository history, commits, issues, pull requests, relationships, or test results.

---

## Development Principles

1. Build vertically — complete and validate one phase before starting the next.
2. Repository-agnostic — no hard-coded project names, paths, or technology assumptions.
3. Evidence over assumption — prefer deterministic repository evidence.
4. Simplicity — no unnecessary dependencies, frameworks, or abstractions.
5. No credentials in source — all secrets via environment variables only.
6. Human approval required for destructive or architectural changes.
