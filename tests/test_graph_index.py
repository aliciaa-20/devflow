"""Tests for structural lookups over a Repository Knowledge Graph.

These cover the adapter that lets Phases 4-5 reason over real static import
edges instead of filename overlap alone.
"""

from devflow.graph_index import RepositoryGraphIndex, build_graph_index
from devflow.models.repository_graph import (
    RepositoryGraphEdge,
    RepositoryGraphNode,
    RepositoryKnowledgeGraph,
    RepositoryNodeType,
    RepositoryRelationshipType,
    file_node_id,
)


def _file(path: str, node_type: RepositoryNodeType = RepositoryNodeType.SOURCE_FILE) -> RepositoryGraphNode:
    return RepositoryGraphNode(
        id=file_node_id(node_type, path),
        label=path.rsplit("/", 1)[-1],
        node_type=node_type,
        description=f"File {path}",
        path=path,
    )


def _edge(source: str, target: str, relationship: RepositoryRelationshipType) -> RepositoryGraphEdge:
    return RepositoryGraphEdge(
        source=source,
        target=target,
        relationship=relationship,
        description=f"{source} {relationship.value} {target}",
    )


def _graph(nodes, edges, error=None) -> RepositoryKnowledgeGraph:
    graph = RepositoryKnowledgeGraph(
        repository_url="https://github.com/example/repo", owner="example", name="repo"
    )
    graph.nodes = list(nodes)
    graph.edges = list(edges)
    graph.error = error
    return graph


def _chain_graph() -> RepositoryKnowledgeGraph:
    """app.py -> service.py -> core.py, with core.py covered by a test."""
    core = _file("src/core.py")
    service = _file("src/service.py")
    app = _file("src/app.py")
    test_core = _file("tests/test_core.py", RepositoryNodeType.TEST_FILE)
    return _graph(
        [core, service, app, test_core],
        [
            _edge(service.id, core.id, RepositoryRelationshipType.IMPORTS),
            _edge(core.id, service.id, RepositoryRelationshipType.IMPORTED_BY),
            _edge(app.id, service.id, RepositoryRelationshipType.IMPORTS),
            _edge(service.id, app.id, RepositoryRelationshipType.IMPORTED_BY),
            _edge(core.id, test_core.id, RepositoryRelationshipType.TESTED_BY),
        ],
    )


def test_index_reports_unavailable_without_a_graph():
    index = build_graph_index(None)
    assert not index.available
    assert index.error
    assert index.imports_of("src/core.py") == ()
    assert index.transitive_dependents("src/core.py") == ()


def test_index_reports_unavailable_when_the_graph_failed():
    index = build_graph_index(_graph([], [], error="clone failed"))
    assert not index.available
    assert index.error == "clone failed"


def test_direct_import_edges_are_readable_in_both_directions():
    index = build_graph_index(_chain_graph())
    assert index.available
    assert index.imports_of("src/service.py") == ("src/core.py",)
    assert index.imported_by("src/core.py") == ("src/service.py",)


def test_imported_by_edges_alone_populate_the_reverse_direction():
    """A graph emitting only IMPORTED_BY must still answer imports_of()."""
    core, service = _file("src/core.py"), _file("src/service.py")
    index = build_graph_index(
        _graph(
            [core, service],
            [_edge(core.id, service.id, RepositoryRelationshipType.IMPORTED_BY)],
        )
    )
    assert index.imported_by("src/core.py") == ("src/service.py",)
    assert index.imports_of("src/service.py") == ("src/core.py",)


def test_transitive_dependents_follow_the_import_chain():
    index = build_graph_index(_chain_graph())
    # service.py imports core.py; app.py imports service.py.
    assert index.transitive_dependents("src/core.py") == ("src/app.py", "src/service.py")
    assert index.blast_radius("src/core.py") == 2


def test_transitive_dependents_respect_the_depth_bound():
    index = build_graph_index(_chain_graph())
    assert index.transitive_dependents("src/core.py", max_depth=1) == ("src/service.py",)


def test_transitive_dependents_exclude_the_starting_file():
    index = build_graph_index(_chain_graph())
    assert "src/core.py" not in index.transitive_dependents("src/core.py")


def test_transitive_dependents_terminate_on_an_import_cycle():
    a, b = _file("src/a.py"), _file("src/b.py")
    index = build_graph_index(
        _graph(
            [a, b],
            [
                _edge(a.id, b.id, RepositoryRelationshipType.IMPORTS),
                _edge(b.id, a.id, RepositoryRelationshipType.IMPORTS),
            ],
        )
    )
    assert index.transitive_dependents("src/a.py", max_depth=5) == ("src/b.py",)


def test_test_associations_are_readable():
    index = build_graph_index(_chain_graph())
    assert index.tests_for("src/core.py") == ("tests/test_core.py",)
    assert index.tests_for("src/service.py") == ()


def test_non_file_nodes_are_excluded_from_structural_lookups():
    """Directory and external-dependency endpoints are not file relationships."""
    core = _file("src/core.py")
    directory = RepositoryGraphNode(
        id="directory:src",
        label="src",
        node_type=RepositoryNodeType.DIRECTORY,
        description="src directory",
        path="src",
    )
    external = RepositoryGraphNode(
        id="external_dependency:requests",
        label="requests",
        node_type=RepositoryNodeType.EXTERNAL_DEPENDENCY,
        description="requests package",
    )
    index = build_graph_index(
        _graph(
            [core, directory, external],
            [
                _edge(directory.id, core.id, RepositoryRelationshipType.CONTAINS),
                _edge(core.id, external.id, RepositoryRelationshipType.IMPORTS),
            ],
        )
    )
    assert index.has_file("src/core.py")
    assert not index.has_file("src")
    # The external package is not a repository file, so it is not an import target.
    assert index.imports_of("src/core.py") == ()
    assert index.file_count == 1


def test_paths_are_normalized_for_lookup():
    index = build_graph_index(_chain_graph())
    assert index.imported_by("/src/core.py") == ("src/service.py",)
    assert index.imported_by("src\\core.py") == ("src/service.py",)


def test_index_counts_real_import_edges():
    index = build_graph_index(_chain_graph())
    assert index.import_edge_count == 2


def test_unknown_file_yields_empty_results_rather_than_raising():
    index = build_graph_index(_chain_graph())
    assert index.imports_of("src/missing.py") == ()
    assert index.imported_by("src/missing.py") == ()
    assert index.transitive_dependents("src/missing.py") == ()
    assert index.blast_radius("src/missing.py") == 0


def test_index_is_constructible_directly():
    assert isinstance(RepositoryGraphIndex(None), RepositoryGraphIndex)
