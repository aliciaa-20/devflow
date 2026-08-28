"""
Repository retriever for DevFlow Phase 2.

Clones a public GitHub repository into a temporary directory using the system
`git` command. No GitHub authentication is required for public repositories.

The caller is responsible for cleanup — use as a context manager to ensure
the temporary directory is always removed.

No credentials are stored or passed here. If the repository is private or
GitHub is unavailable, a RepositoryRetrievalError is raised with a clear
message.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class RepositoryRetrievalError(RuntimeError):
    """Raised when a repository cannot be retrieved."""


class RetrievedRepository:
    """
    A repository that has been cloned to a local temporary directory.

    Use as a context manager to guarantee cleanup:

        with RetrievedRepository.clone(url) as repo:
            ...repo.path...

    Or call cleanup() manually when finished.
    """

    def __init__(self, url: str, owner: str, name: str, local_path: Path) -> None:
        self.url = url
        self.owner = owner
        self.name = name
        self.path: Path = local_path
        self._tempdir: Optional[Path] = local_path  # set to None after cleanup

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "RetrievedRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.cleanup()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Remove the temporary directory. Safe to call multiple times."""
        if self._tempdir is not None and self._tempdir.exists():
            shutil.rmtree(self._tempdir, ignore_errors=True)
        self._tempdir = None

    @property
    def is_available(self) -> bool:
        return self._tempdir is not None and self.path.exists()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def clone(
        cls,
        url: str,
        owner: str,
        name: str,
        timeout: int = 120,
    ) -> "RetrievedRepository":
        """
        Clone a public GitHub repository into a fresh temporary directory.

        Args:
            url:     The https://github.com/... URL to clone.
            owner:   Repository owner (for metadata; already extracted by Phase 1).
            name:    Repository name (for metadata).
            timeout: Maximum seconds to wait for the clone to complete.

        Returns:
            A RetrievedRepository pointing at the cloned directory.

        Raises:
            RepositoryRetrievalError: If git is not available, the repository
                                      does not exist, access is denied, or the
                                      clone times out.
        """
        # Verify that git is available on the system PATH.
        if shutil.which("git") is None:
            raise RepositoryRetrievalError(
                "git is not available on PATH. "
                "Install git to enable repository retrieval."
            )

        # Create a temporary parent directory; the repo will be cloned inside it.
        tmpdir = Path(tempfile.mkdtemp(prefix="devflow_"))
        clone_target = tmpdir / name

        try:
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth=1",       # Shallow clone — we only need current state.
                    "--quiet",
                    url,
                    str(clone_target),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise RepositoryRetrievalError(
                f"Repository clone timed out after {timeout}s: {url}"
            )
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise RepositoryRetrievalError(
                f"Unexpected error cloning {url}: {exc}"
            ) from exc

        if result.returncode != 0:
            shutil.rmtree(tmpdir, ignore_errors=True)
            stderr = result.stderr.strip()
            raise RepositoryRetrievalError(
                f"Failed to clone repository {url!r}. "
                f"git exit code {result.returncode}. "
                f"Detail: {stderr or '(no stderr)'}"
            )

        if not clone_target.exists() or not clone_target.is_dir():
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise RepositoryRetrievalError(
                f"Clone appeared to succeed but target directory not found: {clone_target}"
            )

        return cls(url=url, owner=owner, name=name, local_path=tmpdir)
