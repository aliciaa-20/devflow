"""
DevFlow Phase 4 — Impact Analysis.

Public entry point: build_impact_analysis()

Consumes:
  - RepositoryContext  produced by Phase 2
  - RepositoryHistory  produced by Phase 3  (optional, may be None)

Produces:
  - ImpactAnalysis  containing structured, evidence-backed ImpactFindings

Analysis strategy
-----------------
Phase 2 already identified the relevant artifacts.  Phase 4 does NOT
re-scan the entire repository.  It uses the structured context to:

  1. Record MODIFIES relationships for explicitly changed files.
  2. Record source-to-source IMPACTS relationships for relevant source
     files identified by Phase 2 (keyword / path-overlap evidence).
  3. Record TESTED_BY relationships by matching test artifact names to
     source artifact names (name-stem overlap — deterministic, no content
     read required).
  4. Record DOCUMENTED_BY relationships from documentation artifacts in
     the Phase 2 context (keyword / path-overlap evidence).
  5. Record DEPENDS_ON relationships from dependency manifest artifacts
     in the Phase 2 context.
  6. Record CONFIGURED_BY relationships from configuration artifacts in
     the Phase 2 context.
  7. Record HISTORICALLY_CHANGED_WITH relationships for artifacts that
     Phase 3 found co-changed with relevant source files.

Evidence-strength policy
------------------------
The strength of a finding reflects how firmly repository evidence
connects the artifact to *this specific change* — not merely whether
the artifact exists in the repository.

CONFIRMED  — the artifact is directly named in the change (CHANGED_FILE),
             or the relationship is proven by content (e.g. a real git
             commit hash that modifies this file, a test file whose name
             matches a changed-file stem exactly).

LIKELY     — the relationship is strongly suggested by structural evidence
             (e.g. keyword overlap in a source or test path, a test whose
             stem matches a relevant source, a manifest or config that was
             modified in the same git commits as a relevant source file).

POSSIBLE   — the artifact is included because it exists in the repository
             and is always considered relevant (e.g. every dependency
             manifest, every config file, every doc file) but no specific
             repository evidence connects it to the change.

This policy prevents CONFIRMED being awarded merely because a file
exists in the repository, which would conflate "file present" with
"file proven to be affected by this change".

No AI/LLM calls.  No fabrication.  No external network access.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from devflow.models.context import (
    ArtifactKind,
    ContextArtifact,
    RelevanceReason,
    RepositoryContext,
)
from devflow.models.history import RepositoryHistory
from devflow.models.impact import (
    EvidenceStrength,
    EvidenceType,
    ImpactAnalysis,
    ImpactEvidence,
    ImpactFinding,
    RelationshipType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_impact_analysis(
    context: RepositoryContext,
    history: Optional[RepositoryHistory] = None,
) -> ImpactAnalysis:
    """
    Produce structured impact findings for the change described in *context*.

    Args:
        context: RepositoryContext produced by Phase 2.
        history: RepositoryHistory produced by Phase 3 (optional).
                 If None, historical findings are skipped.

    Returns:
        ImpactAnalysis with all findings and metadata.
        If context.error is set, returns an ImpactAnalysis with .error set
        and no findings.
    """
    analysis = ImpactAnalysis(
        repository_url=context.repository_url,
        owner=context.owner,
        name=context.name,
        change_summary=context.change_summary,
    )

    if context.error:
        analysis.error = (
            f"Skipped: Phase 2 context had an error: {context.error}"
        )
        return analysis

    if not context.artifacts:
        analysis.error = "No relevant artifacts in context; impact analysis cannot proceed."
        return analysis

    try:
        findings = _analyse(context, history)
        # Deduplicate by (artifact, relationship) key.
        analysis.findings = _deduplicate(findings)
        # Sort: confirmed first, then likely, then possible.
        analysis.findings.sort(key=_finding_sort_key)

        logger.info(
            "Impact analysis: %d findings produced for '%s'",
            len(analysis.findings),
            context.change_summary[:60],
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during impact analysis")
        analysis.error = f"Impact analysis failed: {exc}"

    return analysis


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def _analyse(
    context: RepositoryContext,
    history: Optional[RepositoryHistory],
) -> list[ImpactFinding]:
    findings: list[ImpactFinding] = []

    # 1. MODIFIES — explicitly changed files from the ChangeRequest
    findings.extend(_changed_file_findings(context))

    # 2. SOURCE IMPACTS — relevant source files from Phase 2
    findings.extend(_source_impact_findings(context))

    # 3. TESTED_BY — test artifacts whose name stem overlaps a source artifact
    findings.extend(_test_findings(context))

    # 4. DOCUMENTED_BY — documentation artifacts
    findings.extend(_documentation_findings(context))

    # 5. DEPENDS_ON — dependency manifest artifacts
    findings.extend(_dependency_findings(context))

    # 6. CONFIGURED_BY — configuration artifacts
    findings.extend(_configuration_findings(context))

    # 7. HISTORICALLY_CHANGED_WITH — from Phase 3 history
    if history and not history.error:
        findings.extend(_historical_findings(context, history))

    return findings


# ---------------------------------------------------------------------------
# 1. Changed file findings (MODIFIES — DIRECT_EVIDENCE)
# ---------------------------------------------------------------------------


def _changed_file_findings(context: RepositoryContext) -> list[ImpactFinding]:
    """
    Produce a MODIFIES finding for every artifact whose reason is CHANGED_FILE.

    These are files the developer explicitly declared as changed.  Evidence
    is DIRECT_EVIDENCE; strength is CONFIRMED.
    """
    findings: list[ImpactFinding] = []
    for artifact in context.artifacts:
        if artifact.reason != RelevanceReason.CHANGED_FILE:
            continue

        ev = ImpactEvidence(
            artifact=artifact.path,
            description=(
                f"File '{artifact.path}' is listed as a changed file in the "
                "change request (DIRECT_EVIDENCE: changed_files input)."
            ),
            evidence_type=EvidenceType.DIRECT_EVIDENCE,
        )
        finding = ImpactFinding(
            affected_artifact=artifact.path,
            relationship=RelationshipType.MODIFIES,
            potential_impact=(
                f"The change directly modifies '{artifact.path}'. "
                "All consumers of this file may be affected."
            ),
            evidence=(ev,),
            evidence_strength=EvidenceStrength.CONFIRMED,
            finding_type=_artifact_finding_type(artifact),
        )
        findings.append(finding)
        logger.debug("MODIFIES finding: %s", artifact.path)

    return findings


# ---------------------------------------------------------------------------
# 2. Source impact findings (IMPACTS — DERIVED_RELATIONSHIP or INFERENCE)
# ---------------------------------------------------------------------------


def _source_impact_findings(context: RepositoryContext) -> list[ImpactFinding]:
    """
    Produce IMPACTS findings for relevant source artifacts discovered by Phase 2
    that are NOT already CHANGED_FILE.

    - Keyword-match evidence → DERIVED_RELATIONSHIP / likely
    - Entry point evidence → DERIVED_RELATIONSHIP / likely
    - All others → INFERENCE / possible
    """
    findings: list[ImpactFinding] = []
    for artifact in context.relevant_sources():
        if artifact.reason == RelevanceReason.CHANGED_FILE:
            continue  # already covered by MODIFIES

        evidence_type, strength = _source_evidence_classification(artifact)

        ev = ImpactEvidence(
            artifact=artifact.path,
            description=(
                f"Phase 2 identified '{artifact.path}' as relevant "
                f"(reason: {artifact.reason.value}; confidence: {artifact.confidence}). "
                f"Evidence: {artifact.evidence}"
            ),
            evidence_type=evidence_type,
        )
        finding = ImpactFinding(
            affected_artifact=artifact.path,
            relationship=RelationshipType.IMPACTS,
            potential_impact=(
                f"Source file '{artifact.path}' may be affected by the change "
                f"('{context.change_summary[:80]}')."
            ),
            evidence=(ev,),
            evidence_strength=strength,
            finding_type="source",
        )
        findings.append(finding)
        logger.debug("IMPACTS finding: %s", artifact.path)

    return findings


def _source_evidence_classification(
    artifact: ContextArtifact,
) -> tuple[EvidenceType, EvidenceStrength]:
    """Map Phase 2 relevance reason to Phase 4 evidence type + strength."""
    if artifact.reason in (
        RelevanceReason.KEYWORD_MATCH,
        RelevanceReason.ENTRY_POINT,
    ):
        return EvidenceType.DERIVED_RELATIONSHIP, EvidenceStrength.LIKELY
    # TEST_FOR_CHANGED, DEPENDENCY_MANIFEST, CONFIGURATION, DOCUMENTATION
    # are handled in their dedicated sections; if they appear as SOURCE,
    # treat as inference.
    return EvidenceType.INFERENCE, EvidenceStrength.POSSIBLE


# ---------------------------------------------------------------------------
# 3. Test findings (TESTED_BY — DERIVED_RELATIONSHIP)
# ---------------------------------------------------------------------------

# Stem fragments that indicate a test file names a specific module.
# e.g. test_connection.py → "connection", test_pooling.py → "pooling"


def _test_findings(context: RepositoryContext) -> list[ImpactFinding]:
    """
    For each relevant test artifact in Phase 2 context, produce a TESTED_BY
    finding linked to source artifacts whose name-stem appears in the test
    path.

    Matching is purely structural (path stems).  No file content is read.
    Evidence type: DERIVED_RELATIONSHIP.  Strength: LIKELY if the stem
    matches a known source artifact; POSSIBLE otherwise.
    """
    findings: list[ImpactFinding] = []
    source_stems = _build_source_stem_map(context)

    for test_artifact in context.relevant_tests():
        # Determine which source files this test is likely covering.
        matched_sources = _match_test_to_sources(test_artifact.path, source_stems)

        if matched_sources:
            for source_path in matched_sources:
                ev = ImpactEvidence(
                    artifact=test_artifact.path,
                    description=(
                        f"Test file '{test_artifact.path}' name-stem matches "
                        f"source file '{source_path}' (DERIVED_RELATIONSHIP: "
                        "test filename overlaps source module name)."
                    ),
                    evidence_type=EvidenceType.DERIVED_RELATIONSHIP,
                )
                finding = ImpactFinding(
                    affected_artifact=test_artifact.path,
                    relationship=RelationshipType.TESTED_BY,
                    potential_impact=(
                        f"Test '{test_artifact.path}' is structurally associated with "
                        f"source '{source_path}' and may need to be updated or "
                        "re-run after the change."
                    ),
                    evidence=(ev,),
                    evidence_strength=EvidenceStrength.LIKELY,
                    finding_type="test",
                )
                findings.append(finding)
        else:
            # Test is relevant (Phase 2 included it) but no stem match found.
            ev = ImpactEvidence(
                artifact=test_artifact.path,
                description=(
                    f"Test file '{test_artifact.path}' was identified as relevant "
                    f"by Phase 2 (reason: {test_artifact.reason.value}). "
                    "No source-stem match found; relationship is inferred."
                ),
                evidence_type=EvidenceType.INFERENCE,
            )
            finding = ImpactFinding(
                affected_artifact=test_artifact.path,
                relationship=RelationshipType.TESTED_BY,
                potential_impact=(
                    f"Test '{test_artifact.path}' may need review after the change."
                ),
                evidence=(ev,),
                evidence_strength=EvidenceStrength.POSSIBLE,
                finding_type="test",
            )
            findings.append(finding)

        logger.debug("TESTED_BY finding: %s", test_artifact.path)

    return findings


def _build_source_stem_map(context: RepositoryContext) -> dict[str, str]:
    """
    Build a map from lowercased file stem → full path for all relevant source
    artifacts (including those in all_files if they are source-like).
    """
    stem_map: dict[str, str] = {}
    for artifact in context.relevant_sources():
        stem = Path(artifact.path).stem.lower()
        if stem not in stem_map:
            stem_map[stem] = artifact.path
    return stem_map


def _match_test_to_sources(
    test_path: str, source_stems: dict[str, str]
) -> list[str]:
    """
    Return source paths whose stem appears in the test file name.

    Strategy: strip common test prefixes/suffixes from the test filename
    stem and check if the result matches any source stem.

    e.g.  test_connection.py  → "connection" → matches connection.py
          connection_test.py  → "connection" → matches connection.py
    """
    test_stem = Path(test_path).stem.lower()

    # Strip common affixes
    candidate = test_stem
    for prefix in ("test_", "test-"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):]
            break
    for suffix in ("_test", "-test", "_spec", "-spec"):
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)]
            break

    matched = []
    if candidate and candidate in source_stems:
        matched.append(source_stems[candidate])

    # Also check if any source stem is a substring of the test path
    # (e.g. tests/test_connection_pool.py may relate to _pool.py)
    # Only do this for the test filename, not directory components.
    test_filename_lower = Path(test_path).name.lower()
    for stem, src_path in source_stems.items():
        if stem != candidate and len(stem) >= 4 and stem in test_filename_lower:
            if src_path not in matched:
                matched.append(src_path)

    return matched


# ---------------------------------------------------------------------------
# 4. Documentation findings (DOCUMENTED_BY — DERIVED_RELATIONSHIP)
# ---------------------------------------------------------------------------


def _documentation_findings(context: RepositoryContext) -> list[ImpactFinding]:
    """
    For each relevant documentation artifact in the Phase 2 context, produce
    a DOCUMENTED_BY finding.

    Evidence type: DERIVED_RELATIONSHIP (path-based classification).
    Strength: LIKELY for keyword-match docs; POSSIBLE for always-included docs.
    """
    findings: list[ImpactFinding] = []
    for artifact in context.relevant_docs():
        if artifact.reason == RelevanceReason.KEYWORD_MATCH:
            ev_type = EvidenceType.DERIVED_RELATIONSHIP
            strength = EvidenceStrength.LIKELY
        else:
            ev_type = EvidenceType.DERIVED_RELATIONSHIP
            strength = EvidenceStrength.POSSIBLE

        ev = ImpactEvidence(
            artifact=artifact.path,
            description=(
                f"Documentation file '{artifact.path}' was identified as relevant "
                f"by Phase 2 (reason: {artifact.reason.value}; "
                f"evidence: {artifact.evidence})."
            ),
            evidence_type=ev_type,
        )
        finding = ImpactFinding(
            affected_artifact=artifact.path,
            relationship=RelationshipType.DOCUMENTED_BY,
            potential_impact=(
                f"Documentation '{artifact.path}' may describe the affected "
                "functionality and may need to be updated."
            ),
            evidence=(ev,),
            evidence_strength=strength,
            finding_type="documentation",
        )
        findings.append(finding)
        logger.debug("DOCUMENTED_BY finding: %s", artifact.path)

    return findings


# ---------------------------------------------------------------------------
# 5. Dependency findings (DEPENDS_ON)
# ---------------------------------------------------------------------------


def _dependency_findings(context: RepositoryContext) -> list[ImpactFinding]:
    """
    For each dependency manifest in the Phase 2 context, produce a DEPENDS_ON
    finding.

    Evidence type: DIRECT_EVIDENCE — the manifest file is a real repository
    artifact.

    Strength:
    - CONFIRMED  when the manifest was explicitly listed as a changed file.
    - POSSIBLE   when the manifest is always-included (present in every repo
                 inspection) but no specific evidence connects it to this
                 change.

    Rationale: a manifest's *existence* is direct evidence, but its
    connection to *this particular change* is not confirmed merely because
    the file is present.  Awarding CONFIRMED to every manifest would
    over-state certainty.
    """
    findings: list[ImpactFinding] = []
    for artifact in context.relevant_dependencies():
        if artifact.reason == RelevanceReason.CHANGED_FILE:
            strength = EvidenceStrength.CONFIRMED
            connection = "explicitly listed as a changed file"
        else:
            strength = EvidenceStrength.POSSIBLE
            connection = (
                "present in the repository (always included in context; "
                "no specific evidence connects it to this change)"
            )

        ev = ImpactEvidence(
            artifact=artifact.path,
            description=(
                f"Dependency manifest '{artifact.path}' is {connection}. "
                "(DIRECT_EVIDENCE: file identified by Phase 2 context.)"
            ),
            evidence_type=EvidenceType.DIRECT_EVIDENCE,
        )
        finding = ImpactFinding(
            affected_artifact=artifact.path,
            relationship=RelationshipType.DEPENDS_ON,
            potential_impact=(
                f"Dependency manifest '{artifact.path}' defines project dependencies "
                "that may be relevant to the change."
            ),
            evidence=(ev,),
            evidence_strength=strength,
            finding_type="dependency",
        )
        findings.append(finding)
        logger.debug("DEPENDS_ON finding: %s (strength=%s)", artifact.path, strength.value)

    return findings


# ---------------------------------------------------------------------------
# 6. Configuration findings (CONFIGURED_BY)
# ---------------------------------------------------------------------------


def _configuration_findings(context: RepositoryContext) -> list[ImpactFinding]:
    """
    For each configuration artifact in the Phase 2 context, produce a
    CONFIGURED_BY finding.

    Evidence type: DIRECT_EVIDENCE — the config file is a real repository
    artifact.

    Strength:
    - CONFIRMED  when the config was explicitly listed as a changed file.
    - POSSIBLE   when the config is always-included but no specific evidence
                 connects it to this change.

    Rationale: a config file's existence does not confirm it governs the
    specific behavior being changed.  The file is real (DIRECT_EVIDENCE),
    but the connection to the change is unconfirmed.
    """
    findings: list[ImpactFinding] = []
    for artifact in context.relevant_configs():
        if artifact.reason == RelevanceReason.CHANGED_FILE:
            strength = EvidenceStrength.CONFIRMED
            connection = "explicitly listed as a changed file"
        else:
            strength = EvidenceStrength.POSSIBLE
            connection = (
                "present in the repository (always included in context; "
                "no specific evidence connects it to this change)"
            )

        ev = ImpactEvidence(
            artifact=artifact.path,
            description=(
                f"Configuration file '{artifact.path}' is {connection}. "
                "(DIRECT_EVIDENCE: file identified by Phase 2 context.)"
            ),
            evidence_type=EvidenceType.DIRECT_EVIDENCE,
        )
        finding = ImpactFinding(
            affected_artifact=artifact.path,
            relationship=RelationshipType.CONFIGURED_BY,
            potential_impact=(
                f"Configuration file '{artifact.path}' may govern behavior "
                "relevant to the change."
            ),
            evidence=(ev,),
            evidence_strength=strength,
            finding_type="configuration",
        )
        findings.append(finding)
        logger.debug("CONFIGURED_BY finding: %s (strength=%s)", artifact.path, strength.value)

    return findings


# ---------------------------------------------------------------------------
# 7. Historical findings (HISTORICALLY_CHANGED_WITH — DIRECT_EVIDENCE)
# ---------------------------------------------------------------------------


def _historical_findings(
    context: RepositoryContext,
    history: RepositoryHistory,
) -> list[ImpactFinding]:
    """
    For each artifact in the Phase 3 history that has commit activity and is
    in the Phase 2 relevant-artifact set, produce a HISTORICALLY_CHANGED_WITH
    finding.

    What Phase 3 provides: per-artifact commit history (git log --follow on
    each artifact path).  It does NOT provide cross-artifact co-change pairs.
    The finding therefore records that this artifact *has relevant commit
    history* in the repository — not that it was necessarily co-changed with
    another specific artifact in the same commit.

    Evidence type: DIRECT_EVIDENCE — the commit hashes come directly from
    git log output and are real.

    Strength reflects how firmly the artifact is connected to *this change*:

    CONFIRMED  — artifact was explicitly listed as a changed file
                 (RelevanceReason.CHANGED_FILE).  The commits are historical
                 context for a file the developer knows is changing.

    LIKELY     — artifact was keyword-matched (RelevanceReason.KEYWORD_MATCH
                 or TEST_FOR_CHANGED or ENTRY_POINT).  Path keywords connect
                 it to the change description; historical activity reinforces
                 that this area of the codebase is actively maintained.

    POSSIBLE   — artifact is always-included (DEPENDENCY_MANIFEST,
                 CONFIGURATION, DOCUMENTATION).  Historical activity is
                 recorded but the connection to this specific change is weak.
    """
    findings: list[ImpactFinding] = []

    # Gather relevant artifacts from Phase 2 context, keyed by path.
    relevant_artifact_map: dict[str, ContextArtifact] = {
        a.path: a for a in context.artifacts
    }

    _always_included = frozenset({
        RelevanceReason.DEPENDENCY_MANIFEST,
        RelevanceReason.CONFIGURATION,
        RelevanceReason.DOCUMENTATION,
    })
    _keyword_matched = frozenset({
        RelevanceReason.KEYWORD_MATCH,
        RelevanceReason.TEST_FOR_CHANGED,
        RelevanceReason.ENTRY_POINT,
    })

    for artifact_path, art_hist in history.artifact_histories.items():
        if not art_hist.has_history():
            continue

        if artifact_path not in relevant_artifact_map:
            continue

        artifact = relevant_artifact_map[artifact_path]

        # Assign strength based on how firmly the artifact is connected to
        # the change, not merely on whether it has commits.
        if artifact.reason == RelevanceReason.CHANGED_FILE:
            strength = EvidenceStrength.CONFIRMED
        elif artifact.reason in _keyword_matched:
            strength = EvidenceStrength.LIKELY
        else:
            # Always-included artifacts (dep manifests, configs, docs): possible.
            strength = EvidenceStrength.POSSIBLE

        # Build evidence items from the first few commits.
        ev_items: list[ImpactEvidence] = []
        for commit in art_hist.commits[:3]:  # cap at 3 exemplars
            ev_items.append(
                ImpactEvidence(
                    artifact=artifact_path,
                    description=(
                        f"Git commit {commit.short_hash} modified '{artifact_path}': "
                        f"{commit.message[:80]!r}"
                        + (
                            f" (refs: {', '.join(commit.refs)})"
                            if commit.refs
                            else ""
                        )
                        + " (DIRECT_EVIDENCE: git log)."
                    ),
                    evidence_type=EvidenceType.DIRECT_EVIDENCE,
                )
            )

        if not ev_items:
            continue

        finding = ImpactFinding(
            affected_artifact=artifact_path,
            relationship=RelationshipType.HISTORICALLY_CHANGED_WITH,
            potential_impact=(
                f"'{artifact_path}' has {len(art_hist.commits)} recorded "
                f"commit(s) in the repository history relevant to this area of "
                "the codebase."
            ),
            evidence=tuple(ev_items),
            evidence_strength=strength,
            finding_type="historical",
        )
        findings.append(finding)
        logger.debug(
            "HISTORICALLY_CHANGED_WITH finding: %s (strength=%s)",
            artifact_path,
            strength.value,
        )

    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _artifact_finding_type(artifact: ContextArtifact) -> str:
    """Map ArtifactKind to finding_type string."""
    return artifact.kind.value  # "source", "test", "documentation", etc.


def _deduplicate(findings: list[ImpactFinding]) -> list[ImpactFinding]:
    """
    Remove duplicate findings with the same (artifact, relationship) key.

    When duplicates exist, keep the one with the strongest evidence
    (CONFIRMED > LIKELY > POSSIBLE).
    """
    _strength_order = {
        EvidenceStrength.CONFIRMED: 0,
        EvidenceStrength.LIKELY: 1,
        EvidenceStrength.POSSIBLE: 2,
    }
    seen: dict[tuple[str, RelationshipType], ImpactFinding] = {}
    for finding in findings:
        key = (finding.affected_artifact, finding.relationship)
        if key not in seen:
            seen[key] = finding
        else:
            existing = seen[key]
            if _strength_order[finding.evidence_strength] < _strength_order[existing.evidence_strength]:
                seen[key] = finding
    return list(seen.values())


def _finding_sort_key(finding: ImpactFinding) -> tuple[int, int, str]:
    """Sort key: confirmed first, then by finding type, then artifact name."""
    _strength_order = {
        EvidenceStrength.CONFIRMED: 0,
        EvidenceStrength.LIKELY: 1,
        EvidenceStrength.POSSIBLE: 2,
    }
    _type_order = {
        "source": 0,
        "test": 1,
        "documentation": 2,
        "dependency": 3,
        "configuration": 4,
        "historical": 5,
        "other": 6,
    }
    return (
        _strength_order[finding.evidence_strength],
        _type_order.get(finding.finding_type, 6),
        finding.affected_artifact,
    )
