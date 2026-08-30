"""Tests for the generated IBM Bob investigation prompt.

The prompt is submitted evidence: it shows exactly what Bob was asked. It must
therefore contain only facts earlier phases established, and must preserve the
human approval boundary.
"""

from devflow.models.resolution import ResolutionRequest
from devflow.resolution._prompt import build_bob_prompt


def _request(**overrides):
    finding = {
        "id": "risk:0:code",
        "category": "risk",
        "title": "HIGH code risk",
        "description": "'src/flask/ctx.py' has 21 dependents through real import edges.",
        "affected_artifacts": ["src/flask/ctx.py"],
        "severity": "high",
        "is_inference": False,
        "recommendation": "Review the changed code path and its importing callers.",
        "evidence": [
            {
                "artifact": "src/flask/ctx.py",
                "description": "21 file(s) reach it through static import edges.",
                "evidence_type": "DIRECT_EVIDENCE",
            }
        ],
    }
    finding.update(overrides.pop("finding", {}))
    request = ResolutionRequest(
        id="res_20260830T000000Z_risk-0-code",
        repository_url="https://github.com/pallets/flask",
        owner="pallets",
        name="flask",
        change_summary="Refactor request context handling.",
        finding_id="risk:0:code",
        finding_snapshot=finding,
    )
    for key, value in overrides.items():
        setattr(request, key, value)
    return request


def test_prompt_identifies_the_repository_change_and_finding():
    prompt = build_bob_prompt(_request())
    assert "https://github.com/pallets/flask" in prompt
    assert "Refactor request context handling." in prompt
    assert "risk:0:code" in prompt
    assert "res_20260830T000000Z_risk-0-code" in prompt


def test_prompt_carries_the_evidence_and_labels_its_type():
    prompt = build_bob_prompt(_request())
    assert "21 file(s) reach it through static import edges." in prompt
    assert "DIRECT_EVIDENCE" in prompt
    assert "src/flask/ctx.py" in prompt


def test_prompt_preserves_the_human_approval_boundary():
    prompt = build_bob_prompt(_request())
    assert "Do not modify any file yet" in prompt
    assert "human approval" in prompt.lower()


def test_prompt_requests_parallel_subagent_investigation():
    prompt = build_bob_prompt(_request())
    assert "subagents" in prompt
    for skill in ("change-context", "impact-analysis", "historical-context", "evidence-report"):
        assert skill in prompt


def test_inference_findings_are_flagged_as_unconfirmed():
    prompt = build_bob_prompt(_request(finding={"is_inference": True}))
    assert "INFERENCE" in prompt
    assert "not an established defect" in prompt


def test_confirmed_findings_carry_no_inference_warning():
    prompt = build_bob_prompt(_request(finding={"is_inference": False}))
    assert "not an established defect" not in prompt


def test_prompt_forbids_fabricated_results():
    prompt = build_bob_prompt(_request())
    assert "Do not fabricate" in prompt
    assert "do not claim a test passed unless you actually ran it" in prompt.lower()


def test_prompt_states_devflow_will_verify_independently():
    prompt = build_bob_prompt(_request())
    assert "DevFlow will run the tests itself" in prompt


def test_recommendation_is_offered_without_being_binding():
    prompt = build_bob_prompt(_request())
    assert "Review the changed code path" in prompt
    assert "not a specification" in prompt


def test_prompt_omits_the_recommendation_section_when_absent():
    prompt = build_bob_prompt(_request(finding={"recommendation": None}))
    assert "DevFlow's recommended action" not in prompt


def test_prompt_handles_a_finding_without_evidence():
    prompt = build_bob_prompt(_request(finding={"evidence": []}))
    assert "Evidence DevFlow already gathered" not in prompt
    assert "risk:0:code" in prompt


def test_prompt_handles_a_finding_without_artifacts():
    prompt = build_bob_prompt(_request(finding={"affected_artifacts": []}))
    assert "(none recorded)" in prompt


def test_prompt_names_the_exact_follow_up_command():
    prompt = build_bob_prompt(_request())
    assert "devflow apply res_20260830T000000Z_risk-0-code" in prompt
