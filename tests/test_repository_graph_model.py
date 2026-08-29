"""Focused contract tests for the isolated Repository Knowledge Graph model."""

from __future__ import annotations

import json

from devflow.models.repository_graph import (
    RepositoryConfidence,
    RepositoryEvidenceType,
    RepositoryGraphEdge,
    RepositoryGraphEvidence,
    RepositoryGraphNode,
    RepositoryKnowledgeGraph,
    RepositoryNodeType,
    RepositoryRelationshipType,
    directory_node_id,
    external_dependency_node_id,
    file_node_id,
    repository_node_id,
)


def _evidence() -> RepositoryGraphEvidence:
    return RepositoryGraphEvidence(
        artifact="src/api/routes.py",
        description="Static import in src/api/routes.py resolves to src/api/auth.py.",
        evidence_type=RepositoryEvidenceType.DIRECT_STATIC_IMPORT,
        confidence=RepositoryConfidence.CONFIRMED,
    )


def test_stable_namespaced_ids():
    assert repository_node_id("example/project") == "repository:example/project"
    assert directory_node_id("/src/api/") == "directory:src/api"
    assert file_node_id(RepositoryNodeType.SOURCE_FILE, "/src/api/routes.py") == "source_file:src/api/routes.py"
    assert external_dependency_node_id("react") == "external_dependency:react"


def test_node_serialization_preserves_path_metadata_evidence_and_confidence():
    node = RepositoryGraphNode(
        id="source_file:src/api/routes.py",
        label="routes.py",
        node_type=RepositoryNodeType.SOURCE_FILE,
        path="src/api/routes.py",
        description="Source file discovered in the repository.",
        metadata={"language": "python", "parent_path": "src/api"},
        evidence=(_evidence(),),
        confidence=RepositoryConfidence.LIKELY,
    )

    assert node.to_dict() == {
        "id": "source_file:src/api/routes.py",
        "label": "routes.py",
        "node_type": "source_file",
        "path": "src/api/routes.py",
        "description": "Source file discovered in the repository.",
        "metadata": {"language": "python", "parent_path": "src/api"},
        "evidence": [{
            "artifact": "src/api/routes.py",
            "description": "Static import in src/api/routes.py resolves to src/api/auth.py.",
            "evidence_type": "direct_static_import",
            "confidence": "confirmed",
        }],
        "confidence": "likely",
    }
    assert RepositoryGraphNode.from_dict(node.to_dict()) == node


def test_edge_serialization_preserves_direct_evidence_and_relationship_strength():
    edge = RepositoryGraphEdge(
        source="source_file:src/api/routes.py",
        target="source_file:src/api/auth.py",
        relationship=RepositoryRelationshipType.IMPORTS,
        description="routes.py imports auth.py.",
        evidence=(_evidence(),),
        confidence=RepositoryConfidence.CONFIRMED,
        relationship_strength="direct",
    )

    payload = edge.to_dict()
    assert payload["relationship"] == "imports"
    assert payload["evidence"][0]["evidence_type"] == "direct_static_import"
    assert payload["confidence"] == "confirmed"
    assert payload["relationship_strength"] == "direct"
    assert RepositoryGraphEdge.from_dict(payload) == edge


def test_empty_graph_serializes_with_complete_contract():
    graph = RepositoryKnowledgeGraph(
        repository_url="https://github.com/example/project",
        owner="example",
        name="project",
        generated_at="2026-08-29T00:00:00Z",
    )

    assert graph.to_dict() == {
        "repository_url": "https://github.com/example/project",
        "owner": "example",
        "name": "project",
        "default_branch": None,
        "nodes": [],
        "edges": [],
        "summary": {},
        "analysis_limits": None,
        "truncation": None,
        "error": None,
        "generated_at": "2026-08-29T00:00:00Z",
    }


def test_graph_json_round_trip_is_deterministic_and_preserves_summary_limits_and_truncation():
    graph = RepositoryKnowledgeGraph(
        repository_url="https://github.com/example/project",
        owner="example",
        name="project",
        default_branch="main",
        nodes=[
            RepositoryGraphNode(
                id="source_file:src/b.py",
                label="b.py",
                node_type=RepositoryNodeType.SOURCE_FILE,
                description="Source file.",
            ),
            RepositoryGraphNode(
                id="directory:src",
                label="src",
                node_type=RepositoryNodeType.DIRECTORY,
                path="src",
                description="Directory.",
            ),
        ],
        edges=[
            RepositoryGraphEdge(
                source="directory:src",
                target="source_file:src/b.py",
                relationship=RepositoryRelationshipType.CONTAINS,
                description="src contains b.py.",
                evidence=(
                    RepositoryGraphEvidence(
                        artifact="src/b.py",
                        description="Filesystem path shows src contains src/b.py.",
                        evidence_type=RepositoryEvidenceType.DIRECT_FILESYSTEM,
                    ),
                ),
            )
        ],
        summary={"source_files": 1, "directories": 1},
        analysis_limits={"max_visible_nodes": 100},
        truncation={"truncated": True, "hidden_node_count": 42},
        generated_at="2026-08-29T00:00:00Z",
    )

    payload = graph.to_dict()
    assert [node["id"] for node in payload["nodes"]] == ["directory:src", "source_file:src/b.py"]
    assert payload["summary"] == {"source_files": 1, "directories": 1}
    assert payload["analysis_limits"] == {"max_visible_nodes": 100}
    assert payload["truncation"] == {"truncated": True, "hidden_node_count": 42}

    encoded = graph.to_json()
    assert encoded == graph.to_json()
    assert json.loads(encoded) == payload
    assert RepositoryKnowledgeGraph.from_json(encoded).to_dict() == payload


def test_evidence_types_keep_derived_and_likely_relationships_distinct():
    derived = RepositoryGraphEvidence(
        artifact="tests/test_api.py",
        description="Test filename is similar to source filename.",
        evidence_type=RepositoryEvidenceType.DERIVED_RELATIONSHIP,
        confidence=RepositoryConfidence.LIKELY,
    )

    assert derived.to_dict()["evidence_type"] == "derived_relationship"
    assert derived.to_dict()["confidence"] == "likely"


def test_existing_prototype_evidence_labels_normalize_to_explicit_types():
    assert RepositoryGraphEvidence("a.py", "static import", "static_analysis").evidence_type is RepositoryEvidenceType.DIRECT_STATIC_IMPORT
    assert RepositoryGraphEvidence("test_a.py", "name match", "name_similarity").evidence_type is RepositoryEvidenceType.DERIVED_RELATIONSHIP
