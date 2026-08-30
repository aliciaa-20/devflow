"""Phase 4/5 behavior when the Repository Knowledge Graph supplies real import edges.

The pipeline previously reasoned about impact from filename token overlap, and
risk analysis only admitted source files the developer had explicitly listed as
changed. A description-only run therefore produced zero risks. These tests pin
the structural behavior that replaced that.
"""

from devflow.impact import build_impact_analysis
from devflow.models.context import (
    ArtifactKind,
    ContextArtifact,
    RelevanceReason,
    RepositoryContext,
)
from devflow.models.impact import EvidenceStrength, EvidenceType, RelationshipType
from devflow.models.repository_graph import (
    RepositoryGraphEdge,
    RepositoryGraphNode,
    RepositoryKnowledgeGraph,
    RepositoryNodeType,
    RepositoryRelationshipType,
    file_node_id,
)
from devflow.models.risk import RiskCategory, RiskSeverity
from devflow.risk import build_risk_analysis

REPO_URL = "https://github.com/example/repo"
CHANGE = "Refactor session handling."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _node(path: str, node_type: RepositoryNodeType = RepositoryNodeType.SOURCE_FILE):
    return RepositoryGraphNode(
        id=file_node_id(node_type, path),
        label=path.rsplit("/", 1)[-1],
        node_type=node_type,
        description=f"File {path}",
        path=path,
    )


def _edge(source, target, relationship):
    return RepositoryGraphEdge(
        source=source.id,
        target=target.id,
        relationship=relationship,
        description=f"{source.path} {relationship.value} {target.path}",
    )


def _graph(nodes, edges, error=None) -> RepositoryKnowledgeGraph:
    graph = RepositoryKnowledgeGraph(repository_url=REPO_URL, owner="example", name="repo")
    graph.nodes = list(nodes)
    graph.edges = list(edges)
    graph.error = error
    return graph


def _keyword_artifact(path: str, kind: ArtifactKind = ArtifactKind.SOURCE) -> ContextArtifact:
    """An artifact selected by description keywords, never declared as changed."""
    return ContextArtifact(
        path=path,
        kind=kind,
        reason=RelevanceReason.KEYWORD_MATCH,
        evidence="path keywords ['session'] match change keywords",
        confidence="likely",
    )


def _session_graph(with_test: bool = False):
    """session.py is imported by auth.py, which is imported by api.py."""
    session = _node("src/session.py")
    auth = _node("src/auth.py")
    api = _node("src/api.py")
    nodes = [session, auth, api]
    edges = [
        _edge(auth, session, RepositoryRelationshipType.IMPORTS),
        _edge(session, auth, RepositoryRelationshipType.IMPORTED_BY),
        _edge(api, auth, RepositoryRelationshipType.IMPORTS),
        _edge(auth, api, RepositoryRelationshipType.IMPORTED_BY),
    ]
    if with_test:
        test_session = _node("tests/test_session.py", RepositoryNodeType.TEST_FILE)
        nodes.append(test_session)
        edges.append(_edge(session, test_session, RepositoryRelationshipType.TESTED_BY))
    return _graph(nodes, edges)


def _context(graph=None, artifacts=None) -> RepositoryContext:
    artifacts = artifacts if artifacts is not None else [_keyword_artifact("src/session.py")]
    ctx = RepositoryContext(
        repository_url=REPO_URL,
        owner="example",
        name="repo",
        change_summary=CHANGE,
        artifacts=list(artifacts),
        all_files=[a.path for a in artifacts],
    )
    ctx.repository_graph = graph
    return ctx


def _analyze(graph=None, artifacts=None):
    ctx = _context(graph, artifacts)
    impact = build_impact_analysis(ctx)
    risk = build_risk_analysis(impact, ctx)
    return ctx, impact, risk


# ---------------------------------------------------------------------------
# Phase 4: structural impact from real import edges
# ---------------------------------------------------------------------------


def test_direct_dependents_become_confirmed_impact_findings():
    _ctx, impact, _risk = _analyze(_session_graph())
    auth = [
        f
        for f in impact.findings
        if f.affected_artifact == "src/auth.py" and f.relationship == RelationshipType.IMPACTS
    ]
    assert auth, "a file that imports the changed source must appear as impacted"
    assert auth[0].evidence_strength == EvidenceStrength.CONFIRMED
    assert auth[0].primary_evidence_type() == EvidenceType.DIRECT_EVIDENCE
    assert "imports" in auth[0].evidence[0].description


def test_transitive_dependents_are_marked_likely_not_confirmed():
    """The import chain is real; that the change propagates that far is not."""
    _ctx, impact, _risk = _analyze(_session_graph())
    api = [
        f
        for f in impact.findings
        if f.affected_artifact == "src/api.py" and f.relationship == RelationshipType.IMPACTS
    ]
    assert api, "a transitive dependent must still be surfaced"
    assert api[0].evidence_strength == EvidenceStrength.LIKELY
    assert "transitive" in api[0].evidence[0].description.lower()


def test_graph_test_associations_produce_tested_by_findings():
    _ctx, impact, _risk = _analyze(_session_graph(with_test=True))
    tested = [
        f
        for f in impact.findings
        if f.affected_artifact == "tests/test_session.py"
        and f.relationship == RelationshipType.TESTED_BY
    ]
    assert tested
    assert tested[0].primary_evidence_type() == EvidenceType.DIRECT_EVIDENCE


def test_no_structural_findings_without_a_graph():
    """Absent structural evidence, nothing is invented from filenames."""
    _ctx, impact, _risk = _analyze(None)
    structural = [
        f
        for f in impact.findings
        if f.primary_evidence_type() == EvidenceType.DIRECT_EVIDENCE
        and f.relationship in (RelationshipType.IMPACTS, RelationshipType.IMPORTS)
    ]
    assert structural == []


def test_failed_graph_degrades_instead_of_raising():
    broken = _graph([], [], error="Failed to clone repository")
    _ctx, impact, risk = _analyze(broken)
    assert impact.error is None
    assert risk.error is None


def test_files_absent_from_the_graph_are_never_seeded():
    """A relevant artifact the graph does not contain contributes no edges."""
    artifacts = [_keyword_artifact("src/not_in_graph.py")]
    _ctx, impact, _risk = _analyze(_session_graph(), artifacts)
    structural = [
        f for f in impact.findings if f.primary_evidence_type() == EvidenceType.DIRECT_EVIDENCE
    ]
    assert structural == []


# ---------------------------------------------------------------------------
# Phase 5: the description-only risk path
# ---------------------------------------------------------------------------


def test_description_only_change_now_produces_risks():
    """The headline fix: no changed_files supplied, yet real risks emerge."""
    ctx, _impact, risk = _analyze(_session_graph())
    assert all(a.reason != RelevanceReason.CHANGED_FILE for a in ctx.artifacts)
    assert risk.error is None
    assert risk.risks, "a description-only run must still surface risk"
    assert any(r.affected_artifacts == ("src/session.py",) for r in risk.risks)


def test_description_only_change_without_a_graph_still_produces_no_risk():
    """Without structural evidence the previous conservative behavior stands."""
    _ctx, _impact, risk = _analyze(None)
    assert risk.risks == []


def test_code_risk_severity_scales_with_real_dependent_count():
    _ctx, _impact, risk = _analyze(_session_graph())
    code = [r for r in risk.risks if r.category == RiskCategory.CODE]
    assert code
    # session.py has 2 transitive dependents: below the elevation threshold.
    assert code[0].severity == RiskSeverity.LOW


def test_wide_dependent_set_escalates_severity():
    session = _node("src/session.py")
    dependents = [_node(f"src/mod_{i}.py") for i in range(12)]
    edges = []
    for dep in dependents:
        edges.append(_edge(dep, session, RepositoryRelationshipType.IMPORTS))
        edges.append(_edge(session, dep, RepositoryRelationshipType.IMPORTED_BY))
    graph = _graph([session, *dependents], edges)

    _ctx, _impact, risk = _analyze(graph)
    code = [r for r in risk.risks if r.category == RiskCategory.CODE]
    assert code[0].severity == RiskSeverity.HIGH
    assert "12 file(s) depend on it" in code[0].explanation


def test_dependent_counts_are_cited_as_direct_evidence():
    _ctx, _impact, risk = _analyze(_session_graph())
    code = [r for r in risk.risks if r.category == RiskCategory.CODE][0]
    cited = [
        e
        for e in code.evidence
        if e.evidence_type == EvidenceType.DIRECT_EVIDENCE
        and "static import edges" in e.description
    ]
    assert cited, "a blast-radius claim must cite the import edges behind it"


def test_graph_test_association_prevents_a_false_test_gap():
    _ctx, _impact, risk = _analyze(_session_graph(with_test=True))
    gaps = [
        r
        for r in risk.risks
        if r.category == RiskCategory.TEST_GAP and "src/session.py" in r.affected_artifacts
    ]
    assert gaps == [], "a source with a real graph test association is not a test gap"


def test_uncovered_source_still_reports_a_test_gap():
    _ctx, _impact, risk = _analyze(_session_graph(with_test=False))
    gaps = [
        r
        for r in risk.risks
        if r.category == RiskCategory.TEST_GAP and "src/session.py" in r.affected_artifacts
    ]
    assert gaps


def test_declared_changed_files_keep_confirmed_evidence_strength():
    """Structural admission must not weaken the declared-file path."""
    declared = ContextArtifact(
        path="src/session.py",
        kind=ArtifactKind.SOURCE,
        reason=RelevanceReason.CHANGED_FILE,
        evidence="path appears in supplied changed_files",
        confidence="confirmed",
    )
    _ctx, _impact, risk = _analyze(_session_graph(), [declared])
    code = [r for r in risk.risks if r.category == RiskCategory.CODE][0]
    assert code.evidence_strength == EvidenceStrength.CONFIRMED
    assert "explicitly included" in code.explanation


def test_structurally_admitted_source_is_labelled_as_such():
    _ctx, _impact, risk = _analyze(_session_graph())
    code = [r for r in risk.risks if r.category == RiskCategory.CODE][0]
    assert code.evidence_strength == EvidenceStrength.LIKELY
    assert "identified as relevant" in code.explanation
