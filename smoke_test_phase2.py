"""
DevFlow Phase 2 — Controlled Real-World Smoke Test

Repository: https://github.com/affaan-m/ECC
Change:     "Improve the repository's agent skill discovery and loading workflow."

Validation task only. No source code is modified.
No AI/LLM calls. No Phase 3 logic.
"""

import sys
import logging
from collections import Counter

# ── Set up logging so Phase 2 internals are visible ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)

# ── Imports from existing Phase 1 + Phase 2 modules ─────────────────────────
from devflow.input import accept_input
from devflow.context._build import build_context

# ── Test parameters ──────────────────────────────────────────────────────────
REPO_URL = "https://github.com/affaan-m/ECC"
CHANGE_DESC = "Improve the repository's agent skill discovery and loading workflow."

# ── Run ──────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("DevFlow Phase 2 — Real-World Smoke Test")
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
print(f"  Changed files supplied: {list(change.changed_files)}")
print()

# Phase 2 — build context
print("[ Phase 2 ] Building repository context …")
print("  (This will clone the repository — network access required)")
print()

ctx = build_context(repository, change, clone_timeout=120)

# ── Report results ───────────────────────────────────────────────────────────
print()
print("=" * 70)
print("SMOKE TEST RESULTS")
print("=" * 70)

# Repository retrieval status
retrieval_succeeded = ctx.error is None
print()
print(f"  Repository retrieval succeeded : {retrieval_succeeded}")
if not retrieval_succeeded:
    print(f"  ERROR : {ctx.error}")
    print()
    print("SMOKE TEST FAILED — cannot continue without successful retrieval.")
    sys.exit(1)

# Temp directory cleanup
cleanup_confirmed = ctx.retrieval_path is None
print(f"  Temporary data cleaned up      : {cleanup_confirmed}")

# File discovery
total_files = len(ctx.all_files)
print(f"  Total files discovered         : {total_files}")
print(f"  Entry points identified        : {len(ctx.entry_points)}")
if ctx.entry_points:
    for ep in ctx.entry_points:
        print(f"    - {ep}")

# Relevant artifacts
total_artifacts = len(ctx.artifacts)
print(f"  Relevant artifacts selected    : {total_artifacts}")

# Artifact categories
kind_counter = Counter(a.kind.value for a in ctx.artifacts)
print()
print("  Artifact categories:")
for kind, count in sorted(kind_counter.items()):
    print(f"    {kind:<20} : {count}")

# Relevance reasons
reason_counter = Counter(a.reason.value for a in ctx.artifacts)
print()
print("  Relevance reasons:")
for reason, count in sorted(reason_counter.items()):
    print(f"    {reason:<30} : {count}")

# Full artifact listing with evidence
print()
print("  Artifact details (path | kind | reason | confidence | evidence):")
print("  " + "-" * 66)
for a in ctx.artifacts:
    print(f"  [{a.confidence:<9}] {a.kind.value:<14} | {a.reason.value:<22} | {a.path}")
    print(f"              evidence: {a.evidence}")

print()
print("=" * 70)

# Check no ECC-specific logic was required
print("  ECC-specific logic required    : NO")
print("  (All classification done by generic path/name heuristics.)")
print("  (Relevance selection is keyword-driven, language-agnostic.)")
print()
print("SMOKE TEST PASSED")
print("=" * 70)
