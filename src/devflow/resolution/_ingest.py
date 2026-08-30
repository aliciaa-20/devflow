"""Deterministic parsers for Bob resolver-mode markdown output.

.bob/custom_modes.yaml's `resolver` mode defines two fixed output formats:
the "Propose the Fix" report (before the apply-fix approval gate) and the
closing "Resolution Summary ... Final Status" report (after implementation
and validation). Both are plain markdown with a fixed set of headings.

These parsers never guess at missing or malformed sections -- if Bob's raw
output doesn't match the expected shape, that's a ResolutionIngestError, not
a best-effort partial result.
"""

from __future__ import annotations

import re
from typing import Any

from devflow.models.resolution import FinalStatus, ProposedFix, ResolutionIngestError

_SECTION_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$", re.MULTILINE)

_FINAL_STATUS_MAP = {
    "RESOLVED": FinalStatus.RESOLVED,
    "PARTIALLY RESOLVED": FinalStatus.PARTIALLY_RESOLVED,
    "NOT RESOLVED": FinalStatus.NOT_RESOLVED,
    "VALIDATION FAILED": FinalStatus.VALIDATION_FAILED,
}


def _split_sections(raw_text: str) -> dict[str, str]:
    """Split markdown into {lowercased heading text: body text} sections."""
    matches = list(_SECTION_RE.finditer(raw_text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip().lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        sections[title] = raw_text[start:end].strip()
    return sections


def _parse_list_items(text: str) -> tuple[str, ...]:
    """Parse a section body into individual items, one per bulleted or plain line."""
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[-*]\s*", "", stripped)
        stripped = re.sub(r"^`([^`]+)`$", r"\1", stripped)
        if stripped:
            items.append(stripped)
    return tuple(items)


def _require_sections(sections: dict[str, str], required: list[str], *, context: str) -> None:
    missing = [name for name in required if not sections.get(name)]
    if missing:
        raise ResolutionIngestError(
            f"{context} is missing required section(s): {', '.join(missing)}"
        )


def parse_proposed_fix(raw_text: str, *, raw_bob_output_path: str) -> ProposedFix:
    """Parse Bob resolver mode's "Propose the Fix" markdown output.

    Expects the fixed headings from .bob/custom_modes.yaml's Step 3:
    ### Proposed Change / ### Files to Modify / ### Tests / ### Validation
    (### Root Cause is used when present, but is not required for parsing).
    """
    sections = _split_sections(raw_text)
    _require_sections(
        sections,
        ["proposed change", "files to modify", "tests", "validation"],
        context="Bob investigation output",
    )
    return ProposedFix(
        summary=sections["proposed change"],
        root_cause=sections.get("root cause", ""),
        files_to_modify=_parse_list_items(sections["files to modify"]),
        tests_to_add_or_update=_parse_list_items(sections["tests"]),
        validation_plan=sections["validation"],
        raw_bob_output_path=raw_bob_output_path,
    )


def parse_resolution_summary(raw_text: str) -> dict[str, Any]:
    """Parse Bob resolver mode's closing "Resolution Summary ... Final Status" output.

    Returns the claimed final status alongside the narrative fields -- the
    caller (resolution._build.run_validation) is responsible for cross
    checking `claimed_final_status` against DevFlow's own executed test
    results rather than trusting it outright.
    """
    sections = _split_sections(raw_text)
    _require_sections(
        sections,
        ["resolution summary", "final status"],
        context="Bob resolution output",
    )

    final_status_raw = re.sub(r"^[-*]\s*", "", sections["final status"].strip()).upper()
    if final_status_raw not in _FINAL_STATUS_MAP:
        raise ResolutionIngestError(
            f"Unrecognized Final Status value: {sections['final status']!r}. "
            f"Expected one of: {', '.join(_FINAL_STATUS_MAP)}."
        )

    return {
        "change_rationale": sections["resolution summary"],
        "remaining_risks": _parse_list_items(sections.get("remaining risks", "")),
        "claimed_final_status": _FINAL_STATUS_MAP[final_status_raw],
        "files_changed": _parse_list_items(sections.get("files changed", "")),
        "tests_added_or_updated": _parse_list_items(sections.get("tests added / updated", "")),
    }
