"""Phase 3.4 — LLM-based classification, one call per group_hash (same "one lookup
per group" reasoning as jev/retrieval). Prompt combines the element profile, 3.3's
shortlisted candidates and similar examples, and docs/estimating_rules.md, read from
a versioned template file (app/ai/prompts/classify_v1.txt) rather than inlined, so a
prompt change is a visible diff to that one file.

Not wired into app/ai/classify.py yet - combining this signal with rules/jev into a
single routing decision is Phase 3.6/3.7's job, not this one's.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.db.models import CodeList, ExampleMemory

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE_PATH = Path(__file__).parent / "prompts" / "classify_v1.txt"
ESTIMATING_RULES_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "docs"
    / "estimating_rules.md"
)
MAX_ATTEMPTS = 3  # 1 try + 2 retries, per the plan


@dataclass
class LLMResult:
    ibis_code: str | None
    internal_element: str | None
    reasoning: str | None
    self_score: float | None
    flags: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Local/open-source model (Phase 3.1 decision) - always 0, not a placeholder.
    cost_usd: float = 0.0


class _LLMResponseSchema(BaseModel):
    ibis_code: str
    internal_element: str
    reasoning: str
    self_score: float = Field(ge=0.0, le=1.0)
    flags: list[str] = []


_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "ibis_code": {"type": "string"},
        "internal_element": {"type": "string"},
        "reasoning": {"type": "string"},
        "self_score": {"type": "number", "minimum": 0, "maximum": 1},
        "flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ibis_code", "internal_element", "reasoning", "self_score", "flags"],
}


class OllamaLLMClient:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, prompt: str) -> tuple[dict, int, int]:
        """Returns (parsed_json, prompt_tokens, completion_tokens). Raises
        json.JSONDecodeError if the model's output isn't valid JSON - the schema
        constrains generation but doesn't guarantee it (truncation, etc.).
        """
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "format": _RESPONSE_JSON_SCHEMA,
                "stream": False,
            },
            timeout=180.0,
        )
        response.raise_for_status()
        body = response.json()
        parsed = json.loads(body["message"]["content"])
        return (
            parsed,
            body.get("prompt_eval_count", 0),
            body.get("eval_count", 0),
        )


def get_llm_client() -> OllamaLLMClient:
    settings = get_settings()
    return OllamaLLMClient(settings.ollama_base_url, settings.ollama_llm_model)


def _format_candidates(candidates: list[CodeList]) -> str:
    if not candidates:
        return "(none found)"
    return "\n".join(
        f"- {c.ibis_code}: {c.internal_element} ({c.description or 'no description'})"
        for c in candidates
    )


def _format_examples(examples: list[ExampleMemory]) -> str:
    if not examples:
        return "(none found)"
    return "\n".join(
        f'- "{e.profile_text}" -> {e.final_ibis_code} ({e.final_internal_element})'
        for e in examples
    )


def load_estimating_rules() -> str:
    if not ESTIMATING_RULES_PATH.exists():
        return "(no estimating rules available)"
    return ESTIMATING_RULES_PATH.read_text(encoding="utf-8")


def render_prompt(
    profile_text: str,
    candidates: list[CodeList],
    examples: list[ExampleMemory],
    rules_text: str,
) -> str:
    return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8").format(
        profile_text=profile_text,
        candidates_block=_format_candidates(candidates),
        examples_block=_format_examples(examples),
        rules_text=rules_text,
    )


def classify_with_llm(
    client,
    profile_text: str,
    candidates: list[CodeList],
    examples: list[ExampleMemory],
    rules_text: str,
) -> LLMResult:
    """Validates the model's JSON against the strict schema and checks ibis_code is
    one of `candidates` or "NONE", retrying up to MAX_ATTEMPTS times total. After
    exhausting retries, returns a result flagged "llm_failed" rather than raising -
    same fail-safe-to-needs_review philosophy as StubJevClient.
    """
    valid_codes = {c.ibis_code for c in candidates}
    prompt = render_prompt(profile_text, candidates, examples, rules_text)

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            parsed, prompt_tokens, completion_tokens = client.chat(prompt)
            validated = _LLMResponseSchema(**parsed)
            if validated.ibis_code != "NONE" and validated.ibis_code not in valid_codes:
                raise ValueError(
                    f"ibis_code {validated.ibis_code!r} is not one of the candidates "
                    f"or 'NONE'"
                )
            return LLMResult(
                ibis_code=(
                    None if validated.ibis_code == "NONE" else validated.ibis_code
                ),
                internal_element=validated.internal_element,
                reasoning=validated.reasoning,
                self_score=validated.self_score,
                flags=validated.flags,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as exc:
            last_error = exc
            logger.warning(
                "LLM classification attempt %d/%d failed: %s",
                attempt,
                MAX_ATTEMPTS,
                exc,
            )

    logger.error("LLM classification exhausted retries: %s", last_error)
    return LLMResult(
        ibis_code=None,
        internal_element=None,
        reasoning=f"LLM failed after {MAX_ATTEMPTS} attempts: {last_error}",
        self_score=0.0,
        flags=["llm_failed"],
    )
