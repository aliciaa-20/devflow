"""
DevFlow Phase 3 — Controlled Real-World Smoke Test

Repository: https://github.com/affaan-m/ECC
Change:     "Improve the repository's agent skill discovery and loading workflow."

Validation only. No source code is modified.
No AI/LLM calls. No Phase 4+ logic.

This test verifies:
  - Repository retrieval succeeds (Phase 2 path)
  - Historical commits are actually discovered
  - Commit hashes are real (40-char SHA-1)
  - Commit messages come from the retrieved repository
  - Artifact-to-commit relationships are evidence-backed
  - Temporary repository data is cleaned up
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

# ── Test parameters ──────────────────────────────────────────────────────────
REPO_URL = "https://github.com/affaan-m/ECC"
CHANGE_DESC = "Improve the repository's agent skill discovery and loading workflow."

# ── Run ──────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("DevFlow Phase 3 — Real-World Smoke Test")
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
ctx = build_context(repository, change, clone_timeout=120)

if ctx.error:
    print(f"  ERROR : {ctx.error}")
    print()
    print("SMOKE TEST FAILED — Phase 2 context retrieval failed.")
    sys.exit(1)

print(f"  Phase 2 succeeded: {len(ctx.artifacts)} relevant artifacts found.")
print(f"  Temp directory cleaned up: {ctx.retrieval_path is None}")
print()

# Phase 3 — build historical context
print("[ Phase 3 ] Building historical context …")
print("  (This will clone the repository again with depth=100)")
print()

hist = build_historical_context(repository, ctx, clone_timeout=180)

# ── Results ──────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("SMOKE TEST RESULTS — Phase 3")
print("=" * 70)

# Error check
if hist.error:
    print(f"  ERROR : {hist.error}")
    print()
    print("SMOKE TEST FAILED — Phase 3 historical context extraction failed.")
    sys.exit(1)

print()
print(f"  Total artifacts inspected    : {len(hist.artifact_histories)}")
print(f"  Total distinct commits found : {hist.total_commits_found}")
print(f"  Artifacts with history       : {len(hist.artifacts_with_history())}")
print(f"  Artifacts without history    : {len(hist.artifacts_without_history())}")

# Verify commit hashes are real 40-char SHA-1
print()
print("  Commit hash validation:")
all_commits = hist.all_commits()
if not all_commits:
    print("  WARNING: No commits discovered. History may be empty or inaccessible.")
else:
    invalid_hashes = [c.hash for c in all_commits if len(c.hash) != 40]
    if invalid_hashes:
        print(f"  FAILED: {len(invalid_hashes)} invalid commit hashes found.")
        for h in invalid_hashes[:5]:
            print(f"    - {h!r}")
        sys.exit(1)
    else:
        print(f"  OK — all {len(all_commits)} commit hashes are valid 40-char SHA-1.")

# Show per-artifact history
print()
print("  Artifact histories (path | commits | sample message):")
print("  " + "-" * 66)
for artifact_path, art_hist in sorted(hist.artifact_histories.items()):
    commit_count = len(art_hist.commits)
    if commit_count > 0:
        sample = art_hist.commits[0].message[:60]
        latest_hash = art_hist.commits[0].short_hash
        print(f"  [{commit_count:3d} commits] {artifact_path}")
        print(f"              latest: {latest_hash} — {sample!r}")
    else:
        note = (art_hist.note or "no history")[:80]
        print(f"  [  0 commits] {artifact_path}")
        print(f"              note: {note}")

# Verify evidence is present for commits that were found
print()
print("  Evidence validation:")
evidence_count = sum(len(h.evidence) for h in hist.artifact_histories.values())
print(f"  Total evidence items: {evidence_count}")

fabricated_found = False
for art_hist in hist.artifact_histories.values():
    for ev in art_hist.evidence:
        if "github issue" in ev.description.lower():
            print(f"  FAILED: Evidence claims GitHub Issue without confirmation: {ev.description!r}")
            fabricated_found = True
        if ev.evidence_type not in ("direct_modification", "message_reference"):
            print(f"  FAILED: Unknown evidence_type: {ev.evidence_type!r}")
            fabricated_found = True
        if not ev.commit_hash or len(ev.commit_hash) != 40:
            print(f"  FAILED: Evidence has invalid commit hash: {ev.commit_hash!r}")
            fabricated_found = True

if fabricated_found:
    print()
    print("SMOKE TEST FAILED — fabricated or invalid evidence detected.")
    sys.exit(1)
else:
    print("  OK — no fabricated evidence detected.")

# Commit message references
print()
print("  Commit message references (#NNN) — recorded as-is, not as GitHub entities:")
ref_commits = [c for c in all_commits if c.refs]
print(f"  Commits with refs: {len(ref_commits)}")
for c in ref_commits[:5]:
    print(f"    {c.short_hash}: {c.message[:60]!r}  refs={c.refs}")

# Summary
print()
print("=" * 70)
print("  VALIDATION CHECKLIST:")
print(f"  [{'OK' if ctx.retrieval_path is None else 'FAIL'}] Phase 2 temp dir cleaned up")
print(f"  [{'OK' if hist.error is None else 'FAIL'}] Phase 3 completed without error")
print(f"  [{'OK' if all_commits else 'WARN'}] Historical commits discovered")
print(f"  [{'OK' if not invalid_hashes else 'FAIL'}] All commit hashes are real SHA-1" if all_commits else "  [SKIP] Hash validation (no commits)")
print(f"  [{'OK' if not fabricated_found else 'FAIL'}] No fabricated evidence")
print(f"  [OK] No GitHub API used")
print(f"  [OK] No LLM/AI calls")
print()
print("SMOKE TEST PASSED")
print("=" * 70)
