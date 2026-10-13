"""Phase 3.4: LLM classifier.

Mocked client throughout, per the plan's own "tests with a mocked client" - no real
Ollama call needed to prove the retry/validation logic is correct. See
scripts/run_llm_classification.py for the manual real-model run the plan separately
asks for.
"""

import json

import pytest

from app.ai.llm import LLMResult, classify_with_llm, render_prompt
from app.db.models import CodeList, ExampleMemory

CANDIDATES = [
    CodeList(
        ibis_code="21.10",
        internal_element="Buitenwand beton",
        description="concrete exterior wall",
        family="wall",
    ),
    CodeList(
        ibis_code="41.10",
        internal_element="Dakconstructie hout",
        description="timber roof truss",
        family="roof",
    ),
]
EXAMPLES = [
    ExampleMemory(
        profile_text="IfcWall, Concrete, 200mm, external",
        final_ibis_code="21.10",
        final_internal_element="Buitenwand beton",
    )
]
VALID_RESPONSE = {
    "ibis_code": "21.10",
    "internal_element": "Buitenwand beton",
    "reasoning": "matches concrete exterior wall",
    "self_score": 0.9,
    "flags": [],
}


class ScriptedClient:
    """Returns each entry of `responses` in order, one per call. An entry that's a
    dict is a (parsed_json, prompt_tokens, completion_tokens) success; a string is
    raised as the literal exception message via json.JSONDecodeError, simulating an
    unparsable model output.
    """

    def __init__(self, responses: list):
        self.responses = responses
        self.call_count = 0

    def chat(self, prompt: str):
        response = self.responses[self.call_count]
        self.call_count += 1
        if isinstance(response, str):
            raise json.JSONDecodeError(response, response, 0)
        parsed, prompt_tokens, completion_tokens = response
        return parsed, prompt_tokens, completion_tokens


def test_render_prompt_includes_profile_candidates_examples_and_rules() -> None:
    prompt = render_prompt(
        "IfcWall, Concrete, 200mm, external", CANDIDATES, EXAMPLES, "Some rule text"
    )
    assert "IfcWall, Concrete, 200mm, external" in prompt
    assert "21.10: Buitenwand beton" in prompt
    assert "41.10: Dakconstructie hout" in prompt
    assert 'IfcWall, Concrete, 200mm, external" -> 21.10' in prompt
    assert "Some rule text" in prompt


def test_render_prompt_handles_no_candidates_or_examples() -> None:
    prompt = render_prompt("profile", [], [], "rules")
    assert "(none found)" in prompt


def test_classify_with_llm_succeeds_on_first_attempt() -> None:
    client = ScriptedClient([(VALID_RESPONSE, 100, 20)])
    result = classify_with_llm(client, "profile", CANDIDATES, EXAMPLES, "rules")

    assert isinstance(result, LLMResult)
    assert result.ibis_code == "21.10"
    assert result.internal_element == "Buitenwand beton"
    assert result.self_score == 0.9
    assert result.flags == []
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 20
    assert result.cost_usd == 0.0
    assert client.call_count == 1


def test_classify_with_llm_retries_on_bad_json_then_succeeds() -> None:
    client = ScriptedClient(["not valid json", (VALID_RESPONSE, 10, 5)])
    result = classify_with_llm(client, "profile", CANDIDATES, EXAMPLES, "rules")

    assert result.ibis_code == "21.10"
    assert client.call_count == 2


def test_classify_with_llm_retries_on_code_not_in_candidates() -> None:
    bad_code_response = {**VALID_RESPONSE, "ibis_code": "99.99"}
    client = ScriptedClient([(bad_code_response, 10, 5), (VALID_RESPONSE, 10, 5)])
    result = classify_with_llm(client, "profile", CANDIDATES, EXAMPLES, "rules")

    assert result.ibis_code == "21.10"
    assert client.call_count == 2


def test_classify_with_llm_retries_on_self_score_out_of_range() -> None:
    bad_score_response = {**VALID_RESPONSE, "self_score": 1.5}
    client = ScriptedClient([(bad_score_response, 10, 5), (VALID_RESPONSE, 10, 5)])
    result = classify_with_llm(client, "profile", CANDIDATES, EXAMPLES, "rules")

    assert result.ibis_code == "21.10"
    assert client.call_count == 2


def test_classify_with_llm_none_response_maps_to_none_ibis_code() -> None:
    none_response = {**VALID_RESPONSE, "ibis_code": "NONE"}
    client = ScriptedClient([(none_response, 10, 5)])
    result = classify_with_llm(client, "profile", CANDIDATES, EXAMPLES, "rules")

    assert result.ibis_code is None
    assert result.flags == []


def test_classify_with_llm_exhausts_retries_and_returns_flagged_failure() -> None:
    client = ScriptedClient(["bad"] * 5)  # more failures than MAX_ATTEMPTS
    result = classify_with_llm(client, "profile", CANDIDATES, EXAMPLES, "rules")

    assert result.ibis_code is None
    assert result.self_score == 0.0
    assert result.flags == ["llm_failed"]
    assert client.call_count == 3  # MAX_ATTEMPTS, not all 5 available responses


@pytest.mark.parametrize("candidates", [[], CANDIDATES])
def test_classify_with_llm_handles_empty_candidate_list(candidates: list) -> None:
    # An empty candidate list only leaves "NONE" as valid - exercise both shapes to
    # make sure the valid_codes set check doesn't accidentally reject every code
    # when candidates is empty.
    none_response = {**VALID_RESPONSE, "ibis_code": "NONE"}
    client = ScriptedClient([(none_response, 10, 5)])
    result = classify_with_llm(client, "profile", candidates, EXAMPLES, "rules")
    assert result.ibis_code is None
