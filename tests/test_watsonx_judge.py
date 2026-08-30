"""Tests for watsonx.ai as the evidence-backed priority judge.

No test performs network I/O: the client's transport is injected.  The
invariant under test throughout is that the model may reorder and annotate
DevFlow's findings and may do nothing else.
"""

import io
import json

import pytest

from devflow.models.prioritization import PrioritizationSource, WatsonxError
from devflow.watsonx import (
    DEFAULT_MODEL_ID,
    WatsonxClient,
    WatsonxConfig,
    deterministic_order,
    is_denied_model,
    prioritize_findings,
)

WATSONX_ENV = (
    "DEVFLOW_WATSONX_APIKEY",
    "DEVFLOW_WATSONX_PROJECT_ID",
    "DEVFLOW_WATSONX_URL",
    "DEVFLOW_WATSONX_MODEL",
    "DEVFLOW_WATSONX_CACHE",
    "DEVFLOW_WATSONX_DISABLE",
    "DEVFLOW_WATSONX_TIMEOUT",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Never let a developer's real credentials leak into a test run.

    Both halves matter: clearing the environment, and stubbing the .env loader
    so a populated local .env cannot silently reconfigure these tests into
    making real network calls.
    """
    for name in WATSONX_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("devflow.watsonx._client.load_dotenv", lambda *a, **k: [])


def _finding(fid, category="risk", severity="high", direct=1, inference=False, title=None):
    return {
        "id": fid,
        "category": category,
        "title": title or f"{severity} {category} finding",
        "description": f"Description for {fid}",
        "affected_artifacts": [f"src/{fid}.py"],
        "severity": severity,
        "evidence": [
            {"artifact": f"src/{fid}.py", "description": "edge", "evidence_type": "DIRECT_EVIDENCE"}
        ]
        * direct,
        "evidence_strength": "confirmed",
        "is_inference": inference,
    }


def _report(*findings):
    return {
        "repository_url": "https://github.com/example/repo",
        "change_summary": "Refactor session handling.",
        "findings": list(findings),
    }


def _configured():
    return WatsonxConfig(api_key="test-key", project_id="test-project")


def _client_returning(text, *, config=None, calls=None):
    """A client whose transport answers IAM then generation, without network."""

    def transport(url, data, headers, timeout):
        if calls is not None:
            calls.append(url)
        if "iam.cloud.ibm.com" in url:
            return json.dumps({"access_token": "tok", "expires_in": 3600})
        return json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]})

    return WatsonxClient(config or _configured(), transport=transport)


# ---------------------------------------------------------------------------
# Deterministic path
# ---------------------------------------------------------------------------


def test_unconfigured_watsonx_falls_back_to_deterministic_ranking():
    result = prioritize_findings(_report(_finding("a"), _finding("b", severity="low")))
    assert result.source == PrioritizationSource.DETERMINISTIC
    assert "not configured" in (result.error or "")
    assert [r.finding_id for r in result.rankings] == ["a", "b"]


def test_disable_flag_forces_deterministic_ranking(monkeypatch):
    monkeypatch.setenv("DEVFLOW_WATSONX_APIKEY", "key")
    monkeypatch.setenv("DEVFLOW_WATSONX_PROJECT_ID", "project")
    monkeypatch.setenv("DEVFLOW_WATSONX_DISABLE", "true")
    result = prioritize_findings(_report(_finding("a")))
    assert result.source == PrioritizationSource.DETERMINISTIC
    assert "disabled" in (result.error or "")


def test_deterministic_order_prefers_severity_then_direct_evidence():
    findings = [
        _finding("low", severity="low"),
        _finding("critical", severity="critical"),
        _finding("high_thin", severity="high", direct=1),
        _finding("high_thick", severity="high", direct=4),
    ]
    ordered = [f["id"] for f in deterministic_order(findings)]
    assert ordered == ["critical", "high_thick", "high_thin", "low"]


def test_empty_findings_produce_an_empty_ranking():
    result = prioritize_findings(_report())
    assert result.rankings == []
    assert result.error is None


# ---------------------------------------------------------------------------
# watsonx path and its guard rails
# ---------------------------------------------------------------------------


def test_watsonx_ranking_is_applied_when_valid():
    response = json.dumps(
        {
            "rankings": [
                {"finding_id": "b", "rationale": "Wider blast radius."},
                {"finding_id": "a", "rationale": "Locally contained."},
            ]
        }
    )
    result = prioritize_findings(
        _report(_finding("a"), _finding("b")), client=_client_returning(response)
    )
    assert result.source == PrioritizationSource.WATSONX
    assert [r.finding_id for r in result.rankings] == ["b", "a"]
    assert result.rankings[0].rationale == "Wider blast radius."
    assert result.model_id == DEFAULT_MODEL_ID


def test_invented_finding_ids_are_discarded_and_recorded():
    """The repository, not the model, decides what exists."""
    response = json.dumps(
        {
            "rankings": [
                {"finding_id": "does-not-exist", "rationale": "Hallucinated."},
                {"finding_id": "a", "rationale": "Real."},
            ]
        }
    )
    result = prioritize_findings(_report(_finding("a")), client=_client_returning(response))
    assert result.discarded_finding_ids == ["does-not-exist"]
    assert [r.finding_id for r in result.rankings] == ["a"]


def test_omitted_findings_are_appended_never_dropped():
    response = json.dumps({"rankings": [{"finding_id": "b", "rationale": "First."}]})
    result = prioritize_findings(
        _report(_finding("a"), _finding("b"), _finding("c")),
        client=_client_returning(response),
    )
    assert [r.finding_id for r in result.rankings] == ["b", "a", "c"]
    assert result.appended_finding_ids == ["a", "c"]
    # Appended entries are honestly labelled as deterministic, not model judgment.
    assert result.rankings[0].source == PrioritizationSource.WATSONX
    assert result.rankings[1].source == PrioritizationSource.DETERMINISTIC


def test_ranking_always_covers_every_input_finding():
    response = json.dumps({"rankings": [{"finding_id": "a", "rationale": "Only one."}]})
    findings = [_finding(name) for name in ("a", "b", "c", "d")]
    result = prioritize_findings(_report(*findings), client=_client_returning(response))
    assert {r.finding_id for r in result.rankings} == {"a", "b", "c", "d"}
    assert [r.rank for r in result.rankings] == [1, 2, 3, 4]


def test_duplicate_ids_in_the_response_are_collapsed():
    response = json.dumps(
        {
            "rankings": [
                {"finding_id": "a", "rationale": "First."},
                {"finding_id": "a", "rationale": "Again."},
            ]
        }
    )
    result = prioritize_findings(_report(_finding("a"), _finding("b")), client=_client_returning(response))
    assert [r.finding_id for r in result.rankings] == ["a", "b"]


def test_json_wrapped_in_a_code_fence_is_still_parsed():
    response = '```json\n{"rankings": [{"finding_id": "a", "rationale": "Fenced."}]}\n```'
    result = prioritize_findings(_report(_finding("a")), client=_client_returning(response))
    assert result.source == PrioritizationSource.WATSONX
    assert result.rankings[0].rationale == "Fenced."


def test_json_surrounded_by_prose_is_still_parsed():
    response = 'Here you go: {"rankings": [{"finding_id": "a", "rationale": "Prose."}]} Hope that helps!'
    result = prioritize_findings(_report(_finding("a")), client=_client_returning(response))
    assert result.source == PrioritizationSource.WATSONX


def test_unparseable_response_falls_back_deterministically():
    result = prioritize_findings(
        _report(_finding("a"), _finding("b")), client=_client_returning("not json at all")
    )
    assert result.source == PrioritizationSource.DETERMINISTIC
    assert result.error
    assert len(result.rankings) == 2


def test_response_with_only_unknown_ids_falls_back_deterministically():
    response = json.dumps({"rankings": [{"finding_id": "ghost", "rationale": "Nope."}]})
    result = prioritize_findings(_report(_finding("a")), client=_client_returning(response))
    assert result.source == PrioritizationSource.DETERMINISTIC
    assert "no ranking entry matching" in (result.error or "")


def test_transport_failure_falls_back_deterministically():
    def failing(url, data, headers, timeout):
        raise OSError("connection reset")

    client = WatsonxClient(_configured(), transport=failing)
    result = prioritize_findings(_report(_finding("a")), client=client)
    assert result.source == PrioritizationSource.DETERMINISTIC
    assert result.error


def test_severity_and_title_are_carried_from_devflow_not_the_model():
    """The model cannot restate a fact: severity comes from the finding."""
    response = json.dumps(
        {"rankings": [{"finding_id": "a", "rationale": "x", "severity": "critical"}]}
    )
    result = prioritize_findings(
        _report(_finding("a", severity="low", title="Real title")),
        client=_client_returning(response),
    )
    assert result.rankings[0].severity == "low"
    assert result.rankings[0].title == "Real title"


def test_long_rationale_is_truncated():
    response = json.dumps({"rankings": [{"finding_id": "a", "rationale": "x" * 900}]})
    result = prioritize_findings(_report(_finding("a")), client=_client_returning(response))
    assert len(result.rankings[0].rationale) <= 300


# ---------------------------------------------------------------------------
# Model policy and credentials
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_id",
    [
        "meta-llama/llama-3-405b-instruct",
        "mistralai/mistral-medium-2505",
        "mistralai/mistral-small-3-1-24b-instruct-2503",
    ],
)
def test_hackathon_denied_models_are_refused(model_id):
    assert is_denied_model(model_id)
    config = WatsonxConfig(api_key="k", project_id="p", model_id=model_id)
    client = _client_returning('{"rankings": []}', config=config)
    with pytest.raises(WatsonxError, match="out of scope"):
        client.generate("prompt")


def test_default_model_is_granite_and_allowed():
    assert "granite" in DEFAULT_MODEL_ID
    assert not is_denied_model(DEFAULT_MODEL_ID)


def test_empty_completion_is_reported_rather_than_ranked():
    """A chat-tuned model given a bad prompt returns '' with HTTP 200."""
    client = _client_returning("")
    with pytest.raises(WatsonxError, match="empty completion"):
        client.generate("prompt")


def test_empty_completion_falls_back_to_deterministic_ranking():
    result = prioritize_findings(_report(_finding("a")), client=_client_returning(""))
    assert result.source == PrioritizationSource.DETERMINISTIC
    assert "empty completion" in (result.error or "")


def test_api_error_body_is_surfaced_not_swallowed():
    """A bare status code hides the fix; the API's own message does not."""
    import urllib.error

    def failing(url, data, headers, timeout):
        if "iam.cloud.ibm.com" in url:
            return json.dumps({"access_token": "tok", "expires_in": 3600})
        raise urllib.error.HTTPError(
            url,
            404,
            "Not Found",
            {},
            io.BytesIO(
                json.dumps(
                    {"errors": [{"code": "model_not_supported", "message": "Model X not found."}]}
                ).encode()
            ),
        )

    client = WatsonxClient(_configured(), transport=failing)
    with pytest.raises(WatsonxError, match="Model X not found."):
        client.generate("prompt")


def test_config_gap_message_never_reveals_credentials():
    config = WatsonxConfig(api_key="super-secret-value", project_id="")
    message = config.describe_gap()
    assert "super-secret-value" not in message
    assert "DEVFLOW_WATSONX_PROJECT_ID" in message


def test_iam_token_is_requested_before_generation():
    calls = []
    response = json.dumps({"rankings": [{"finding_id": "a", "rationale": "ok"}]})
    prioritize_findings(
        _report(_finding("a")), client=_client_returning(response, calls=calls)
    )
    assert "iam.cloud.ibm.com" in calls[0]
    assert "ml/v1/text/chat" in calls[1]


def test_iam_token_is_reused_across_calls():
    calls = []
    client = _client_returning(
        json.dumps({"rankings": [{"finding_id": "a", "rationale": "ok"}]}), calls=calls
    )
    prioritize_findings(_report(_finding("a")), client=client, use_cache=False)
    prioritize_findings(_report(_finding("a")), client=client, use_cache=False)
    assert sum(1 for url in calls if "iam.cloud.ibm.com" in url) == 1


# ---------------------------------------------------------------------------
# Demo-reliability cache
# ---------------------------------------------------------------------------


def test_cached_response_is_replayed_without_calling_watsonx(tmp_path, monkeypatch):
    cache = tmp_path / "watsonx-cache.json"
    monkeypatch.setenv("DEVFLOW_WATSONX_CACHE", str(cache))
    response = json.dumps({"rankings": [{"finding_id": "a", "rationale": "Cached."}]})
    report = _report(_finding("a"), _finding("b"))

    calls = []
    first = prioritize_findings(report, client=_client_returning(response, calls=calls))
    assert first.source == PrioritizationSource.WATSONX
    assert not first.from_cache
    assert cache.is_file()

    def must_not_be_called(url, data, headers, timeout):
        raise AssertionError("cache hit must not reach the network")

    replay = prioritize_findings(
        report, client=WatsonxClient(_configured(), transport=must_not_be_called)
    )
    assert replay.source == PrioritizationSource.WATSONX
    assert replay.from_cache
    assert replay.rankings[0].rationale == "Cached."


def test_cache_replays_even_when_credentials_are_absent(tmp_path, monkeypatch):
    """Demo reliability: a recorded answer survives losing the network."""
    cache = tmp_path / "cache.json"
    monkeypatch.setenv("DEVFLOW_WATSONX_CACHE", str(cache))
    response = json.dumps({"rankings": [{"finding_id": "a", "rationale": "Recorded."}]})
    report = _report(_finding("a"))
    prioritize_findings(report, client=_client_returning(response))

    unconfigured = prioritize_findings(report, config=WatsonxConfig(api_key="", project_id=""))
    assert unconfigured.source == PrioritizationSource.WATSONX
    assert unconfigured.from_cache


def test_cache_is_keyed_by_finding_set(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    monkeypatch.setenv("DEVFLOW_WATSONX_CACHE", str(cache))
    response = json.dumps({"rankings": [{"finding_id": "a", "rationale": "One."}]})
    prioritize_findings(_report(_finding("a")), client=_client_returning(response))

    # A different finding set must miss the cache, not silently reuse the answer.
    result = prioritize_findings(
        _report(_finding("z")), config=WatsonxConfig(api_key="", project_id="")
    )
    assert result.source == PrioritizationSource.DETERMINISTIC


def test_corrupt_cache_file_is_ignored(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    cache.write_text("{ not json", encoding="utf-8")
    monkeypatch.setenv("DEVFLOW_WATSONX_CACHE", str(cache))
    result = prioritize_findings(_report(_finding("a")))
    assert result.source == PrioritizationSource.DETERMINISTIC
