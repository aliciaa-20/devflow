"""Read/write bob_sessions/<id>/ evidence files for DevFlow Phase 8.

Every resolution gets its own directory under bob_sessions/, matching
CLAUDE.md's requirement to preserve real Bob task-session evidence:

    request.json          immutable snapshot at creation
    state.json             current full ResolutionRequest, overwritten each transition
    bob_investigation.md   verbatim copy of Bob's "Propose the Fix" output
    bob_result.md          verbatim copy of Bob's closing "Resolution Summary" output
    test_run.txt           real captured stdout/stderr of the executed test command
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from devflow.models.resolution import ResolutionRequest


def _sessions_root(bob_sessions_dir: Optional[str | Path] = None) -> Path:
    if bob_sessions_dir is not None:
        return Path(bob_sessions_dir)
    return Path(__file__).resolve().parents[3] / "bob_sessions"


def session_dir(resolution_id: str, *, bob_sessions_dir: Optional[str | Path] = None) -> Path:
    return _sessions_root(bob_sessions_dir) / resolution_id


def write_request_snapshot(
    request: ResolutionRequest, *, bob_sessions_dir: Optional[str | Path] = None
) -> Path:
    """Write the immutable request.json snapshot. Call this once, at creation."""
    target_dir = session_dir(request.id, bob_sessions_dir=bob_sessions_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "request.json"
    target.write_text(json.dumps(request.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_state(
    request: ResolutionRequest, *, bob_sessions_dir: Optional[str | Path] = None
) -> Path:
    """Overwrite state.json with the current full ResolutionRequest state."""
    target_dir = session_dir(request.id, bob_sessions_dir=bob_sessions_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "state.json"
    target.write_text(json.dumps(request.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def read_state(
    resolution_id: str, *, bob_sessions_dir: Optional[str | Path] = None
) -> dict:
    target = session_dir(resolution_id, bob_sessions_dir=bob_sessions_dir) / "state.json"
    return json.loads(target.read_text(encoding="utf-8"))


def load_request(
    resolution_id: str, *, bob_sessions_dir: Optional[str | Path] = None
) -> ResolutionRequest:
    """Reconstruct a ResolutionRequest from its persisted state.json.

    Each CLI invocation is a fresh process, so a resolution in progress must
    be reloaded from disk between the investigate gate, the fix-ingest step,
    the apply gate, and validation.
    """
    return ResolutionRequest.from_dict(read_state(resolution_id, bob_sessions_dir=bob_sessions_dir))


def write_raw_text(
    resolution_id: str,
    filename: str,
    text: str,
    *,
    bob_sessions_dir: Optional[str | Path] = None,
) -> Path:
    """Write a verbatim copy of raw text evidence (Bob output, test output)."""
    target_dir = session_dir(resolution_id, bob_sessions_dir=bob_sessions_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_text(text, encoding="utf-8")
    return target
