"""IBM watsonx.ai / Granite as DevFlow's evidence-backed priority judge.

DevFlow's deterministic pipeline decides what is true.  This module decides
only what to look at first.  The separation is enforced structurally, not by
prompt wording:

  * The model receives findings DevFlow already produced, with their evidence.
    It never receives repository source and is never asked for a fact.
  * The model returns identifiers and rationales.  Any identifier DevFlow did
    not produce is discarded and recorded.
  * Any finding the model omits is appended in deterministic order, so a
    ranking can never make a finding disappear.
  * Every failure path -- unconfigured, offline, timeout, malformed JSON,
    denied model, empty result -- falls back to deterministic ordering.

The result therefore always covers exactly DevFlow's own finding set, in some
order, whatever the model does.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from devflow.models.prioritization import (
    Prioritization,
    PrioritizationSource,
    RankedFinding,
    WatsonxError,
)
from devflow.watsonx._client import WatsonxClient, WatsonxConfig

logger = logging.getLogger(__name__)

# Ranking a long tail adds no value and costs tokens; the developer acts on the
# top of the list. The remainder is still returned, ordered deterministically.
MAX_FINDINGS_SENT = 25

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_CATEGORY_RANK = {"risk": 0, "impact": 1, "historical": 2, "context": 3}

_PROMPT = """You are a senior code reviewer triaging findings for a developer.

The findings below were produced by a deterministic repository analysis. Every
fact in them is already verified against the repository. Your ONLY job is to
decide the order in which a developer should investigate them, and to justify
each position using the evidence shown.

Rules you must follow:
- Rank ONLY the findings listed. Never introduce a finding_id that is not listed.
- Never state a new fact about the repository. Reason only from the evidence shown.
- Prefer findings with wide, import-proven blast radius and missing test coverage.
- Treat findings marked INFERENCE with more caution than those with direct evidence.
- Keep each rationale to one sentence, under 200 characters.

Change under review: {change_summary}
Repository: {repository}

FINDINGS:
{findings_block}

Respond with JSON only, no prose before or after, in exactly this shape:
{{"rankings": [{{"finding_id": "<id from the list>", "rationale": "<one sentence>"}}]}}
"""


def _finding_block(findings: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for finding in findings:
        evidence = finding.get("evidence") or []
        evidence_types = sorted(
            {str(item.get("evidence_type")) for item in evidence if item.get("evidence_type")}
        )
        artifacts = ", ".join(finding.get("affected_artifacts") or []) or "(none)"
        lines.append(
            "- finding_id: {fid}\n"
            "  category: {category} | severity: {severity} | "
            "evidence_strength: {strength} | inference_level: {inference}\n"
            "  title: {title}\n"
            "  artifacts: {artifacts}\n"
            "  evidence_types: {etypes} ({ecount} item(s))\n"
            "  description: {description}".format(
                fid=finding.get("id"),
                category=finding.get("category"),
                severity=finding.get("severity") or "unrated",
                strength=finding.get("evidence_strength") or "unrated",
                inference="yes" if finding.get("is_inference") else "no",
                title=_truncate(str(finding.get("title") or ""), 120),
                artifacts=_truncate(artifacts, 200),
                etypes=", ".join(evidence_types) or "none",
                ecount=len(evidence),
                description=_truncate(str(finding.get("description") or ""), 400),
            )
        )
    return "\n".join(lines)


def _truncate(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def deterministic_order(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DevFlow's own ordering: severity, then category, then evidence weight.

    This is the fallback and also the tie-break appended after any model
    ranking, so the full ordering is reproducible without a network call.
    """

    def sort_key(finding: dict[str, Any]) -> tuple:
        severity = str(finding.get("severity") or "").lower()
        category = str(finding.get("category") or "").lower()
        evidence = finding.get("evidence") or []
        direct = sum(
            1 for item in evidence if str(item.get("evidence_type")) == "DIRECT_EVIDENCE"
        )
        return (
            _SEVERITY_RANK.get(severity, 4),
            _CATEGORY_RANK.get(category, 5),
            -direct,
            1 if finding.get("is_inference") else 0,
            str(finding.get("id") or ""),
        )

    return sorted(findings, key=sort_key)


def _deterministic_result(
    findings: list[dict[str, Any]], *, error: Optional[str] = None
) -> Prioritization:
    ordered = deterministic_order(findings)
    return Prioritization(
        source=PrioritizationSource.DETERMINISTIC,
        rankings=[
            RankedFinding(
                finding_id=str(finding.get("id")),
                rank=position,
                rationale=_deterministic_rationale(finding),
                severity=finding.get("severity"),
                title=finding.get("title"),
                source=PrioritizationSource.DETERMINISTIC,
            )
            for position, finding in enumerate(ordered, start=1)
        ],
        error=error,
    )


def _deterministic_rationale(finding: dict[str, Any]) -> str:
    severity = str(finding.get("severity") or "unrated")
    evidence = finding.get("evidence") or []
    direct = sum(
        1 for item in evidence if str(item.get("evidence_type")) == "DIRECT_EVIDENCE"
    )
    return (
        f"Ordered deterministically: {severity} severity, "
        f"{direct} direct-evidence item(s), category {finding.get('category')}."
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a model response.

    Models often wrap JSON in prose or a code fence even when told not to, so
    fall back to the outermost braces rather than failing the whole ranking.
    """
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise WatsonxError("watsonx response contained no JSON object.")
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise WatsonxError("watsonx response was not parseable JSON.") from exc


def _validate_rankings(
    payload: dict[str, Any], findings: list[dict[str, Any]], model_id: Optional[str]
) -> Prioritization:
    """Constrain model output to DevFlow's own finding set.

    This is the guard that gives the ranking its credibility: the model may
    permute the list and annotate it, and may do nothing else.
    """
    by_id = {str(finding.get("id")): finding for finding in findings}
    raw_rankings = payload.get("rankings")
    if not isinstance(raw_rankings, list) or not raw_rankings:
        raise WatsonxError("watsonx response contained no 'rankings' list.")

    ordered: list[RankedFinding] = []
    seen: set[str] = set()
    discarded: list[str] = []

    for entry in raw_rankings:
        if not isinstance(entry, dict):
            continue
        finding_id = str(entry.get("finding_id") or "").strip()
        if not finding_id:
            continue
        if finding_id not in by_id:
            # The repository, not the model, decides what exists.
            discarded.append(finding_id)
            continue
        if finding_id in seen:
            continue
        seen.add(finding_id)
        finding = by_id[finding_id]
        ordered.append(
            RankedFinding(
                finding_id=finding_id,
                rank=len(ordered) + 1,
                rationale=_truncate(str(entry.get("rationale") or "").strip(), 300)
                or "No rationale returned.",
                severity=finding.get("severity"),
                title=finding.get("title"),
                source=PrioritizationSource.WATSONX,
            )
        )

    if not ordered:
        raise WatsonxError(
            "watsonx returned no ranking entry matching a DevFlow finding id."
        )

    # A ranking must never lose a finding: append everything the model omitted.
    appended: list[str] = []
    remaining = [finding for fid, finding in by_id.items() if fid not in seen]
    for finding in deterministic_order(remaining):
        finding_id = str(finding.get("id"))
        appended.append(finding_id)
        ordered.append(
            RankedFinding(
                finding_id=finding_id,
                rank=len(ordered) + 1,
                rationale=_deterministic_rationale(finding),
                severity=finding.get("severity"),
                title=finding.get("title"),
                source=PrioritizationSource.DETERMINISTIC,
            )
        )

    if discarded:
        logger.warning(
            "Discarded %d watsonx finding id(s) not present in DevFlow findings: %s",
            len(discarded),
            ", ".join(discarded),
        )

    return Prioritization(
        source=PrioritizationSource.WATSONX,
        rankings=ordered,
        model_id=model_id,
        discarded_finding_ids=discarded,
        appended_finding_ids=appended,
    )


# ---------------------------------------------------------------------------
# Response cache -- demo reliability without pretending a call happened
# ---------------------------------------------------------------------------


def _cache_path() -> Optional[Path]:
    raw = os.environ.get("DEVFLOW_WATSONX_CACHE", "").strip()
    return Path(raw) if raw else None


def _cache_key(repository: str, change_summary: str, findings: list[dict[str, Any]]) -> str:
    ids = "|".join(sorted(str(f.get("id")) for f in findings))
    return f"{repository}::{change_summary}::{ids}"


def _load_cached(key: str) -> Optional[str]:
    path = _cache_path()
    if path is None or not path.is_file():
        return None
    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("watsonx cache at %s could not be read; ignoring it.", path)
        return None
    value = store.get(key)
    return str(value) if isinstance(value, str) else None


def _store_cached(key: str, raw_response: str) -> None:
    path = _cache_path()
    if path is None:
        return
    store: dict[str, Any] = {}
    if path.is_file():
        try:
            store = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            store = {}
    store[key] = raw_response
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write watsonx cache at %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def prioritize_findings(
    report_payload: dict[str, Any],
    *,
    client: Optional[WatsonxClient] = None,
    config: Optional[WatsonxConfig] = None,
    use_cache: bool = True,
) -> Prioritization:
    """Rank a Developer Report's findings, preferring watsonx judgment.

    Always returns a Prioritization covering every input finding.  Never
    raises: any failure is reported through ``Prioritization.error`` with the
    deterministic ordering already in place.
    """
    findings = list(report_payload.get("findings") or [])
    if not findings:
        return Prioritization(source=PrioritizationSource.DETERMINISTIC, rankings=[])

    resolved_config = config or (client.config if client else WatsonxConfig())
    repository = str(report_payload.get("repository_url") or "")
    change_summary = str(report_payload.get("change_summary") or "")
    candidates = deterministic_order(findings)[:MAX_FINDINGS_SENT]
    key = _cache_key(repository, change_summary, candidates)

    raw: Optional[str] = None
    from_cache = False

    if use_cache:
        raw = _load_cached(key)
        from_cache = raw is not None

    if raw is None:
        gap = resolved_config.describe_gap()
        if gap:
            logger.info("Deterministic prioritization: %s", gap)
            return _deterministic_result(findings, error=gap)
        try:
            active = client or WatsonxClient(resolved_config)
            raw = active.generate(
                _PROMPT.format(
                    change_summary=_truncate(change_summary, 300) or "(not supplied)",
                    repository=repository or "(unknown)",
                    findings_block=_finding_block(candidates),
                )
            )
        except WatsonxError as exc:
            logger.warning("watsonx prioritization unavailable: %s", exc)
            return _deterministic_result(findings, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.warning("watsonx prioritization failed unexpectedly: %s", exc)
            return _deterministic_result(findings, error=f"Unexpected watsonx failure: {exc}")

    try:
        result = _validate_rankings(_extract_json(raw), findings, resolved_config.model_id)
    except WatsonxError as exc:
        logger.warning("watsonx prioritization rejected: %s", exc)
        return _deterministic_result(findings, error=str(exc))

    result.from_cache = from_cache
    if use_cache and not from_cache:
        _store_cached(key, raw)
    return result
