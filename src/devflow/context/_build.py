"""
DevFlow Phase 2 — Repository Context Reconstruction.

Public entry point: build_context()

Orchestrates:
  1. Repository cloning (retriever)
  2. File-system inspection (inspector)
  3. Relevance selection (relevance)
  4. Cleanup

Returns a RepositoryContext that future phases (Impact Analysis,
Change Impact Map, etc.) can consume directly.
"""

from __future__ import annotations

import logging
from pathlib import Path

from devflow.models.change import ChangeRequest
from devflow.models.context import RepositoryContext
from devflow.models.repository import RepositoryInput
from devflow.context.inspector import walk_repository
from devflow.context.relevance import select_relevant_artifacts
from devflow.context.retriever import RetrievedRepository, RepositoryRetrievalError

logger = logging.getLogger(__name__)


def build_context(
    repository: RepositoryInput,
    change: ChangeRequest,
    *,
    clone_timeout: int = 120,
) -> RepositoryContext:
    """
    Retrieve and inspect a public GitHub repository, then produce structured
    context relevant to the supplied change.

    The temporary clone directory is cleaned up before this function returns,
    regardless of success or failure. The RepositoryContext.retrieval_path
    field is set to None after cleanup to reflect this.

    Args:
        repository:    Validated RepositoryInput from Phase 1.
        change:        Validated ChangeRequest from Phase 1.
        clone_timeout: Maximum seconds to allow for the git clone operation.

    Returns:
        A RepositoryContext with:
        - All discovered repository files
        - Identified entry points
        - Relevant artifacts with reasons and evidence
        - An error message (and empty artifact list) if retrieval failed

    This function does not raise RepositoryRetrievalError; errors are captured
    in RepositoryContext.error so the caller can handle or surface them.
    """
    ctx = RepositoryContext(
        repository_url=repository.url,
        owner=repository.owner,
        name=repository.name,
        change_summary=change.description,
    )

    try:
        retrieved = RetrievedRepository.clone(
            url=repository.url,
            owner=repository.owner,
            name=repository.name,
            timeout=clone_timeout,
        )
    except RepositoryRetrievalError as exc:
        logger.warning("Repository retrieval failed: %s", exc)
        ctx.error = str(exc)
        return ctx

    try:
        repo_root = _find_repo_root(retrieved.path, repository.name)

        logger.info("Inspecting repository at %s", repo_root)

        all_files, entry_points = walk_repository(repo_root)

        logger.info(
            "Found %d files, %d entry points",
            len(all_files),
            len(entry_points),
        )

        artifacts = select_relevant_artifacts(all_files, change)

        logger.info("Selected %d relevant artifacts", len(artifacts))

        ctx.all_files = all_files
        ctx.entry_points = entry_points
        ctx.artifacts = artifacts
        # retrieval_path is intentionally left None (cleaned up below).

        # Build the Repository Knowledge Graph from the clone we already have.
        # Phases 4-5 need its real static import and test-association edges to
        # reason structurally instead of by filename overlap, and building it
        # here removes a second, redundant clone of the same repository.
        #
        # This is best-effort: the graph is a separate product concern, so a
        # failure here degrades impact/risk analysis to the non-structural
        # path rather than failing context reconstruction.
        #
        # Imported here rather than at module scope: devflow.knowledge_graph
        # imports devflow.context.inspector, which initializes this package,
        # so a top-level import would be circular.
        try:
            from devflow.knowledge_graph import build_repository_knowledge_graph

            ctx.repository_graph = build_repository_knowledge_graph(
                repository.url, local_root=repo_root
            )
            if ctx.repository_graph.error:
                logger.warning(
                    "Repository knowledge graph unavailable: %s",
                    ctx.repository_graph.error,
                )
            else:
                logger.info(
                    "Repository knowledge graph: %d nodes, %d edges",
                    len(ctx.repository_graph.nodes),
                    len(ctx.repository_graph.edges),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Repository knowledge graph build failed: %s", exc)
            ctx.repository_graph = None

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during repository inspection")
        ctx.error = f"Repository inspection failed: {exc}"

    finally:
        retrieved.cleanup()
        logger.debug("Temporary repository directory cleaned up")

    return ctx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_repo_root(tmpdir: Path, name: str) -> Path:
    """
    Locate the cloned repository root inside a temporary directory.

    git clone creates a subdirectory named after the repository. If the
    expected name doesn't exist, fall back to the first subdirectory found.
    """
    candidate = tmpdir / name
    if candidate.is_dir():
        return candidate

    # Try the name without potential .git suffix.
    candidate2 = tmpdir / name.removesuffix(".git")
    if candidate2.is_dir():
        return candidate2

    # Fallback: first directory entry.
    subdirs = [p for p in tmpdir.iterdir() if p.is_dir()]
    if subdirs:
        return subdirs[0]

    # Last resort: the tmp dir itself.
    return tmpdir
