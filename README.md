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

The current implementation includes structured repository context for this purpose, but it does not yet provide a dedicated interactive Repository Knowledge Graph UI.

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
| 8+ | Bob Resolution, Validation, Demo, Submission | NOT IMPLEMENTED / BLOCKED |

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

Current limitations:

- The full interactive Change Impact Map described in the architecture is not yet complete.
- IBM Bob is not yet integrated into a production-style resolution workflow.
- Repository Knowledge Graph remains an orientation concept rather than a dedicated interactive feature.
- Phases 8 and beyond are not implemented yet and remain blocked per project task sequencing.

---

## How to run DevFlow

### Requirements

- Python 3.11+
- Git available on PATH for repository inspection and history retrieval

### Install

```bash
pip install -e ".[dev]"
```

### Run the local entry point

```bash
python -m devflow
```

This entry point demonstrates the implemented phases and prints the current validation/demo status without requiring a live repository fetch for the basic example flow.

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

- 268 tests passed in the current repository state

This reflects the implementation that exists today; it does not imply that later blocked phases are complete.

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

## IBM Bob's intended role

IBM Bob is intended to enter the workflow at the later resolution stage, not to replace the core analysis pipeline.

Current capability:

- The codebase does not yet integrate Bob into a working resolution workflow.
- Bob is not used as a required part of the implemented repository analysis pipeline.

Planned role:

- investigate an approved finding
- propose a focused fix
- validate the fix with relevant tests
- report what changed and why

This is part of the planned Phase 8 workflow and remains future work.

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
