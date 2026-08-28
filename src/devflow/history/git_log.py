"""
Git history inspector for DevFlow Phase 3.

Runs `git log` on a locally cloned repository and extracts structured commit
information for a given list of file paths.

All data comes directly from Git output. Nothing is fabricated.
No network access is required — this operates on the already-cloned local path.

References found in commit messages (e.g. "#142") are recorded as-is.
DevFlow does NOT assert these are GitHub Issues or Pull Requests.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from devflow.models.history import HistoricalCommit, HistoricalEvidence

# ---------------------------------------------------------------------------
# git log format
# ---------------------------------------------------------------------------

# Record separator: highly unlikely to appear in a commit message.
_RECORD_SEP = "\x1e"  # ASCII unit separator (RS)
_FIELD_SEP = "\x1f"   # ASCII unit separator (US)

# Format:  hash<sep>short_hash<sep>author<sep>date<sep>message
_GIT_FORMAT = f"%H{_FIELD_SEP}%h{_FIELD_SEP}%an{_FIELD_SEP}%ci{_FIELD_SEP}%s{_RECORD_SEP}"

# Maximum commits to collect per artifact.
_MAX_COMMITS_PER_ARTIFACT = 20

# Regex to find references like #123 in commit messages.
_REF_RE = re.compile(r"#\d+")


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def get_commits_for_artifact(
    repo_root: Path,
    artifact_path: str,
    max_commits: int = _MAX_COMMITS_PER_ARTIFACT,
) -> tuple[list[HistoricalCommit], list[HistoricalEvidence]]:
    """
    Run `git log` on a single artifact path and return structured commits
    with associated evidence.

    Args:
        repo_root:     Absolute path to the repository root (where .git lives).
        artifact_path: Repository-relative path (forward slashes).
        max_commits:   Maximum number of commits to return.

    Returns:
        A (commits, evidence) tuple.
        - commits: HistoricalCommit instances, most-recent first.
        - evidence: HistoricalEvidence items linking each commit to the artifact.

    If git is unavailable or history is empty, empty lists are returned.
    The caller is responsible for handling partial/missing history gracefully.
    """
    raw_output = _run_git_log(repo_root, artifact_path, max_commits)
    if raw_output is None:
        return [], []

    commits: list[HistoricalCommit] = []
    evidence_items: list[HistoricalEvidence] = []

    for record in raw_output.split(_RECORD_SEP):
        record = record.strip()
        if not record:
            continue

        parts = record.split(_FIELD_SEP)
        if len(parts) < 5:
            continue

        commit_hash = parts[0].strip()
        short_hash = parts[1].strip()
        author = parts[2].strip() or None
        date_iso = parts[3].strip() or None
        message = parts[4].strip()

        if not commit_hash or len(commit_hash) < 7:
            continue

        # Extract message references (e.g. "#142") — recorded as-is.
        refs = tuple(sorted(set(_REF_RE.findall(message))))

        commit = HistoricalCommit(
            hash=commit_hash,
            short_hash=short_hash,
            message=message,
            author=author,
            date_iso=date_iso,
            refs=refs,
        )
        commits.append(commit)

        ev = HistoricalEvidence(
            artifact_path=artifact_path,
            commit_hash=commit_hash,
            description=(
                f"Git commit {short_hash} modified {artifact_path}. "
                f"Message: \"{message}\". "
                f"Author: {author or 'unknown'}. "
                f"Date: {date_iso or 'unknown'}."
            ),
            relevance_reason=f"commit {short_hash} directly modified '{artifact_path}'",
            evidence_type="direct_modification",
        )
        evidence_items.append(ev)

    return commits, evidence_items


def is_git_repository(path: Path) -> bool:
    """Return True if the given path is inside a Git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(path),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_git_log(
    repo_root: Path,
    artifact_path: str,
    max_commits: int,
) -> Optional[str]:
    """
    Execute git log for a specific file path and return raw output.

    Returns None if git is unavailable or the command fails.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--max-count={max_commits}",
                f"--format={_GIT_FORMAT}",
                "--follow",   # follow file renames
                "--",
                artifact_path,
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    return result.stdout
