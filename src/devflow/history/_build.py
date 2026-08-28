"""
DevFlow Phase 3 — Historical Context.

Public entry point: build_historical_context()

Orchestrates:
  1. Repository cloning (reuses Phase 2 retriever)
  2. Git log inspection per relevant artifact (git_log)
  3. Structured RepositoryHistory output
  4. Cleanup

Accepts the RepositoryContext produced by Phase 2 (or at minimum the
repository URL, owner, name, and list of relevant artifact paths).

Returns a RepositoryHistory that Phase 4 (Impact Analysis) and Phase 6
(Change Impact Map) can consume directly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from devflow.models.context import RepositoryContext
from devflow.models.history import ArtifactHistory, RepositoryHistory
from devflow.models.repository import RepositoryInput
from devflow.context.retriever import RetrievedRepository, RepositoryRetrievalError
from devflow.history.git_log import get_commits_for_artifact, is_git_repository

logger = logging.getLogger(__name__)


def build_historical_context(
    repository: RepositoryInput,
    context: RepositoryContext,
    *,
    clone_timeout: int = 120,
    max_commits_per_artifact: int = 20,
    max_artifacts: int = 50,
) -> RepositoryHistory:
    """
    Inspect the Git history of a repository for the artifacts identified by
    Phase 2, and produce structured historical context.

    The repository is cloned fresh (shallow clone with extended depth to
    capture meaningful history), inspected, and cleaned up before return.

    Args:
        repository:               Validated RepositoryInput from Phase 1.
        context:                  RepositoryContext produced by Phase 2.
        clone_timeout:            Maximum seconds for git clone.
        max_commits_per_artifact: Upper bound on commits collected per artifact.
        max_artifacts:            Upper bound on artifacts inspected (by relevance
                                  order; avoids extremely long runs on large repos).

    Returns:
        A RepositoryHistory with per-artifact history and evidence.
        If cloning fails, returns a RepositoryHistory with .error set.
    """
    hist = RepositoryHistory(
        repository_url=repository.url,
        owner=repository.owner,
        name=repository.name,
        change_summary=context.change_summary,
    )

    if context.error:
        hist.error = (
            f"Skipped: Phase 2 context had an error: {context.error}"
        )
        return hist

    # Collect the artifact paths to inspect.
    # Prioritise: source/test artifacts from Phase 2 context (most relevant).
    artifact_paths = [a.path for a in context.artifacts]
    artifact_paths = artifact_paths[:max_artifacts]

    if not artifact_paths:
        hist.error = "No relevant artifacts to inspect."
        return hist

    # Clone the repository again with deeper history.
    try:
        retrieved = _clone_with_history(repository, clone_timeout)
    except RepositoryRetrievalError as exc:
        logger.warning("Repository retrieval failed for historical context: %s", exc)
        hist.error = str(exc)
        return hist

    try:
        repo_root = _find_repo_root(retrieved.path, repository.name)
        logger.info("Inspecting git history at %s", repo_root)

        if not is_git_repository(repo_root):
            hist.error = "Cloned directory is not a recognizable Git repository."
            return hist

        all_commit_hashes: set[str] = set()

        for artifact_path in artifact_paths:
            commits, evidence = get_commits_for_artifact(
                repo_root=repo_root,
                artifact_path=artifact_path,
                max_commits=max_commits_per_artifact,
            )

            note: Optional[str] = None
            if not commits:
                note = (
                    f"No Git history found for '{artifact_path}'. "
                    "The file may be new, renamed beyond --follow detection, "
                    "or the history depth may be insufficient."
                )

            artifact_hist = ArtifactHistory(
                artifact_path=artifact_path,
                commits=tuple(commits),
                evidence=tuple(evidence),
                note=note,
            )
            hist.artifact_histories[artifact_path] = artifact_hist

            for commit in commits:
                all_commit_hashes.add(commit.hash)

            logger.debug(
                "Artifact '%s': %d commits found", artifact_path, len(commits)
            )

        hist.total_commits_found = len(all_commit_hashes)
        logger.info(
            "Historical context: %d artifacts inspected, %d distinct commits found",
            len(artifact_paths),
            hist.total_commits_found,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during historical context extraction")
        hist.error = f"Historical context extraction failed: {exc}"

    finally:
        retrieved.cleanup()
        logger.debug("Temporary repository directory cleaned up after history inspection")

    return hist


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clone_with_history(
    repository: RepositoryInput,
    timeout: int,
) -> RetrievedRepository:
    """
    Clone the repository with enough depth to capture meaningful history.

    Uses --depth=100 rather than --depth=1 to retrieve recent history while
    keeping network usage reasonable.
    """
    import shutil
    import subprocess
    import tempfile

    if shutil.which("git") is None:
        raise RepositoryRetrievalError(
            "git is not available on PATH. "
            "Install git to enable repository retrieval."
        )

    tmpdir = Path(tempfile.mkdtemp(prefix="devflow_hist_"))
    clone_target = tmpdir / repository.name

    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth=100",
                "--quiet",
                repository.url,
                str(clone_target),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RepositoryRetrievalError(
            f"Repository clone timed out after {timeout}s: {repository.url}"
        )
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RepositoryRetrievalError(
            f"Unexpected error cloning {repository.url}: {exc}"
        ) from exc

    if result.returncode != 0:
        shutil.rmtree(tmpdir, ignore_errors=True)
        stderr = result.stderr.strip()
        raise RepositoryRetrievalError(
            f"Failed to clone repository {repository.url!r}. "
            f"git exit code {result.returncode}. "
            f"Detail: {stderr or '(no stderr)'}"
        )

    if not clone_target.exists() or not clone_target.is_dir():
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RepositoryRetrievalError(
            f"Clone appeared to succeed but target directory not found: {clone_target}"
        )

    return RetrievedRepository(
        url=repository.url,
        owner=repository.owner,
        name=repository.name,
        local_path=tmpdir,
    )


def _find_repo_root(tmpdir: Path, name: str) -> Path:
    """Locate the cloned repository root inside a temporary directory."""
    candidate = tmpdir / name
    if candidate.is_dir():
        return candidate

    candidate2 = tmpdir / name.removesuffix(".git")
    if candidate2.is_dir():
        return candidate2

    subdirs = [p for p in tmpdir.iterdir() if p.is_dir()]
    if subdirs:
        return subdirs[0]

    return tmpdir
