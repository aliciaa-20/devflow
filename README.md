# DevFlow

**From unfamiliar code to confident change.**

DevFlow is an agentic, context-aware code review assistant for developers working in unfamiliar or evolving codebases.

DevFlow accepts a public GitHub repository URL and a developer change description, reconstructs the relevant technical and historical context, and presents it as a visual, evidence-backed Change Impact Map.

DevFlow is repository-agnostic. It does not depend on any specific project, technology stack, or repository structure.

---

## Quickstart

### Requirements

- Python 3.11 or later

### Install

```bash
pip install -e ".[dev]"
```

### Run

```bash
python -m devflow
```

### Test

```bash
pytest
```

---

## Project Structure

```
devflow/
├── __init__.py         # package version
├── __main__.py         # application entry point
├── config.py           # environment-based configuration
└── pipeline/           # future pipeline stages (Phase 1–9)
    └── __init__.py

tests/
├── __init__.py
└── test_entry.py       # smoke tests

docs/
└── architecture.md     # architecture overview
```

---

## Development Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Foundation | IN PROGRESS |
| 1 | Repository + Change Input | BLOCKED |
| 2 | Repository Ingestion + Context Reconstruction | BLOCKED |
| 3 | Historical Context | BLOCKED |
| 4 | Impact Analysis | BLOCKED |
| 5 | Risk Analysis | BLOCKED |
| 6 | Change Impact Map | BLOCKED |
| 7 | Developer Report | BLOCKED |
| 8 | Bob Resolution | BLOCKED |
| 9 | Validation | BLOCKED |

---

## License

This project is developed as part of the DevFlow implementation.
