"""Tests for automated resolution polling (Phase 8 resolve-auto command)."""

import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

from devflow.resolution._build import wait_for_bob_investigation
from devflow.resolution._sessions import session_dir, write_request_snapshot, write_state
from devflow.models.resolution import ResolutionRequest


def test_wait_for_bob_investigation_returns_content_when_file_appears(tmp_path):
    """Poll until bob_investigation.md appears, then return its content."""
    # Create a fake resolution session
    session = session_dir("res_test_001", bob_sessions_dir=tmp_path)
    session.mkdir(parents=True, exist_ok=True)

    # Create dummy request to persist
    request = ResolutionRequest(
        id="res_test_001",
        repository_url="https://github.com/example/repo",
        owner="example",
        name="repo",
        change_summary="Test change",
        finding_id="test-finding",
        finding_snapshot={},
    )
    write_request_snapshot(request, bob_sessions_dir=tmp_path)

    # Write the file after a short delay (in background thread)
    def write_after_delay():
        time.sleep(0.5)
        investigation_path = session / "bob_investigation.md"
        investigation_path.write_text("## Proposed Change\n\nTest fix.\n", encoding="utf-8")

    thread = threading.Thread(target=write_after_delay, daemon=True)
    thread.start()

    # Poll for the file
    result = wait_for_bob_investigation("res_test_001", timeout_seconds=5, bob_sessions_dir=tmp_path)

    assert "Test fix" in result
    assert "Proposed Change" in result


def test_wait_for_bob_investigation_raises_timeout_when_file_never_appears(tmp_path):
    """Raise TimeoutError if bob_investigation.md doesn't appear within timeout."""
    # Create a fake resolution session
    session = session_dir("res_test_002", bob_sessions_dir=tmp_path)
    session.mkdir(parents=True, exist_ok=True)

    # Create dummy request
    request = ResolutionRequest(
        id="res_test_002",
        repository_url="https://github.com/example/repo",
        owner="example",
        name="repo",
        change_summary="Test change",
        finding_id="test-finding",
        finding_snapshot={},
    )
    write_request_snapshot(request, bob_sessions_dir=tmp_path)

    # Poll with short timeout (should fail immediately)
    with pytest.raises(TimeoutError, match="Waited .* for Bob investigation output"):
        wait_for_bob_investigation("res_test_002", timeout_seconds=1, bob_sessions_dir=tmp_path)
