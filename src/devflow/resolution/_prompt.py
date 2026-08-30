"""Build the IBM Bob investigation prompt for an approved finding.

DevFlow's premise is that a developer should not have to reconstruct context
before acting.  The same applies to the agent: rather than asking the developer
to describe the finding to Bob by hand, DevFlow hands Bob the evidence it
already gathered.

Everything in the generated prompt comes from the resolution request, which was
built from the Developer Report.  Nothing is invented here: this module only
formats facts that earlier phases established, and it says explicitly which
statements are inference rather than observed fact.
"""

from __future__ import annotations

from typing import Any

from devflow.models.resolution import ResolutionRequest

# The four investigation skills shipped in .bob/skills/. Dispatching them as
# parallel subagents is what makes the investigation genuinely multi-perspective
# rather than a single pass.
_BOB_SKILLS = (
    ("change-context", "what surrounds this code and why it is relevant"),
    ("impact-analysis", "what else this change could affect"),
    ("historical-context", "what repository history says about this area"),
    ("evidence-report", "synthesis of the above into evidence-backed findings"),
)


def _evidence_lines(evidence: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in evidence:
        evidence_type = str(item.get("evidence_type") or "UNKNOWN")
        description = " ".join(str(item.get("description") or "").split())
        artifact = str(item.get("artifact") or "")
        prefix = f"- [{evidence_type}]"
        if artifact:
            prefix += f" ({artifact})"
        lines.append(f"{prefix} {description}")
    return lines


def build_bob_prompt(request: ResolutionRequest) -> str:
    """Render a copy-pasteable prompt for Bob's `resolver` custom mode."""
    finding = request.finding_snapshot
    artifacts = list(finding.get("affected_artifacts") or [])
    evidence = list(finding.get("evidence") or [])
    severity = finding.get("severity") or "unrated"
    recommendation = finding.get("recommendation")

    sections: list[str] = []

    sections.append(
        "# DevFlow resolution request\n\n"
        f"Repository: {request.repository_url}\n"
        f"Change under review: {request.change_summary}\n"
        f"DevFlow resolution id: {request.id}\n"
        f"DevFlow finding id: {request.finding_id}\n"
    )

    sections.append(
        "## The finding\n\n"
        f"**{finding.get('title') or request.finding_id}**\n\n"
        f"- Category: {finding.get('category')}\n"
        f"- Severity: {severity}\n"
        f"- Affected artifacts: {', '.join(artifacts) if artifacts else '(none recorded)'}\n\n"
        f"{' '.join(str(finding.get('description') or '').split())}\n"
    )

    if finding.get("is_inference"):
        sections.append(
            "> This finding is an INFERENCE drawn from repository evidence. It\n"
            "> describes potential exposure, not an established defect. Confirm it\n"
            "> against the code before proposing any change, and say so if the\n"
            "> evidence does not support it.\n"
        )

    if evidence:
        sections.append(
            "## Evidence DevFlow already gathered\n\n"
            "Each item below was derived deterministically from the repository.\n"
            "DIRECT_EVIDENCE items are parsed facts (import statements, git log);\n"
            "DERIVED_RELATIONSHIP items are structural inferences.\n\n"
            + "\n".join(_evidence_lines(evidence))
            + "\n"
        )

    if recommendation:
        sections.append(
            "## DevFlow's recommended action\n\n"
            f"{' '.join(str(recommendation).split())}\n\n"
            "Treat this as a starting point, not a specification. If investigation\n"
            "shows a better minimal fix, propose that instead and explain why.\n"
        )

    skills = "\n".join(f"   - `{name}` — {purpose}" for name, purpose in _BOB_SKILLS)
    sections.append(
        "## What to do\n\n"
        "1. Investigate this finding in parallel from the perspectives below,\n"
        "   using the DevFlow skills in `.bob/skills/` as subagents:\n\n"
        f"{skills}\n\n"
        "2. Determine the root cause where the evidence establishes one.\n"
        "3. Identify the smallest safe change that addresses the finding.\n"
        "4. Report using the `resolver` mode's 'Propose the Fix' format:\n"
        "   Finding / Root Cause / Proposed Change / Files to Modify / Tests /\n"
        "   Validation.\n\n"
        "**Do not modify any file yet.** DevFlow requires explicit human approval\n"
        "between your proposal and its implementation.\n"
    )

    sections.append(
        "## Constraints\n\n"
        "- Fix only this finding. Report anything else you notice separately.\n"
        "- Do not fabricate commits, issues, tests, or test results.\n"
        "- If the evidence does not support the finding, say so rather than\n"
        "  inventing a fix.\n"
        "- DevFlow will run the tests itself afterwards and will report the real\n"
        "  result, so do not claim a test passed unless you actually ran it.\n"
    )

    sections.append(
        "## After approval\n\n"
        "Save this proposal to a file, then the developer runs:\n\n"
        "```bash\n"
        f"devflow apply {request.id} <path-to-this-proposal.md>\n"
        "```\n"
    )

    return "\n".join(sections)
