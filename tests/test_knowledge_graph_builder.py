"""Tests for the Repository Knowledge Graph builder (devflow.knowledge_graph).

Uses build_repository_knowledge_graph's local_root parameter to run against a
local fixture directory -- no network clone, no live GitHub access -- mirroring
how the rest of the deterministic pipeline is tested.
"""

from __future__ import annotations

import json

from devflow.knowledge_graph import (
    build_repository_knowledge_graph,
    serialize_repository_knowledge_graph,
    write_repository_graph_payload,
)
from devflow.models.repository_graph import RepositoryNodeType, RepositoryRelationshipType


def _write_fixture_repo(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "import os\nimport src.util\n\ndef run():\n    return src.util.VALUE\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_run():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("flask\nrequests\n", encoding="utf-8")
    (tmp_path / "setup.cfg").write_text("[metadata]\nname = example\n", encoding="utf-8")
    return tmp_path


def test_build_repository_knowledge_graph_from_local_fixture(tmp_path):
    root = _write_fixture_repo(tmp_path)

    graph = build_repository_knowledge_graph(
        "https://github.com/example/project", local_root=root
    )

    assert graph.error is None
    assert graph.owner == "example"
    assert graph.name == "project"
    assert graph.generated_at

    node_ids = {node.id for node in graph.nodes}
    assert "repository:example/project" in node_ids
    assert "source_file:src/app.py" in node_ids
    assert "source_file:src/util.py" in node_ids
    assert "test_file:tests/test_app.py" in node_ids
    assert "documentation_file:docs/guide.md" in node_ids
    assert "external_dependency:requirements.txt" in node_ids


def test_build_repository_knowledge_graph_records_real_import_and_test_edges(tmp_path):
    root = _write_fixture_repo(tmp_path)

    graph = build_repository_knowledge_graph(
        "https://github.com/example/project", local_root=root
    )

    imports_edges = [
        edge for edge in graph.edges if edge.relationship == RepositoryRelationshipType.IMPORTS
    ]
    assert any(
        edge.source == "source_file:src/app.py" and edge.target == "source_file:src/util.py"
        for edge in imports_edges
    ), "expected a real static-import edge from app.py to util.py"

    tested_by_edges = [
        edge for edge in graph.edges if edge.relationship == RepositoryRelationshipType.TESTED_BY
    ]
    assert any(
        edge.source == "source_file:src/app.py" and edge.target == "test_file:tests/test_app.py"
        for edge in tested_by_edges
    ), "expected a name-similarity TESTED_BY edge from app.py to test_app.py"

    for edge in imports_edges + tested_by_edges:
        assert edge.evidence, "every relationship edge must carry evidence, never asserted without it"


def test_build_repository_knowledge_graph_declares_manifest_dependencies(tmp_path):
    root = _write_fixture_repo(tmp_path)

    graph = build_repository_knowledge_graph(
        "https://github.com/example/project", local_root=root
    )

    dependency_ids = {
        node.id for node in graph.nodes if node.node_type == RepositoryNodeType.EXTERNAL_DEPENDENCY
    }
    assert "external_dependency:flask" in dependency_ids
    assert "external_dependency:requests" in dependency_ids


def test_build_repository_knowledge_graph_invalid_url_reports_error_not_fabrication():
    graph = build_repository_knowledge_graph("not-a-github-url")

    assert graph.error is not None
    assert graph.nodes == []
    assert graph.edges == []


def test_build_repository_knowledge_graph_round_trips_through_json(tmp_path):
    root = _write_fixture_repo(tmp_path)
    graph = build_repository_knowledge_graph(
        "https://github.com/example/project", local_root=root
    )

    payload = json.loads(graph.to_json())
    assert payload["owner"] == "example"
    assert len(payload["nodes"]) == len(graph.nodes)
    assert len(payload["edges"]) == len(graph.edges)


def test_serialize_repository_knowledge_graph_writes_json_file(tmp_path):
    root = _write_fixture_repo(tmp_path / "repo")
    graph = build_repository_knowledge_graph(
        "https://github.com/example/project", local_root=root
    )

    output_path = tmp_path / "out" / "repo-graph.json"
    result_path = serialize_repository_knowledge_graph(graph, output_path)

    assert result_path == output_path
    assert output_path.exists()
    on_disk = json.loads(output_path.read_text(encoding="utf-8"))
    assert on_disk["owner"] == "example"


def test_build_repository_knowledge_graph_resolves_standard_relative_imports(tmp_path):
    """`from .module import X` and `from . import module` are the dominant
    Python relative-import styles (ast strips the leading dots into
    node.level rather than keeping them in node.module) -- both must resolve
    to real IMPORTS edges, not silently vanish."""
    root = tmp_path
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "a.py").write_text("from .b import VALUE\n", encoding="utf-8")
    (root / "pkg" / "b.py").write_text("from . import c\n", encoding="utf-8")
    (root / "pkg" / "c.py").write_text("VALUE = 1\n", encoding="utf-8")

    graph = build_repository_knowledge_graph("https://github.com/example/project", local_root=root)

    imports_edges = {
        (edge.source, edge.target)
        for edge in graph.edges
        if edge.relationship == RepositoryRelationshipType.IMPORTS
    }
    assert ("source_file:pkg/a.py", "source_file:pkg/b.py") in imports_edges
    assert ("source_file:pkg/b.py", "source_file:pkg/c.py") in imports_edges


def test_build_repository_knowledge_graph_resolves_imports_through_a_symlinked_root(tmp_path):
    """Regression guard: on macOS, /tmp -> /private/tmp and /var -> /private/var
    are symlinks, so a real clone (or any local_root) commonly sits behind one.
    build_repository_knowledge_graph must resolve root_dir before comparing
    resolved candidate paths against it, or every relative-import resolution
    silently fails and no IMPORTS/IMPORTED_BY edges are ever produced."""
    real_root = tmp_path / "actual_repo"
    _write_fixture_repo(real_root)
    symlinked_root = tmp_path / "symlinked_repo"
    symlinked_root.symlink_to(real_root, target_is_directory=True)

    graph = build_repository_knowledge_graph(
        "https://github.com/example/project", local_root=symlinked_root
    )

    imports_edges = [
        edge for edge in graph.edges if edge.relationship == RepositoryRelationshipType.IMPORTS
    ]
    assert any(
        edge.source == "source_file:src/app.py" and edge.target == "source_file:src/util.py"
        for edge in imports_edges
    ), "internal import resolution must not silently break when root_dir is reached through a symlink"


def test_write_repository_graph_payload_targets_dedicated_file_not_change_impact_map(tmp_path):
    """Regression guard: the Repository Knowledge Graph must never write to
    devflow-graph.json -- that file belongs to the Change Impact Map (Phase 6)
    and the two graph concepts must not overwrite each other."""
    root = _write_fixture_repo(tmp_path / "repo")
    graph = build_repository_knowledge_graph(
        "https://github.com/example/project", local_root=root
    )

    output_dir = tmp_path / "frontend_root"
    result_path = write_repository_graph_payload(graph, frontend_dir=output_dir)

    assert result_path.name == "devflow-repo-graph.json"
    assert result_path.name != "devflow-graph.json"
    assert not (output_dir / "frontend" / "public" / "devflow-graph.json").exists()
