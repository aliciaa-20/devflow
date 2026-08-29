"""
Deterministic evidence-based relevance selection for repository artifacts.

Repository inspection may discover many files, but only artifacts with a
specific connection to the developer change are returned as context artifacts.
"""

from __future__ import annotations

import re
from pathlib import Path

from devflow.context.inspector import classify_file
from devflow.models.change import ChangeRequest
from devflow.models.context import ArtifactKind, ContextArtifact, RelevanceReason


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_STOP_WORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "are", "was",
        "its", "into", "all", "not", "any", "can", "will", "add", "update",
        "change", "changes", "new", "old", "remove", "fix", "fixes", "use",
        "using", "when", "which", "also",
    }
)
_DOMAIN_ALIASES: dict[str, frozenset[str]] = {
    "authentication": frozenset({"auth"}),
    "configuration": frozenset({"config"}),
    "context": frozenset({"ctx"}),
    "documentation": frozenset({"docs", "doc"}),
    "dependency": frozenset({"deps", "requirements"}),
}


def _extract_keywords(text: str) -> frozenset[str]:
    """Extract meaningful lowercase tokens from a change description."""
    tokens = {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}
    return frozenset(tokens - _STOP_WORDS)


def _expand_keywords(keywords: frozenset[str]) -> frozenset[str]:
    """Add conservative code-oriented aliases without inventing artifacts."""
    expanded = set(keywords)
    for keyword in keywords:
        expanded.update(_DOMAIN_ALIASES.get(keyword, ()))
    return frozenset(expanded)


def _path_keywords(rel_path: str) -> frozenset[str]:
    """Extract lowercase tokens from path components."""
    raw = re.split(r"[/\\._\-]", rel_path)
    return frozenset(token.lower() for token in raw if len(token) >= 3)


def select_relevant_artifacts(
    all_files: list[str],
    change: ChangeRequest,
    max_source_files: int = 50,
    max_test_files: int = 30,
) -> list[ContextArtifact]:
    """Select only artifacts with structured evidence connecting them to change."""
    artifacts: dict[str, ContextArtifact] = {}
    desc_keywords = _expand_keywords(_extract_keywords(change.description))
    changed_dir_keywords: set[str] = set()
    changed_stems: set[str] = set()
    for changed_file in change.changed_files:
        path = Path(changed_file)
        changed_dir_keywords.update(_path_keywords(str(path.parent)))
        changed_stems.add(path.stem.lower().replace("-", "_"))
    combined_keywords = desc_keywords | changed_dir_keywords

    def add(artifact: ContextArtifact) -> None:
        artifacts.setdefault(artifact.path, artifact)

    # Explicitly changed files are the strongest relevance evidence.
    for rel_path in all_files:
        normalized = rel_path.replace("\\", "/")
        if normalized in change.changed_files or rel_path in change.changed_files:
            add(
                ContextArtifact(
                    path=rel_path,
                    kind=classify_file(rel_path),
                    reason=RelevanceReason.CHANGED_FILE,
                    evidence=f"path '{rel_path}' appears in supplied changed_files",
                    confidence="confirmed",
                )
            )

    # Path matches are useful evidence for source, tests, and directly named
    # supporting artifacts, but a file's type alone is never enough.
    matches: list[tuple[int, str, ArtifactKind, frozenset[str]]] = []
    for rel_path in all_files:
        if rel_path in artifacts:
            continue
        kind = classify_file(rel_path)
        if kind not in {
            ArtifactKind.SOURCE,
            ArtifactKind.TEST,
            ArtifactKind.DOCUMENTATION,
            ArtifactKind.DEPENDENCY,
            ArtifactKind.CONFIGURATION,
        }:
            continue
        matched = _path_keywords(rel_path) & combined_keywords
        if matched:
            matches.append((len(matched), rel_path, kind, matched))

    matches.sort(key=lambda item: (-item[0], item[1]))
    source_count = 0
    test_count = 0
    for _score, rel_path, kind, matched in matches:
        if kind == ArtifactKind.SOURCE:
            if source_count >= max_source_files:
                continue
            source_count += 1
            reason = RelevanceReason.KEYWORD_MATCH
        elif kind == ArtifactKind.TEST:
            if test_count >= max_test_files:
                continue
            test_count += 1
            reason = RelevanceReason.KEYWORD_MATCH
        elif kind == ArtifactKind.DOCUMENTATION:
            reason = RelevanceReason.DOCUMENTATION
        elif kind == ArtifactKind.DEPENDENCY:
            reason = RelevanceReason.DEPENDENCY_MANIFEST
        else:
            reason = RelevanceReason.CONFIGURATION
        add(
            ContextArtifact(
                path=rel_path,
                kind=kind,
                reason=reason,
                evidence=f"path keywords {sorted(matched)!r} match change keywords",
                confidence="likely",
            )
        )

    # A test stem matching an explicitly changed file is direct structural
    # evidence even when the developer description contains no matching word.
    for rel_path in all_files:
        if rel_path in artifacts or classify_file(rel_path) != ArtifactKind.TEST:
            continue
        stem = Path(rel_path).stem.lower().replace("-", "_")
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
            add(
                ContextArtifact(
                    path=rel_path,
                    kind=ArtifactKind.TEST,
                    reason=RelevanceReason.TEST_FOR_CHANGED,
                    evidence=f"test file stem '{subject}' matches a changed-file stem",
                    confidence="likely",
                )
            )

    return sorted(artifacts.values(), key=lambda artifact: artifact.path)
