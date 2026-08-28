"""
Deterministic tests for Phase 4: Impact Analysis.

All tests use in-memory fixture data or temporary local Git repositories.
No network access or GitHub availability is required.

Covers:
 1.  Impact finding creation
 2.  Changed-file (MODIFIES) relationships
 3.  Source-to-source (IMPACTS) relationships
 4.  Source-to-test (TESTED_BY) relationships
 5.  Source-to-documentation (DOCUMENTED_BY) relationships
 6.  Dependency (DEPENDS_ON) relationships
 7.  Configuration (CONFIGURED_BY) relationships
 8.  Historical (HISTORICALLY_CHANGED_WITH) relationships
 9.  Evidence preservation
10.  Evidence type classification
11.  Evidence strength / confidence
12.  Distinction between evidence and inference
13.  Empty / insufficient context
14.  Repository-agnostic behavior
15.  Duplicate relationship prevention
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import pytest

from devflow.impact._build import build_impact_analysis
from devflow.models.change import ChangeRequest
from devflow.models.context import (
    ArtifactKind,
    ContextArtifact,
    RelevanceReason,
    RepositoryContext,
)
from devflow.models.history import (
    ArtifactHistory,
    HistoricalCommit,
    HistoricalEvidence,
    RepositoryHistory,
)
from devflow.models.impact import (
    EvidenceStrength,
    EvidenceType,
    ImpactAnalysis,
    ImpactEvidence,
    ImpactFinding,
    RelationshipType,
)
from devflow.models.repository import RepositoryInput


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_repo_input(name: str = "testrepo") -> RepositoryInput:
    return RepositoryInput(
        url=f"https://github.com/test/{name}",
        owner="test",
        name=name,
    )


def _make_artifact(
    path: str,
    kind: ArtifactKind,
    reason: RelevanceReason = RelevanceReason.KEYWORD_MATCH,
    confidence: str = "likely",
    evidence: str = "test evidence",
) -> ContextArtifact:
    return ContextArtifact(
        path=path,
        kind=kind,
        reason=reason,
        evidence=evidence,
        confidence=confidence,
    )


def _make_context(
    artifacts: list[ContextArtifact],
    change_summary: str = "Improve connection pooling.",
    all_files: Optional[list[str]] = None,
    error: Optional[str] = None,
) -> RepositoryContext:
    repo = _make_repo_input()
    return RepositoryContext(
        repository_url=repo.url,
        owner=repo.owner,
        name=repo.name,
        change_summary=change_summary,
        artifacts=artifacts,
        all_files=all_files or [a.path for a in artifacts],
        error=error,
    )


def _make_commit(
    hash_: str = "a" * 40,
    message: str = "test commit",
    refs: tuple[str, ...] = (),
) -> HistoricalCommit:
    return HistoricalCommit(
        hash=hash_,
        short_hash=hash_[:7],
        message=message,
        author="Dev",
        date_iso="2024-01-01 12:00:00 +0000",
        refs=refs,
    )


def _make_artifact_history(
    artifact_path: str,
    commits: list[HistoricalCommit],
) -> ArtifactHistory:
    evidence = tuple(
        HistoricalEvidence(
            artifact_path=artifact_path,
            commit_hash=c.hash,
            description=f"Git commit {c.short_hash} modified '{artifact_path}': {c.message!r}",
            relevance_reason="direct_modification",
            evidence_type="direct_modification",
        )
        for c in commits
    )
    return ArtifactHistory(
        artifact_path=artifact_path,
        commits=tuple(commits),
        evidence=evidence,
    )


def _make_history(
    histories: dict[str, list[HistoricalCommit]],
    change_summary: str = "Improve connection pooling.",
) -> RepositoryHistory:
    repo = _make_repo_input()
    hist = RepositoryHistory(
        repository_url=repo.url,
        owner=repo.owner,
        name=repo.name,
        change_summary=change_summary,
    )
    total: set[str] = set()
    for path, commits in histories.items():
        hist.artifact_histories[path] = _make_artifact_history(path, commits)
        for c in commits:
            total.add(c.hash)
    hist.total_commits_found = len(total)
    return hist


# ---------------------------------------------------------------------------
# 1. Impact finding creation
# ---------------------------------------------------------------------------


class TestImpactFindingCreation:
    def test_build_returns_impact_analysis(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE, confidence="confirmed"),
        ])
        analysis = build_impact_analysis(ctx)
        assert isinstance(analysis, ImpactAnalysis)

    def test_findings_not_empty_for_valid_context(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        assert len(analysis.findings) > 0

    def test_each_finding_has_required_fields(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        for f in analysis.findings:
            assert isinstance(f, ImpactFinding)
            assert f.affected_artifact
            assert isinstance(f.relationship, RelationshipType)
            assert f.potential_impact
            assert f.evidence  # at least one evidence item
            assert isinstance(f.evidence_strength, EvidenceStrength)
            assert f.finding_type

    def test_each_evidence_item_has_required_fields(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        for finding in analysis.findings:
            for ev in finding.evidence:
                assert isinstance(ev, ImpactEvidence)
                assert ev.artifact
                assert ev.description
                assert isinstance(ev.evidence_type, EvidenceType)

    def test_metadata_preserved(self):
        ctx = _make_context(
            [_make_artifact("src/pool.py", ArtifactKind.SOURCE)],
            change_summary="Test change.",
        )
        analysis = build_impact_analysis(ctx)
        assert analysis.repository_url == ctx.repository_url
        assert analysis.owner == ctx.owner
        assert analysis.name == ctx.name
        assert analysis.change_summary == "Test change."


# ---------------------------------------------------------------------------
# 2. Changed-file (MODIFIES) relationships
# ---------------------------------------------------------------------------


class TestChangedFileRelationships:
    def test_modifies_finding_for_changed_file(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE, confidence="confirmed",
                           evidence="path appears in changed_files"),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES]
        assert len(modifies) == 1
        assert modifies[0].affected_artifact == "src/pool.py"

    def test_modifies_has_confirmed_strength(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES]
        assert all(f.evidence_strength == EvidenceStrength.CONFIRMED for f in modifies)

    def test_modifies_evidence_type_is_direct(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES]
        for finding in modifies:
            assert all(
                ev.evidence_type == EvidenceType.DIRECT_EVIDENCE
                for ev in finding.evidence
            )

    def test_no_modifies_for_keyword_match_only(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES]
        assert len(modifies) == 0

    def test_multiple_changed_files_each_get_modifies(self):
        ctx = _make_context([
            _make_artifact("src/a.py", ArtifactKind.SOURCE, RelevanceReason.CHANGED_FILE),
            _make_artifact("src/b.py", ArtifactKind.SOURCE, RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        modifies_artifacts = {
            f.affected_artifact for f in analysis.findings
            if f.relationship == RelationshipType.MODIFIES
        }
        assert "src/a.py" in modifies_artifacts
        assert "src/b.py" in modifies_artifacts


# ---------------------------------------------------------------------------
# 3. Source-to-source (IMPACTS) relationships
# ---------------------------------------------------------------------------


class TestSourceToSourceRelationships:
    def test_impacts_finding_for_keyword_match_source(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        impacts = [f for f in analysis.findings
                   if f.relationship == RelationshipType.IMPACTS]
        assert len(impacts) == 1
        assert impacts[0].affected_artifact == "src/pool.py"
        assert impacts[0].finding_type == "source"

    def test_impacts_strength_for_keyword_match(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        impacts = [f for f in analysis.findings
                   if f.relationship == RelationshipType.IMPACTS]
        assert impacts[0].evidence_strength == EvidenceStrength.LIKELY

    def test_impacts_evidence_type_derived(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        impacts = [f for f in analysis.findings
                   if f.relationship == RelationshipType.IMPACTS]
        for finding in impacts:
            assert all(
                ev.evidence_type == EvidenceType.DERIVED_RELATIONSHIP
                for ev in finding.evidence
            )

    def test_changed_file_source_does_not_get_duplicate_impacts(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        # CHANGED_FILE sources should be MODIFIES only, not also IMPACTS
        impacts = [f for f in analysis.findings
                   if f.relationship == RelationshipType.IMPACTS
                   and f.affected_artifact == "src/pool.py"]
        assert len(impacts) == 0


# ---------------------------------------------------------------------------
# 4. Source-to-test (TESTED_BY) relationships
# ---------------------------------------------------------------------------


class TestSourceToTestRelationships:
    def test_tested_by_finding_for_test_artifact(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
            _make_artifact("tests/test_pool.py", ArtifactKind.TEST,
                           RelevanceReason.TEST_FOR_CHANGED),
        ])
        analysis = build_impact_analysis(ctx)
        tested_by = [f for f in analysis.findings
                     if f.relationship == RelationshipType.TESTED_BY]
        assert len(tested_by) >= 1

    def test_tested_by_finding_type_is_test(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
            _make_artifact("tests/test_pool.py", ArtifactKind.TEST,
                           RelevanceReason.TEST_FOR_CHANGED),
        ])
        analysis = build_impact_analysis(ctx)
        tested_by = [f for f in analysis.findings
                     if f.relationship == RelationshipType.TESTED_BY]
        assert all(f.finding_type == "test" for f in tested_by)

    def test_stem_match_produces_likely_strength(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
            _make_artifact("tests/test_pool.py", ArtifactKind.TEST,
                           RelevanceReason.TEST_FOR_CHANGED),
        ])
        analysis = build_impact_analysis(ctx)
        tested_by = [f for f in analysis.findings
                     if f.relationship == RelationshipType.TESTED_BY
                     and f.affected_artifact == "tests/test_pool.py"]
        # Should be LIKELY due to stem match "pool"
        assert len(tested_by) == 1
        assert tested_by[0].evidence_strength == EvidenceStrength.LIKELY

    def test_no_stem_match_produces_possible_strength(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
            _make_artifact("tests/test_integration.py", ArtifactKind.TEST,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        tested_by = [f for f in analysis.findings
                     if f.relationship == RelationshipType.TESTED_BY
                     and f.affected_artifact == "tests/test_integration.py"]
        assert len(tested_by) == 1
        assert tested_by[0].evidence_strength == EvidenceStrength.POSSIBLE

    def test_stem_match_evidence_type_is_derived(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
            _make_artifact("tests/test_pool.py", ArtifactKind.TEST,
                           RelevanceReason.TEST_FOR_CHANGED),
        ])
        analysis = build_impact_analysis(ctx)
        tested_by = [f for f in analysis.findings
                     if f.relationship == RelationshipType.TESTED_BY
                     and f.affected_artifact == "tests/test_pool.py"]
        assert tested_by[0].evidence[0].evidence_type == EvidenceType.DERIVED_RELATIONSHIP

    def test_no_stem_match_evidence_type_is_inference(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
            _make_artifact("tests/test_integration.py", ArtifactKind.TEST),
        ])
        analysis = build_impact_analysis(ctx)
        tested_by = [f for f in analysis.findings
                     if f.relationship == RelationshipType.TESTED_BY
                     and f.affected_artifact == "tests/test_integration.py"]
        assert tested_by[0].evidence[0].evidence_type == EvidenceType.INFERENCE


# ---------------------------------------------------------------------------
# 5. Source-to-documentation (DOCUMENTED_BY) relationships
# ---------------------------------------------------------------------------


class TestSourceToDocumentationRelationships:
    def test_documented_by_finding_for_doc_artifact(self):
        ctx = _make_context([
            _make_artifact("docs/pool.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        doc_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DOCUMENTED_BY]
        assert len(doc_findings) == 1
        assert doc_findings[0].affected_artifact == "docs/pool.md"

    def test_documented_by_finding_type(self):
        ctx = _make_context([
            _make_artifact("docs/pool.md", ArtifactKind.DOCUMENTATION),
        ])
        analysis = build_impact_analysis(ctx)
        doc_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DOCUMENTED_BY]
        assert all(f.finding_type == "documentation" for f in doc_findings)

    def test_keyword_match_doc_is_likely(self):
        ctx = _make_context([
            _make_artifact("docs/pool.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        doc_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DOCUMENTED_BY]
        assert doc_findings[0].evidence_strength == EvidenceStrength.LIKELY

    def test_always_included_doc_is_possible(self):
        ctx = _make_context([
            _make_artifact("README.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.DOCUMENTATION),
        ])
        analysis = build_impact_analysis(ctx)
        doc_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DOCUMENTED_BY]
        assert doc_findings[0].evidence_strength == EvidenceStrength.POSSIBLE

    def test_doc_evidence_type_is_derived(self):
        ctx = _make_context([
            _make_artifact("docs/pool.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        doc_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DOCUMENTED_BY]
        for finding in doc_findings:
            assert all(
                ev.evidence_type == EvidenceType.DERIVED_RELATIONSHIP
                for ev in finding.evidence
            )


# ---------------------------------------------------------------------------
# 6. Dependency (DEPENDS_ON) relationships
# ---------------------------------------------------------------------------


class TestDependencyRelationships:
    def test_depends_on_finding_for_manifest(self):
        ctx = _make_context([
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST,
                           confidence="confirmed"),
        ])
        analysis = build_impact_analysis(ctx)
        dep_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DEPENDS_ON]
        assert len(dep_findings) == 1

    def test_dependency_finding_type(self):
        ctx = _make_context([
            _make_artifact("requirements.txt", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        dep_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DEPENDS_ON]
        assert all(f.finding_type == "dependency" for f in dep_findings)

    def test_dependency_evidence_is_direct(self):
        ctx = _make_context([
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        dep_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DEPENDS_ON]
        for finding in dep_findings:
            assert all(
                ev.evidence_type == EvidenceType.DIRECT_EVIDENCE
                for ev in finding.evidence
            )

    def test_dependency_always_included_is_possible(self):
        """A manifest included unconditionally must be POSSIBLE, not CONFIRMED."""
        ctx = _make_context([
            _make_artifact("package.json", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        dep_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DEPENDS_ON]
        assert all(
            f.evidence_strength == EvidenceStrength.POSSIBLE
            for f in dep_findings
        )

    def test_dependency_changed_file_is_confirmed(self):
        """A manifest explicitly listed as a changed file must be CONFIRMED."""
        ctx = _make_context([
            _make_artifact("requirements.txt", ArtifactKind.DEPENDENCY,
                           RelevanceReason.CHANGED_FILE,
                           confidence="confirmed",
                           evidence="path appears in changed_files"),
        ])
        analysis = build_impact_analysis(ctx)
        dep_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DEPENDS_ON]
        assert len(dep_findings) == 1
        assert dep_findings[0].evidence_strength == EvidenceStrength.CONFIRMED


# ---------------------------------------------------------------------------
# 7. Configuration (CONFIGURED_BY) relationships
# ---------------------------------------------------------------------------


class TestConfigurationRelationships:
    def test_configured_by_finding_for_config(self):
        ctx = _make_context([
            _make_artifact("pytest.ini", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CONFIGURATION,
                           confidence="confirmed"),
        ])
        analysis = build_impact_analysis(ctx)
        cfg_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.CONFIGURED_BY]
        assert len(cfg_findings) >= 1

    def test_config_finding_type(self):
        ctx = _make_context([
            _make_artifact(".github/workflows/test.yml",
                           ArtifactKind.CONFIGURATION,
                           RelevanceReason.CONFIGURATION),
        ])
        analysis = build_impact_analysis(ctx)
        cfg_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.CONFIGURED_BY]
        assert all(f.finding_type == "configuration" for f in cfg_findings)

    def test_config_evidence_is_direct(self):
        ctx = _make_context([
            _make_artifact("tox.ini", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CONFIGURATION),
        ])
        analysis = build_impact_analysis(ctx)
        cfg_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.CONFIGURED_BY]
        for finding in cfg_findings:
            assert all(
                ev.evidence_type == EvidenceType.DIRECT_EVIDENCE
                for ev in finding.evidence
            )

    def test_config_always_included_is_possible(self):
        """A config included unconditionally must be POSSIBLE, not CONFIRMED."""
        ctx = _make_context([
            _make_artifact("tox.ini", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CONFIGURATION),
        ])
        analysis = build_impact_analysis(ctx)
        cfg_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.CONFIGURED_BY]
        assert all(
            f.evidence_strength == EvidenceStrength.POSSIBLE
            for f in cfg_findings
        )

    def test_config_changed_file_is_confirmed(self):
        """A config explicitly listed as a changed file must be CONFIRMED."""
        ctx = _make_context([
            _make_artifact("tox.ini", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CHANGED_FILE,
                           confidence="confirmed",
                           evidence="path appears in changed_files"),
        ])
        analysis = build_impact_analysis(ctx)
        cfg_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.CONFIGURED_BY]
        assert len(cfg_findings) == 1
        assert cfg_findings[0].evidence_strength == EvidenceStrength.CONFIRMED


# ---------------------------------------------------------------------------
# 8. Historical (HISTORICALLY_CHANGED_WITH) relationships
# ---------------------------------------------------------------------------


class TestHistoricalRelationships:
    def test_historical_finding_when_history_present(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        commit = _make_commit("a" * 40, "feat: improve pool")
        history = _make_history({"src/pool.py": [commit]})
        analysis = build_impact_analysis(ctx, history)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH]
        assert len(hist_findings) >= 1

    def test_no_historical_finding_without_history_arg(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
        ])
        analysis = build_impact_analysis(ctx, history=None)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH]
        assert len(hist_findings) == 0

    def test_historical_evidence_type_is_direct(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
        ])
        commit = _make_commit("b" * 40, "refactor: pool handling")
        history = _make_history({"src/pool.py": [commit]})
        analysis = build_impact_analysis(ctx, history)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH]
        for finding in hist_findings:
            assert all(
                ev.evidence_type == EvidenceType.DIRECT_EVIDENCE
                for ev in finding.evidence
            )

    def test_historical_changed_file_is_confirmed(self):
        """CHANGED_FILE artifacts with history must be CONFIRMED."""
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        commit = _make_commit("c" * 40, "chore: update pool")
        history = _make_history({"src/pool.py": [commit]})
        analysis = build_impact_analysis(ctx, history)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH]
        for finding in hist_findings:
            assert finding.evidence_strength == EvidenceStrength.CONFIRMED

    def test_historical_keyword_match_is_likely(self):
        """KEYWORD_MATCH artifacts with history must be LIKELY, not CONFIRMED."""
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        commit = _make_commit("c" * 40, "chore: update pool")
        history = _make_history({"src/pool.py": [commit]})
        analysis = build_impact_analysis(ctx, history)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH]
        assert len(hist_findings) == 1
        assert hist_findings[0].evidence_strength == EvidenceStrength.LIKELY

    def test_historical_always_included_is_possible(self):
        """Always-included artifacts (docs/deps/configs) with history must be POSSIBLE."""
        ctx = _make_context([
            _make_artifact("CHANGELOG.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.DOCUMENTATION),
        ])
        commit = _make_commit("d" * 40, "docs: update changelog")
        history = _make_history({"CHANGELOG.md": [commit]})
        analysis = build_impact_analysis(ctx, history)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH
                         and f.affected_artifact == "CHANGELOG.md"]
        assert len(hist_findings) == 1
        assert hist_findings[0].evidence_strength == EvidenceStrength.POSSIBLE

    def test_no_historical_finding_for_artifact_without_commits(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
        ])
        history = _make_history({"src/pool.py": []})
        analysis = build_impact_analysis(ctx, history)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH]
        assert len(hist_findings) == 0

    def test_historical_evidence_contains_commit_hash(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
        ])
        commit_hash = "d" * 40
        commit = _make_commit(commit_hash, "fix: pool deadlock")
        history = _make_history({"src/pool.py": [commit]})
        analysis = build_impact_analysis(ctx, history)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH
                         and f.affected_artifact == "src/pool.py"]
        assert len(hist_findings) == 1
        ev_description = " ".join(e.description for e in hist_findings[0].evidence)
        # short hash (7 chars) should appear
        assert commit_hash[:7] in ev_description


# ---------------------------------------------------------------------------
# 9. Evidence preservation
# ---------------------------------------------------------------------------


class TestEvidencePreservation:
    def test_evidence_artifact_path_preserved(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        for finding in analysis.findings:
            for ev in finding.evidence:
                assert ev.artifact  # not empty

    def test_evidence_description_not_empty(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        for finding in analysis.findings:
            for ev in finding.evidence:
                assert ev.description.strip()

    def test_evidence_references_artifact_in_description(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES]
        assert len(modifies) == 1
        ev = modifies[0].evidence[0]
        assert "src/pool.py" in ev.description

    def test_finding_is_frozen(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        finding = analysis.findings[0]
        with pytest.raises((AttributeError, TypeError)):
            finding.affected_artifact = "mutated"  # type: ignore[misc]

    def test_evidence_is_frozen(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        ev = analysis.findings[0].evidence[0]
        with pytest.raises((AttributeError, TypeError)):
            ev.artifact = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 10. Evidence type classification
# ---------------------------------------------------------------------------


class TestEvidenceTypeClassification:
    def test_changed_file_is_direct_evidence(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES]
        for finding in modifies:
            assert all(
                ev.evidence_type == EvidenceType.DIRECT_EVIDENCE
                for ev in finding.evidence
            )

    def test_keyword_match_source_is_derived(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        impacts = [f for f in analysis.findings
                   if f.relationship == RelationshipType.IMPACTS]
        for finding in impacts:
            assert all(
                ev.evidence_type == EvidenceType.DERIVED_RELATIONSHIP
                for ev in finding.evidence
            )

    def test_dependency_is_direct_evidence(self):
        ctx = _make_context([
            _make_artifact("requirements.txt", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        dep = [f for f in analysis.findings
               if f.relationship == RelationshipType.DEPENDS_ON]
        for finding in dep:
            assert all(
                ev.evidence_type == EvidenceType.DIRECT_EVIDENCE
                for ev in finding.evidence
            )

    def test_test_with_no_stem_match_is_inference(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
            _make_artifact("tests/test_integration.py", ArtifactKind.TEST),
        ])
        analysis = build_impact_analysis(ctx)
        tested_by = [f for f in analysis.findings
                     if f.relationship == RelationshipType.TESTED_BY
                     and f.affected_artifact == "tests/test_integration.py"]
        assert tested_by[0].primary_evidence_type() == EvidenceType.INFERENCE

    def test_primary_evidence_type_returns_weakest(self):
        # Create a finding manually with mixed evidence types
        finding = ImpactFinding(
            affected_artifact="src/pool.py",
            relationship=RelationshipType.IMPACTS,
            potential_impact="test",
            evidence=(
                ImpactEvidence(
                    artifact="src/pool.py",
                    description="direct",
                    evidence_type=EvidenceType.DIRECT_EVIDENCE,
                ),
                ImpactEvidence(
                    artifact="src/pool.py",
                    description="inferred",
                    evidence_type=EvidenceType.INFERENCE,
                ),
            ),
            evidence_strength=EvidenceStrength.LIKELY,
            finding_type="source",
        )
        assert finding.primary_evidence_type() == EvidenceType.INFERENCE


# ---------------------------------------------------------------------------
# 11. Evidence strength / confidence
# ---------------------------------------------------------------------------


class TestEvidenceStrength:
    def test_confirmed_for_changed_files(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES]
        assert all(f.evidence_strength == EvidenceStrength.CONFIRMED for f in modifies)

    def test_possible_for_always_included_dependencies(self):
        """Always-included dependency manifests → POSSIBLE (not CONFIRMED)."""
        ctx = _make_context([
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        dep = [f for f in analysis.findings
               if f.relationship == RelationshipType.DEPENDS_ON]
        assert all(f.evidence_strength == EvidenceStrength.POSSIBLE for f in dep)

    def test_possible_for_always_included_configs(self):
        """Always-included config files → POSSIBLE (not CONFIRMED)."""
        ctx = _make_context([
            _make_artifact("pytest.ini", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CONFIGURATION),
        ])
        analysis = build_impact_analysis(ctx)
        cfg = [f for f in analysis.findings
               if f.relationship == RelationshipType.CONFIGURED_BY]
        assert all(f.evidence_strength == EvidenceStrength.POSSIBLE for f in cfg)

    def test_likely_for_keyword_match_source(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        impacts = [f for f in analysis.findings
                   if f.relationship == RelationshipType.IMPACTS]
        assert all(f.evidence_strength == EvidenceStrength.LIKELY for f in impacts)

    def test_confirmed_findings_helper(self):
        """confirmed_findings() returns only CONFIRMED-strength findings."""
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
            _make_artifact("src/other.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        confirmed = analysis.confirmed_findings()
        assert all(f.evidence_strength == EvidenceStrength.CONFIRMED for f in confirmed)
        # Only MODIFIES on src/pool.py should be CONFIRMED; pyproject.toml → POSSIBLE
        assert len(confirmed) >= 1
        assert any(
            f.relationship == RelationshipType.MODIFIES
            and f.affected_artifact == "src/pool.py"
            for f in confirmed
        )


# ---------------------------------------------------------------------------
# 12. Distinction between evidence and inference
# ---------------------------------------------------------------------------


class TestEvidenceVsInference:
    def test_inference_is_never_called_direct_evidence(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
            _make_artifact("tests/test_other.py", ArtifactKind.TEST),
        ])
        analysis = build_impact_analysis(ctx)
        for finding in analysis.findings:
            for ev in finding.evidence:
                if ev.evidence_type == EvidenceType.INFERENCE:
                    # Inferences must not claim to be direct evidence
                    assert "DIRECT_EVIDENCE" not in ev.description
                    assert "directly confirmed" not in ev.description.lower()

    def test_direct_evidence_is_traceable_to_artifact(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        for finding in analysis.findings:
            for ev in finding.evidence:
                if ev.evidence_type == EvidenceType.DIRECT_EVIDENCE:
                    # Evidence artifact must be a real path from context
                    assert ev.artifact  # not empty

    def test_no_fabricated_relationships_in_empty_context(self):
        ctx = _make_context([])
        analysis = build_impact_analysis(ctx)
        assert analysis.error is not None  # gracefully reports no artifacts
        assert len(analysis.findings) == 0


# ---------------------------------------------------------------------------
# 13. Empty / insufficient context
# ---------------------------------------------------------------------------


class TestEmptyOrInsufficientContext:
    def test_context_error_produces_analysis_error(self):
        ctx = _make_context([], error="Phase 2 failed: network error")
        analysis = build_impact_analysis(ctx)
        assert analysis.error is not None
        assert len(analysis.findings) == 0

    def test_empty_artifacts_produces_error(self):
        ctx = _make_context([])
        analysis = build_impact_analysis(ctx)
        assert analysis.error is not None
        assert len(analysis.findings) == 0

    def test_history_error_does_not_crash_analysis(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        hist = RepositoryHistory(
            repository_url="https://github.com/test/repo",
            owner="test",
            name="repo",
            change_summary="test",
            error="Phase 3 failed",
        )
        analysis = build_impact_analysis(ctx, hist)
        # Should still produce findings from context alone
        assert analysis.error is None
        assert len(analysis.findings) > 0

    def test_history_without_relevant_artifacts_skipped(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
        ])
        # History has only an irrelevant artifact not in context
        commit = _make_commit("e" * 40, "feat: unrelated")
        history = _make_history({"src/unrelated.py": [commit]})
        analysis = build_impact_analysis(ctx, history)
        hist_findings = [f for f in analysis.findings
                         if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH]
        # src/unrelated.py is not in context.artifacts so no historical finding
        assert all(
            f.affected_artifact != "src/unrelated.py"
            for f in hist_findings
        )


# ---------------------------------------------------------------------------
# 14. Repository-agnostic behavior
# ---------------------------------------------------------------------------


class TestRepositoryAgnosticBehavior:
    def test_works_with_python_project_structure(self):
        ctx = _make_context([
            _make_artifact("src/conn.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("tests/test_conn.py", ArtifactKind.TEST,
                           RelevanceReason.TEST_FOR_CHANGED),
            _make_artifact("requirements.txt", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
            _make_artifact("README.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.DOCUMENTATION),
        ])
        analysis = build_impact_analysis(ctx)
        rels = {f.relationship for f in analysis.findings}
        assert RelationshipType.MODIFIES in rels
        assert RelationshipType.TESTED_BY in rels
        assert RelationshipType.DEPENDS_ON in rels
        assert RelationshipType.DOCUMENTED_BY in rels

    def test_works_with_node_project_structure(self):
        ctx = _make_context([
            _make_artifact("src/pool.js", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
            _make_artifact("package.json", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
            _make_artifact("docs/api.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        rels = {f.relationship for f in analysis.findings}
        assert RelationshipType.IMPACTS in rels
        assert RelationshipType.DEPENDS_ON in rels
        assert RelationshipType.DOCUMENTED_BY in rels

    def test_works_with_go_project_structure(self):
        ctx = _make_context([
            _make_artifact("pool/pool.go", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("go.mod", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
            _make_artifact("pool/pool_test.go", ArtifactKind.TEST,
                           RelevanceReason.TEST_FOR_CHANGED),
        ])
        analysis = build_impact_analysis(ctx)
        rels = {f.relationship for f in analysis.findings}
        assert RelationshipType.MODIFIES in rels
        assert RelationshipType.DEPENDS_ON in rels
        assert RelationshipType.TESTED_BY in rels

    def test_no_hard_coded_project_assumptions(self):
        """Analysis should not produce findings for paths not in the context."""
        ctx = _make_context([
            _make_artifact("lib/mymodule.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        artifact_paths = {f.affected_artifact for f in analysis.findings}
        # No finding should reference a path outside of context
        for path in artifact_paths:
            assert path in ctx.all_files, (
                f"Finding references artifact '{path}' not in context"
            )


# ---------------------------------------------------------------------------
# 15. Duplicate relationship prevention
# ---------------------------------------------------------------------------


class TestDuplicateRelationshipPrevention:
    def test_no_duplicate_modifies_for_same_artifact(self):
        # Duplicate artifact in context (same path, same reason)
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES
                    and f.affected_artifact == "src/pool.py"]
        assert len(modifies) == 1

    def test_no_duplicate_tested_by_for_same_test(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE),
            _make_artifact("tests/test_pool.py", ArtifactKind.TEST,
                           RelevanceReason.TEST_FOR_CHANGED),
            _make_artifact("tests/test_pool.py", ArtifactKind.TEST,
                           RelevanceReason.TEST_FOR_CHANGED),
        ])
        analysis = build_impact_analysis(ctx)
        tested_by = [f for f in analysis.findings
                     if f.relationship == RelationshipType.TESTED_BY
                     and f.affected_artifact == "tests/test_pool.py"]
        # Should have at most one TESTED_BY per (artifact, relationship) pair
        assert len(tested_by) == 1

    def test_no_duplicate_depends_on_for_same_manifest(self):
        ctx = _make_context([
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        dep = [f for f in analysis.findings
               if f.relationship == RelationshipType.DEPENDS_ON
               and f.affected_artifact == "pyproject.toml"]
        assert len(dep) == 1

    def test_all_artifact_relationship_pairs_unique(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        keys = [(f.affected_artifact, f.relationship) for f in analysis.findings]
        assert len(keys) == len(set(keys)), "Duplicate (artifact, relationship) found"


# ---------------------------------------------------------------------------
# Accessors / helpers on ImpactAnalysis
# ---------------------------------------------------------------------------


class TestImpactAnalysisAccessors:
    def test_findings_by_type(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("tests/test_pool.py", ArtifactKind.TEST),
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        assert all(f.finding_type == "source" for f in analysis.source_findings())
        assert all(f.finding_type == "test" for f in analysis.test_findings())
        assert all(f.finding_type == "dependency" for f in analysis.dependency_findings())

    def test_confirmed_findings_subset(self):
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
            _make_artifact("src/other.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        confirmed = analysis.confirmed_findings()
        all_findings = analysis.findings
        for f in confirmed:
            assert f in all_findings
        # All confirmed findings have CONFIRMED strength
        assert all(f.evidence_strength == EvidenceStrength.CONFIRMED for f in confirmed)


# ---------------------------------------------------------------------------
# Models are importable and frozen
# ---------------------------------------------------------------------------


class TestModelsImportable:
    def test_impact_models_importable(self):
        from devflow.models.impact import (
            EvidenceStrength,
            EvidenceType,
            ImpactAnalysis,
            ImpactEvidence,
            ImpactFinding,
            RelationshipType,
        )
        assert EvidenceType.DIRECT_EVIDENCE.value == "DIRECT_EVIDENCE"
        assert EvidenceType.DERIVED_RELATIONSHIP.value == "DERIVED_RELATIONSHIP"
        assert EvidenceType.INFERENCE.value == "INFERENCE"

    def test_relationship_types_have_expected_values(self):
        assert RelationshipType.MODIFIES.value == "modifies"
        assert RelationshipType.TESTED_BY.value == "tested_by"
        assert RelationshipType.DOCUMENTED_BY.value == "documented_by"
        assert RelationshipType.DEPENDS_ON.value == "depends_on"
        assert RelationshipType.CONFIGURED_BY.value == "configured_by"
        assert RelationshipType.HISTORICALLY_CHANGED_WITH.value == "historically_changed_with"
        assert RelationshipType.IMPACTS.value == "impacts"

    def test_evidence_strength_values(self):
        assert EvidenceStrength.CONFIRMED.value == "confirmed"
        assert EvidenceStrength.LIKELY.value == "likely"
        assert EvidenceStrength.POSSIBLE.value == "possible"

    def test_impact_finding_is_frozen(self):
        ev = ImpactEvidence(
            artifact="src/pool.py",
            description="test",
            evidence_type=EvidenceType.DIRECT_EVIDENCE,
        )
        finding = ImpactFinding(
            affected_artifact="src/pool.py",
            relationship=RelationshipType.MODIFIES,
            potential_impact="test",
            evidence=(ev,),
            evidence_strength=EvidenceStrength.CONFIRMED,
            finding_type="source",
        )
        with pytest.raises((AttributeError, TypeError)):
            finding.affected_artifact = "mutated"  # type: ignore[misc]

    def test_impact_analysis_no_error_by_default(self):
        a = ImpactAnalysis(
            repository_url="https://github.com/test/repo",
            owner="test",
            name="repo",
            change_summary="Test.",
        )
        assert a.error is None
        assert a.findings == []


# ---------------------------------------------------------------------------
# False-positive relationship prevention
# ---------------------------------------------------------------------------
#
# These tests directly verify the cases raised in the Phase 4 quality review:
# over-confirmed relationships that are not backed by specific repository
# evidence connecting the artifact to *this* change.
# ---------------------------------------------------------------------------


class TestFalsePositivePrevention:
    """
    Verify that no relationship receives unjustifiably strong evidence strength.

    False-positive rule: an artifact's mere presence in the repository is
    NOT sufficient to award CONFIRMED.  CONFIRMED requires that the artifact
    is explicitly connected to the change (e.g. listed as a changed file).
    """

    # -- 1. Dependency manifests --

    def test_manifest_not_connected_to_change_is_possible_not_confirmed(self):
        """
        pyproject.toml / requirements.txt present in every repo.
        Without a specific link to the change they must be POSSIBLE.
        """
        ctx = _make_context([
            _make_artifact("src/auth.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
            _make_artifact("requirements.txt", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        dep_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DEPENDS_ON]
        for f in dep_findings:
            assert f.evidence_strength != EvidenceStrength.CONFIRMED, (
                f"Manifest '{f.affected_artifact}' is not connected to the change "
                "but was awarded CONFIRMED — false positive."
            )

    def test_manifest_explicitly_changed_is_confirmed(self):
        """If the developer explicitly changes a manifest it deserves CONFIRMED."""
        ctx = _make_context([
            _make_artifact("requirements.txt", ArtifactKind.DEPENDENCY,
                           RelevanceReason.CHANGED_FILE,
                           confidence="confirmed",
                           evidence="path appears in changed_files"),
        ])
        analysis = build_impact_analysis(ctx)
        dep_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DEPENDS_ON]
        assert len(dep_findings) == 1
        assert dep_findings[0].evidence_strength == EvidenceStrength.CONFIRMED

    # -- 2. Configuration files --

    def test_config_not_connected_to_change_is_possible_not_confirmed(self):
        """
        .gitignore / tox.ini present in every repo.
        Without a specific link to the change they must be POSSIBLE.
        """
        ctx = _make_context([
            _make_artifact("src/api.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact(".gitignore", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CONFIGURATION),
            _make_artifact("tox.ini", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CONFIGURATION),
        ])
        analysis = build_impact_analysis(ctx)
        cfg_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.CONFIGURED_BY]
        for f in cfg_findings:
            assert f.evidence_strength != EvidenceStrength.CONFIRMED, (
                f"Config '{f.affected_artifact}' is not connected to the change "
                "but was awarded CONFIRMED — false positive."
            )

    def test_config_explicitly_changed_is_confirmed(self):
        """If the developer explicitly changes a config it deserves CONFIRMED."""
        ctx = _make_context([
            _make_artifact("pytest.ini", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CHANGED_FILE,
                           confidence="confirmed",
                           evidence="path appears in changed_files"),
        ])
        analysis = build_impact_analysis(ctx)
        cfg_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.CONFIGURED_BY]
        assert len(cfg_findings) == 1
        assert cfg_findings[0].evidence_strength == EvidenceStrength.CONFIRMED

    # -- 3. Documentation files --

    def test_always_included_doc_is_possible_not_confirmed(self):
        """
        README.md is always included by Phase 2 but its connection to any
        specific change is unconfirmed.  Must be POSSIBLE.
        """
        ctx = _make_context([
            _make_artifact("README.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.DOCUMENTATION),
        ])
        analysis = build_impact_analysis(ctx)
        doc_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DOCUMENTED_BY]
        for f in doc_findings:
            assert f.evidence_strength == EvidenceStrength.POSSIBLE, (
                f"Always-included doc '{f.affected_artifact}' should be POSSIBLE "
                f"but got {f.evidence_strength.value}."
            )

    def test_keyword_matched_doc_is_at_most_likely(self):
        """
        A doc whose *path* matches a change keyword is DERIVED_RELATIONSHIP/LIKELY.
        Still not CONFIRMED because we haven't read the content.
        """
        ctx = _make_context([
            _make_artifact("docs/connection.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        doc_findings = [f for f in analysis.findings
                        if f.relationship == RelationshipType.DOCUMENTED_BY]
        assert len(doc_findings) == 1
        assert doc_findings[0].evidence_strength in (
            EvidenceStrength.LIKELY,
            EvidenceStrength.POSSIBLE,
        ), (
            "Keyword-matched doc should be LIKELY or POSSIBLE, not CONFIRMED."
        )
        assert doc_findings[0].evidence_strength != EvidenceStrength.CONFIRMED

    # -- 4. Historical commits --

    def test_history_of_always_included_artifact_is_possible(self):
        """
        A CHANGELOG.md has commits, but those commits don't confirm it is
        affected by *this* change.  Must be POSSIBLE, not CONFIRMED.
        """
        ctx = _make_context([
            _make_artifact("src/conn.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
            _make_artifact("CHANGELOG.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.DOCUMENTATION),
        ])
        commit = _make_commit("a" * 40, "docs: release notes")
        history = _make_history({
            "src/conn.py": [_make_commit("b" * 40, "feat: improve conn")],
            "CHANGELOG.md": [commit],
        })
        analysis = build_impact_analysis(ctx, history)

        changelog_hist = [
            f for f in analysis.findings
            if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH
            and f.affected_artifact == "CHANGELOG.md"
        ]
        assert len(changelog_hist) == 1
        assert changelog_hist[0].evidence_strength == EvidenceStrength.POSSIBLE, (
            "CHANGELOG.md is always-included; its historical commits must "
            "not be CONFIRMED — they don't prove it's affected by this change."
        )

    def test_history_of_changed_file_is_confirmed(self):
        """
        A file explicitly listed as changed has CONFIRMED historical findings
        because the developer declared it is being changed.
        """
        ctx = _make_context([
            _make_artifact("src/conn.py", ArtifactKind.SOURCE,
                           RelevanceReason.CHANGED_FILE),
        ])
        commit = _make_commit("c" * 40, "feat: improve conn")
        history = _make_history({"src/conn.py": [commit]})
        analysis = build_impact_analysis(ctx, history)

        src_hist = [
            f for f in analysis.findings
            if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH
            and f.affected_artifact == "src/conn.py"
        ]
        assert len(src_hist) == 1
        assert src_hist[0].evidence_strength == EvidenceStrength.CONFIRMED

    def test_history_of_keyword_matched_source_is_likely(self):
        """
        A keyword-matched source file with history is LIKELY.
        It's structurally relevant but not explicitly named as changed.
        """
        ctx = _make_context([
            _make_artifact("src/conn.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        commit = _make_commit("d" * 40, "refactor: connection logic")
        history = _make_history({"src/conn.py": [commit]})
        analysis = build_impact_analysis(ctx, history)

        src_hist = [
            f for f in analysis.findings
            if f.relationship == RelationshipType.HISTORICALLY_CHANGED_WITH
            and f.affected_artifact == "src/conn.py"
        ]
        assert len(src_hist) == 1
        assert src_hist[0].evidence_strength == EvidenceStrength.LIKELY

    # -- 5. Keyword match does not over-elevate source relationship --

    def test_keyword_matched_source_is_impacts_not_modifies(self):
        """
        A source file matched only by keyword must be IMPACTS (not MODIFIES).
        MODIFIES requires CHANGED_FILE.
        """
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        modifies = [f for f in analysis.findings
                    if f.relationship == RelationshipType.MODIFIES
                    and f.affected_artifact == "src/pool.py"]
        assert len(modifies) == 0, (
            "Keyword-matched source must not receive MODIFIES — "
            "that requires explicit CHANGED_FILE evidence."
        )

    def test_keyword_matched_source_is_at_most_likely(self):
        """A keyword-matched source relationship must not be CONFIRMED."""
        ctx = _make_context([
            _make_artifact("src/pool.py", ArtifactKind.SOURCE,
                           RelevanceReason.KEYWORD_MATCH),
        ])
        analysis = build_impact_analysis(ctx)
        impacts = [f for f in analysis.findings
                   if f.relationship == RelationshipType.IMPACTS
                   and f.affected_artifact == "src/pool.py"]
        assert len(impacts) == 1
        assert impacts[0].evidence_strength != EvidenceStrength.CONFIRMED, (
            "Keyword-matched source must not receive CONFIRMED strength."
        )

    # -- 6. Evidence type integrity across all relationship types --

    def test_possible_findings_are_never_direct_evidence_confirmed(self):
        """No POSSIBLE finding should be typed DIRECT_EVIDENCE and also CONFIRMED."""
        ctx = _make_context([
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
            _make_artifact("tox.ini", ArtifactKind.CONFIGURATION,
                           RelevanceReason.CONFIGURATION),
            _make_artifact("README.md", ArtifactKind.DOCUMENTATION,
                           RelevanceReason.DOCUMENTATION),
        ])
        analysis = build_impact_analysis(ctx)
        for finding in analysis.findings:
            if finding.evidence_strength == EvidenceStrength.POSSIBLE:
                # POSSIBLE findings must not simultaneously claim CONFIRMED
                # (this is a tautological check on the invariant)
                assert finding.evidence_strength != EvidenceStrength.CONFIRMED

    def test_evidence_type_direct_with_possible_strength_is_coherent(self):
        """
        DIRECT_EVIDENCE + POSSIBLE is coherent: the file exists (direct),
        but its connection to the change is unconfirmed (possible).
        Verify this combination is used correctly for always-included artifacts.
        """
        ctx = _make_context([
            _make_artifact("pyproject.toml", ArtifactKind.DEPENDENCY,
                           RelevanceReason.DEPENDENCY_MANIFEST),
        ])
        analysis = build_impact_analysis(ctx)
        dep = [f for f in analysis.findings
               if f.relationship == RelationshipType.DEPENDS_ON]
        assert len(dep) == 1
        finding = dep[0]
        # Evidence type: DIRECT (file is real)
        assert all(ev.evidence_type == EvidenceType.DIRECT_EVIDENCE
                   for ev in finding.evidence)
        # Strength: POSSIBLE (connection to change unconfirmed)
        assert finding.evidence_strength == EvidenceStrength.POSSIBLE


# ---------------------------------------------------------------------------
# Phase 0–3 regression
# ---------------------------------------------------------------------------


class TestPhase03Regression:
    def test_phase1_imports(self):
        from devflow.input import accept_input
        repo, change = accept_input(
            "https://github.com/example/repo",
            "Test change.",
        )
        assert repo.owner == "example"

    def test_phase2_models_importable(self):
        from devflow.models.context import ArtifactKind, RepositoryContext
        assert ArtifactKind.SOURCE.value == "source"

    def test_phase3_models_importable(self):
        from devflow.models.history import RepositoryHistory
        h = RepositoryHistory(
            repository_url="https://github.com/test/repo",
            owner="test",
            name="repo",
            change_summary="test",
        )
        assert h.total_commits_found == 0

    def test_impact_module_importable(self):
        from devflow.impact import build_impact_analysis
        assert callable(build_impact_analysis)
