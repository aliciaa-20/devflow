"""
Relevance engine for DevFlow Phase 2.

Given the list of all repository files, the ChangeRequest, and the
ArtifactKind classification, this module determines which artifacts are
relevant to the change, assigns a reason, and records supporting evidence.

All decisions are deterministic and based solely on:
- The file paths present in the repository
- The ArtifactKind classification
- Keywords derived from the change description and changed_files list

No AI calls. No fabrication.
"""

from __future__ import annotations

import re
from pathlib import Path

from devflow.models.change import ChangeRequest
from devflow.models.context import ArtifactKind, ContextArtifact, RelevanceReason
from devflow.context.inspector import classify_file


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")  # words >= 3 chars


def _extract_keywords(text: str) -> frozenset[str]:
    """
    Extract lowercase meaningful tokens from a description string.

    Stops-words and very short tokens are filtered out.
    """
    _STOP = frozenset(
        {
            "the", "and", "for", "with", "from", "that", "this", "are",
            "was", "its", "into", "all", "not", "any", "can", "will",
            "add", "update", "change", "changes", "new", "old", "remove",
            "fix", "fixes", "use", "using", "when", "which", "also",
        }
    )
    tokens = {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}
    return frozenset(tokens - _STOP)


def _path_keywords(rel_path: str) -> frozenset[str]:
    """Extract lowercase tokens from the path components of a file."""
    # Split on path separators and common non-alphanumeric chars.
    raw = re.split(r"[/\\._\-]", rel_path)
    tokens = {t.lower() for t in raw if len(t) >= 3}
    return frozenset(tokens)


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

_ALWAYS_RELEVANT_KINDS: frozenset[ArtifactKind] = frozenset(
    {
        ArtifactKind.DEPENDENCY,
        ArtifactKind.CONFIGURATION,
        ArtifactKind.DOCUMENTATION,
    }
)


def select_relevant_artifacts(
    all_files: list[str],
    change: ChangeRequest,
    max_source_files: int = 50,
    max_test_files: int = 30,
) -> list[ContextArtifact]:
    """
    Select relevant artifacts from the full repository file list.

    Strategy (in priority order):
    1. Any file explicitly listed in change.changed_files → confirmed + CHANGED_FILE.
    2. Dependency manifests, config, docs → confirmed + their specific reason.
    3. Source / test files whose path shares keywords with the change description
       or changed_files paths → likely + KEYWORD_MATCH.
    4. Tests whose stem overlaps a changed-file stem → likely + TEST_FOR_CHANGED.

    Limits are applied to source and test results to keep context manageable.

    Args:
        all_files:       All files in the repository (relative paths).
        change:          The validated ChangeRequest from Phase 1.
        max_source_files: Upper limit on keyword-matched source files.
        max_test_files:  Upper limit on keyword-matched test files.

    Returns:
        A list of ContextArtifact instances, deduplicated and sorted by path.
    """
    artifacts: dict[str, ContextArtifact] = {}

    # --- Derive keyword sets ---
    desc_keywords = _extract_keywords(change.description)

    # Keywords from changed file directory paths (not stems, to avoid conflating
    # changed-file stem matching with the TEST_FOR_CHANGED mechanism).
    changed_dir_keywords: frozenset[str] = frozenset()
    changed_stem_words: frozenset[str] = frozenset()
    for cf in change.changed_files:
        cf_path = Path(cf)
        # Directory components only (not the filename stem) for keyword matching.
        dir_part = str(cf_path.parent)
        if dir_part not in (".", ""):
            changed_dir_keywords |= _path_keywords(dir_part)
        # Stems are kept separate; used by TEST_FOR_CHANGED (Pass 4) not Pass 3.
        changed_stem_words |= {cf_path.stem.lower().replace("-", "_")}

    # combined_keywords for source-file matching: description + directory context.
    combined_keywords = desc_keywords | changed_dir_keywords

    # Stems of explicitly changed files (for test matching).
    changed_stems = frozenset(
        Path(cf).stem.lower().replace("-", "_")
        for cf in change.changed_files
    )

    def _add(artifact: ContextArtifact) -> None:
        # First encounter wins (higher-priority reasons come first in caller).
        if artifact.path not in artifacts:
            artifacts[artifact.path] = artifact

    # --- Pass 1: explicitly changed files ---
    for rel_path in all_files:
        norm = rel_path.replace("\\", "/")
        if norm in change.changed_files or rel_path in change.changed_files:
            kind = classify_file(rel_path)
            _add(
                ContextArtifact(
                    path=rel_path,
                    kind=kind,
                    reason=RelevanceReason.CHANGED_FILE,
                    evidence=f"path '{rel_path}' appears in the supplied changed_files list",
                    confidence="confirmed",
                )
            )

    # --- Pass 2: always-relevant kinds ---
    for rel_path in all_files:
        if rel_path in artifacts:
            continue
        kind = classify_file(rel_path)
        if kind == ArtifactKind.DEPENDENCY:
            _add(
                ContextArtifact(
                    path=rel_path,
                    kind=kind,
                    reason=RelevanceReason.DEPENDENCY_MANIFEST,
                    evidence=f"'{rel_path}' is a dependency manifest file",
                    confidence="confirmed",
                )
            )
        elif kind == ArtifactKind.CONFIGURATION:
            _add(
                ContextArtifact(
                    path=rel_path,
                    kind=kind,
                    reason=RelevanceReason.CONFIGURATION,
                    evidence=f"'{rel_path}' is a project configuration file",
                    confidence="confirmed",
                )
            )
        elif kind == ArtifactKind.DOCUMENTATION:
            _add(
                ContextArtifact(
                    path=rel_path,
                    kind=kind,
                    reason=RelevanceReason.DOCUMENTATION,
                    evidence=f"'{rel_path}' is a documentation file",
                    confidence="confirmed",
                )
            )

    # --- Pass 3: keyword-matched source files ---
    source_matches: list[tuple[int, str]] = []
    test_matches: list[tuple[int, str, str]] = []  # (score, path, match_reason)

    for rel_path in all_files:
        if rel_path in artifacts:
            continue
        kind = classify_file(rel_path)
        if kind not in (ArtifactKind.SOURCE, ArtifactKind.TEST):
            continue

        path_kws = _path_keywords(rel_path)
        matched = path_kws & combined_keywords
        score = len(matched)

        if score == 0:
            continue

        if kind == ArtifactKind.SOURCE:
            source_matches.append((score, rel_path))
        else:
            test_matches.append((score, rel_path, ", ".join(sorted(matched))))

    # Sort by descending score, then path for determinism.
    source_matches.sort(key=lambda x: (-x[0], x[1]))
    test_matches.sort(key=lambda x: (-x[0], x[1]))

    for _score, rel_path in source_matches[:max_source_files]:
        path_kws = _path_keywords(rel_path)
        matched = path_kws & combined_keywords
        _add(
            ContextArtifact(
                path=rel_path,
                kind=ArtifactKind.SOURCE,
                reason=RelevanceReason.KEYWORD_MATCH,
                evidence=(
                    f"path keywords {sorted(matched)!r} match change keywords derived "
                    f"from description or changed_files"
                ),
                confidence="likely",
            )
        )

    for _score, rel_path, _kws in test_matches[:max_test_files]:
        path_kws = _path_keywords(rel_path)
        matched = path_kws & combined_keywords
        _add(
            ContextArtifact(
                path=rel_path,
                kind=ArtifactKind.TEST,
                reason=RelevanceReason.KEYWORD_MATCH,
                evidence=(
                    f"path keywords {sorted(matched)!r} match change keywords"
                ),
                confidence="likely",
            )
        )

    # --- Pass 4: tests whose stem overlaps a changed-file stem ---
    if changed_stems:
        for rel_path in all_files:
            if rel_path in artifacts:
                continue
            kind = classify_file(rel_path)
            if kind != ArtifactKind.TEST:
                continue
            stem = Path(rel_path).stem.lower().replace("-", "_")
            # Strip common test prefixes/suffixes to get the subject stem.
            subject = stem
            for prefix in ("test_", "test-"):
                if subject.startswith(prefix):
                    subject = subject[len(prefix):]
                    break
            for suffix in ("_test", "-test", "_spec", "-spec"):
                if subject.endswith(suffix):
                    subject = subject[: -len(suffix)]
                    break
            if subject in changed_stems or stem in changed_stems:
                _add(
                    ContextArtifact(
                        path=rel_path,
                        kind=ArtifactKind.TEST,
                        reason=RelevanceReason.TEST_FOR_CHANGED,
                        evidence=(
                            f"test file stem '{subject}' matches a changed-file stem"
                        ),
                        confidence="likely",
                    )
                )

    return sorted(artifacts.values(), key=lambda a: a.path)
