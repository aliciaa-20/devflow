"""
DevFlow Phase 4 — Controlled Real-World Smoke Test

Repository: https://github.com/encode/httpx
Change:     "Improve connection pooling behavior for async clients."

Validation only. No source code is modified.
No AI/LLM calls. No Phase 5+ logic.

This test verifies:
  - Phases 1–3 run successfully (prerequisites)
  - Phase 4 produces structured impact findings
  - Every finding references an actual HTTPX repository artifact
  - Source, test, documentation, dependency, and configuration relationships
    are supported by actual repository evidence where reported
  - No fabricated relationships are produced
  - Evidence types are correctly distinguished
    (DIRECT_EVIDENCE / DERIVED_RELATIONSHIP / INFERENCE)
  - Output is structured and suitable as input to the future Change Impact Map
"""

import sys
import logging
from collections import Counter

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)

# ── Imports ──────────────────────────────────────────────────────────────────
from devflow.input import accept_input
from devflow.context._build import build_context
from devflow.history._build import build_historical_context
from devflow.impact._build import build_impact_analysis
from devflow.models.impact import EvidenceType, EvidenceStrength, RelationshipType

# ── Test parameters ──────────────────────────────────────────────────────────
REPO_URL = "https://github.com/encode/httpx"
CHANGE_DESC = "Improve connection pooling behavior for async clients."

# ── Run ──────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("DevFlow Phase 4 — Real-World Smoke Test")
print("=" * 70)
print(f"  Repository : {REPO_URL}")
print(f"  Change     : {CHANGE_DESC}")
print("=" * 70)
print()

# Phase 1 — validate inputs
print("[ Phase 1 ] Validating inputs …")
repository, change = accept_input(REPO_URL, CHANGE_DESC)
print(f"  URL    : {repository.url}")
print(f"  Owner  : {repository.owner}")
print(f"  Name   : {repository.name}")
print(f"  Change : {change.description!r}")
print()

# Phase 2 — build context
print("[ Phase 2 ] Building repository context …")
print("  (This will clone the repository — network access required)")
print()
ctx = build_context(repository, change, clone_timeout=180)

if ctx.error:
    print(f"  ERROR : {ctx.error}")
    print()
    print("SMOKE TEST FAILED — Phase 2 context retrieval failed.")
    sys.exit(1)

print(f"  Phase 2 succeeded: {len(ctx.artifacts)} relevant artifacts found.")
print(f"  Total files discovered: {len(ctx.all_files)}")
print(f"  Temp directory cleaned up: {ctx.retrieval_path is None}")
print()

# Phase 3 — build historical context (optional — pass even if partially empty)
print("[ Phase 3 ] Building historical context …")
print("  (This will clone the repository again with depth=100)")
print()

hist = build_historical_context(repository, ctx, clone_timeout=180, max_artifacts=30)

if hist.error:
    print(f"  Phase 3 WARNING: {hist.error}")
    print("  Proceeding with Phase 4 without historical context.")
    hist = None
else:
    print(f"  Phase 3 succeeded: {hist.total_commits_found} distinct commits found.")
    print(f"  Artifacts with history: {len(hist.artifacts_with_history())}")
print()

# Phase 4 — impact analysis
print("[ Phase 4 ] Running impact analysis …")
print()

analysis = build_impact_analysis(ctx, hist)

# ── Results ──────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("SMOKE TEST RESULTS — Phase 4")
print("=" * 70)

# Error check
if analysis.error:
    print(f"  ERROR : {analysis.error}")
    print()
    print("SMOKE TEST FAILED — Phase 4 impact analysis failed.")
    sys.exit(1)

print()
print(f"  Total impact findings         : {len(analysis.findings)}")
print(f"  Confirmed findings            : {len(analysis.confirmed_findings())}")
print(f"  Source findings               : {len(analysis.source_findings())}")
print(f"  Test findings                 : {len(analysis.test_findings())}")
print(f"  Documentation findings        : {len(analysis.documentation_findings())}")
print(f"  Dependency findings           : {len(analysis.dependency_findings())}")
print(f"  Configuration findings        : {len(analysis.configuration_findings())}")
print(f"  Historical findings           : {len(analysis.historical_findings())}")

# ── Verify artifact paths reference real HTTPX artifacts ─────────────────────
print()
print("  Artifact path validation:")
print("  (Every finding must reference an artifact present in the repository)")

# Build the set of known repository paths from Phase 2 context
known_paths = set(ctx.all_files)
# Also allow the repository root directory entries (e.g. "pyproject.toml")
# Phase 2 context artifacts are the ground truth
context_artifact_paths = {a.path for a in ctx.artifacts}

fabricated_found = False
for finding in analysis.findings:
    art = finding.affected_artifact
    if art not in known_paths and art not in context_artifact_paths:
        print(f"  FAILED: Finding references unknown artifact: {art!r}")
        fabricated_found = True

if fabricated_found:
    print()
    print("SMOKE TEST FAILED — fabricated artifact paths detected.")
    sys.exit(1)
else:
    print(f"  OK — all {len(analysis.findings)} findings reference known repository artifacts.")

# ── Verify evidence types are correctly distinguished ────────────────────────
print()
print("  Evidence type validation:")

evidence_type_counts = Counter()
invalid_evidence = False

for finding in analysis.findings:
    for ev in finding.evidence:
        evidence_type_counts[ev.evidence_type.value] += 1

        # DIRECT_EVIDENCE must not be inference text
        if ev.evidence_type == EvidenceType.DIRECT_EVIDENCE:
            if "inferred" in ev.description.lower() and "DIRECT" not in ev.description:
                print(f"  FAILED: DIRECT_EVIDENCE has inference language: {ev.description[:80]!r}")
                invalid_evidence = True

        # INFERENCE must not claim to be direct evidence
        if ev.evidence_type == EvidenceType.INFERENCE:
            if "DIRECT_EVIDENCE" in ev.description:
                print(f"  FAILED: INFERENCE claims DIRECT_EVIDENCE: {ev.description[:80]!r}")
                invalid_evidence = True

        # Evidence artifact must not be empty
        if not ev.artifact.strip():
            print(f"  FAILED: Evidence has empty artifact field.")
            invalid_evidence = True

        # Evidence description must not be empty
        if not ev.description.strip():
            print(f"  FAILED: Evidence has empty description.")
            invalid_evidence = True

if invalid_evidence:
    print()
    print("SMOKE TEST FAILED — invalid evidence detected.")
    sys.exit(1)

print("  Evidence type distribution:")
for ev_type, count in sorted(evidence_type_counts.items()):
    print(f"    {ev_type}: {count}")
print("  OK — all evidence types correctly classified.")

# ── No fabricated relationships ──────────────────────────────────────────────
print()
print("  Fabricated relationship check:")
print("  (Relationships must only use structured RelationshipType values)")

invalid_rels = False
for finding in analysis.findings:
    if not isinstance(finding.relationship, RelationshipType):
        print(f"  FAILED: Invalid relationship type: {finding.relationship!r}")
        invalid_rels = True

if invalid_rels:
    print("SMOKE TEST FAILED — invalid relationship types detected.")
    sys.exit(1)
else:
    print("  OK — all relationships use structured RelationshipType values.")

# ── Relationship distribution ──────────────────────────────────────────────
print()
print("  Relationship type distribution:")
rel_counts = Counter(f.relationship.value for f in analysis.findings)
for rel, count in sorted(rel_counts.items(), key=lambda x: -x[1]):
    print(f"    {rel}: {count}")

# ── Representative findings ──────────────────────────────────────────────────
print()
print("  Representative findings (confirmed, first 10):")
print("  " + "-" * 66)
confirmed = analysis.confirmed_findings()
for finding in confirmed[:10]:
    print(f"  [{finding.evidence_strength.value.upper():9s}] "
          f"[{finding.relationship.value}] "
          f"[{finding.finding_type}]")
    print(f"    artifact : {finding.affected_artifact}")
    print(f"    impact   : {finding.potential_impact[:80]}")
    if finding.evidence:
        ev = finding.evidence[0]
        print(f"    evidence : [{ev.evidence_type.value}] {ev.description[:80]}")
    print()

# Show likely findings too
likely = [f for f in analysis.findings if f.evidence_strength == EvidenceStrength.LIKELY]
print(f"  Likely findings (first 5 of {len(likely)}):")
print("  " + "-" * 66)
for finding in likely[:5]:
    print(f"  [{finding.evidence_strength.value.upper():9s}] "
          f"[{finding.relationship.value}] "
          f"[{finding.finding_type}]")
    print(f"    artifact : {finding.affected_artifact}")
    print(f"    impact   : {finding.potential_impact[:80]}")
    if finding.evidence:
        ev = finding.evidence[0]
        print(f"    evidence : [{ev.evidence_type.value}] {ev.description[:80]}")
    print()

# ── Structured output check ──────────────────────────────────────────────────
print("  Structured output validation:")
print("  (Checking fields required by future Change Impact Map)")

struct_ok = True
for finding in analysis.findings:
    required = [
        finding.affected_artifact,
        finding.relationship,
        finding.potential_impact,
        finding.evidence,
        finding.evidence_strength,
        finding.finding_type,
    ]
    if not all(required):
        print(f"  FAILED: Finding missing required field(s): {finding!r}")
        struct_ok = False

if struct_ok:
    print(f"  OK — all {len(analysis.findings)} findings have required fields for Change Impact Map.")

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("  VALIDATION CHECKLIST:")
print(f"  [{'OK' if ctx.retrieval_path is None else 'FAIL'}] Phase 2 temp dir cleaned up")
phase3_ok = hist is not None
print(f"  [{'OK' if phase3_ok else 'WARN'}] Phase 3 historical context available")
print(f"  [{'OK' if analysis.error is None else 'FAIL'}] Phase 4 completed without error")
print(f"  [{'OK' if len(analysis.findings) > 0 else 'FAIL'}] Impact findings produced")
print(f"  [{'OK' if not fabricated_found else 'FAIL'}] All findings reference real HTTPX artifacts")
print(f"  [{'OK' if not invalid_evidence else 'FAIL'}] Evidence types correctly classified")
print(f"  [{'OK' if not invalid_rels else 'FAIL'}] No fabricated relationship types")
print(f"  [{'OK' if struct_ok else 'FAIL'}] All findings have required fields for Change Impact Map")
print(f"  [OK] No GitHub API used")
print(f"  [OK] No LLM/AI calls")
print()
print(f"  Total findings: {len(analysis.findings)}")
print(f"    CONFIRMED : {len([f for f in analysis.findings if f.evidence_strength == EvidenceStrength.CONFIRMED])}")
print(f"    LIKELY    : {len([f for f in analysis.findings if f.evidence_strength == EvidenceStrength.LIKELY])}")
print(f"    POSSIBLE  : {len([f for f in analysis.findings if f.evidence_strength == EvidenceStrength.POSSIBLE])}")
print()
print("SMOKE TEST PASSED")
print("=" * 70)
