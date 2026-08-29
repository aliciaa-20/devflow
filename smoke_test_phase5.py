"""Controlled Phase 5 smoke test against https://github.com/encode/httpx.

This validates only structured, artifact-backed risks. It makes no changes,
uses no API/LLM services, and exits non-zero if a risk cites an unknown path
or presents an inference as confirmed.
"""

import sys

from devflow.context import build_context
from devflow.history import build_historical_context
from devflow.impact import build_impact_analysis
from devflow.input import accept_input
from devflow.models.impact import EvidenceType
from devflow.risk import build_risk_analysis


URL = "https://github.com/encode/httpx"
CHANGE = "Improve connection pooling behavior for async clients."


def main() -> None:
    # The declared file makes the smoke test's requested change explicit;
    # it is a real HTTPX artifact relevant to async-client pooling behavior.
    repository, change = accept_input(URL, CHANGE, ["httpx/_client.py"])
    context = build_context(repository, change, clone_timeout=180)
    if context.error:
        raise RuntimeError(f"Phase 2 failed: {context.error}")
    history = build_historical_context(repository, context, clone_timeout=180, max_artifacts=30)
    if history.error:
        print(f"Phase 3 warning: {history.error}")
        history = None
    impact = build_impact_analysis(context, history)
    if impact.error:
        raise RuntimeError(f"Phase 4 failed: {impact.error}")
    risks = build_risk_analysis(impact, context, history)
    if risks.error:
        raise RuntimeError(f"Phase 5 failed: {risks.error}")

    known_paths = set(context.all_files) | {artifact.path for artifact in context.artifacts}
    for risk in risks.risks:
        if not set(risk.affected_artifacts) <= known_paths:
            raise RuntimeError(f"Risk references unknown artifacts: {risk.affected_artifacts}")
        if not risk.evidence or not risk.recommended_action:
            raise RuntimeError(f"Risk lacks evidence or recommendation: {risk}")
        if risk.is_inference and risk.assessment_type != EvidenceType.INFERENCE:
            raise RuntimeError(f"Risk inference label is inconsistent: {risk}")

    print(f"Phase 5 smoke test passed: {len(risks.risks)} risks for {URL}")
    for risk in risks.risks:
        print(f"- {risk.severity.value} {risk.category.value}: {', '.join(risk.affected_artifacts)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
