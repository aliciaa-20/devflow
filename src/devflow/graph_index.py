"""
Fast, deterministic lookups over a RepositoryKnowledgeGraph.

The Repository Knowledge Graph answers "what exists in this codebase?".  This
module is the adapter that lets the Change Impact Map pipeline (Phases 4-5)
reason over the *structural* evidence that graph already computed -- real
static import edges and test associations -- instead of relying on filename
token overlap alone.

The two graph concepts stay separate: this module never mutates the knowledge
graph and never merges it into the Change Impact Map.  It only reads edges.

Every lookup returns repository-relative paths, sorted, so callers produce
deterministic output.  A missing or failed graph degrades to an empty index
rather than raising, so the pipeline keeps working without structural
evidence.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from devflow.models.repository_graph import (
    RepositoryKnowledgeGraph,
    RepositoryNodeType,
    RepositoryRelationshipType,
)

# Node types that represent an actual file in the repository.  Directory,
# repository-root and external-dependency nodes are deliberately excluded:
# impact analysis reasons about files.
_FILE_NODE_TYPES = frozenset(
    {
        RepositoryNodeType.SOURCE_FILE,
        RepositoryNodeType.TEST_FILE,
        RepositoryNodeType.DOCUMENTATION_FILE,
        RepositoryNodeType.CONFIGURATION_FILE,
        RepositoryNodeType.DEPENDENCY_MANIFEST,
        RepositoryNodeType.ENTRY_POINT,
        RepositoryNodeType.GENERATED_FILE,
        RepositoryNodeType.OTHER_FILE,
    }
)


def _node_path(node) -> Optional[str]:
    """Recover a node's repository-relative path.

    Prefers the explicit ``path`` field, then ``metadata['path']``, then the
    path segment of the namespaced node id (``file_node_id`` guarantees the
    ``<node_type>:<path>`` shape).
    """
    if getattr(node, "path", None):
        return str(node.path).replace("\\", "/").strip("/")
    metadata = getattr(node, "metadata", None) or {}
    raw = metadata.get("path")
    if raw:
        return str(raw).replace("\\", "/").strip("/")
    node_id = getattr(node, "id", "") or ""
    if ":" in node_id:
        return node_id.split(":", 1)[1].replace("\\", "/").strip("/")
    return None


class RepositoryGraphIndex:
    """Read-only structural lookups over a RepositoryKnowledgeGraph."""

    def __init__(self, graph: Optional[RepositoryKnowledgeGraph] = None) -> None:
        self._path_by_node_id: dict[str, str] = {}
        self._imports: dict[str, set[str]] = {}
        self._imported_by: dict[str, set[str]] = {}
        self._tested_by: dict[str, set[str]] = {}
        self._file_paths: set[str] = set()
        self._graph_error: Optional[str] = None

        if graph is None:
            self._graph_error = "No repository knowledge graph was supplied."
            return
        if graph.error:
            self._graph_error = graph.error
            return

        for node in graph.nodes:
            if node.node_type not in _FILE_NODE_TYPES:
                continue
            path = _node_path(node)
            if not path:
                continue
            self._path_by_node_id[node.id] = path
            self._file_paths.add(path)

        for edge in graph.edges:
            source = self._path_by_node_id.get(edge.source)
            target = self._path_by_node_id.get(edge.target)
            if source is None or target is None:
                # One endpoint is a directory, the repository root or an
                # external package: not a file-to-file structural relationship.
                continue
            if edge.relationship == RepositoryRelationshipType.IMPORTS:
                self._imports.setdefault(source, set()).add(target)
                self._imported_by.setdefault(target, set()).add(source)
            elif edge.relationship == RepositoryRelationshipType.IMPORTED_BY:
                self._imported_by.setdefault(source, set()).add(target)
                self._imports.setdefault(target, set()).add(source)
            elif edge.relationship == RepositoryRelationshipType.TESTED_BY:
                self._tested_by.setdefault(source, set()).add(target)

    # -- availability -------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether structural evidence is usable for this repository."""
        return self._graph_error is None and bool(self._file_paths)

    @property
    def error(self) -> Optional[str]:
        return self._graph_error

    @property
    def file_count(self) -> int:
        return len(self._file_paths)

    @property
    def import_edge_count(self) -> int:
        return sum(len(targets) for targets in self._imports.values())

    def has_file(self, path: str) -> bool:
        return _normalize(path) in self._file_paths

    # -- direct edges -------------------------------------------------------

    def imports_of(self, path: str) -> tuple[str, ...]:
        """Files that ``path`` imports (static import evidence)."""
        return tuple(sorted(self._imports.get(_normalize(path), ())))

    def imported_by(self, path: str) -> tuple[str, ...]:
        """Files that import ``path`` -- its direct dependents."""
        return tuple(sorted(self._imported_by.get(_normalize(path), ())))

    def tests_for(self, path: str) -> tuple[str, ...]:
        """Test files structurally associated with ``path``."""
        return tuple(sorted(self._tested_by.get(_normalize(path), ())))

    # -- derived ------------------------------------------------------------

    def transitive_dependents(self, path: str, *, max_depth: int = 3) -> tuple[str, ...]:
        """Files reachable by following ``imported_by`` up to ``max_depth`` hops.

        Bounded so a highly connected repository cannot produce an unbounded
        impact set.  The starting file is never included in the result.
        """
        start = _normalize(path)
        if max_depth < 1 or start not in self._file_paths:
            return ()
        seen: set[str] = {start}
        collected: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for dependent in self._imported_by.get(current, ()):
                if dependent in seen:
                    continue
                seen.add(dependent)
                collected.add(dependent)
                queue.append((dependent, depth + 1))
        return tuple(sorted(collected))

    def blast_radius(self, path: str, *, max_depth: int = 3) -> int:
        """How many files transitively depend on ``path``.

        This is the deterministic ranking signal for "how exposed is this
        change?" -- it is a count of real import edges, never an estimate.
        """
        return len(self.transitive_dependents(path, max_depth=max_depth))


def _normalize(path: str) -> str:
    return (path or "").replace("\\", "/").strip("/")


def build_graph_index(graph: Optional[RepositoryKnowledgeGraph]) -> RepositoryGraphIndex:
    """Build an index, tolerating a missing or failed graph."""
    return RepositoryGraphIndex(graph)
