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
from sqlalchemy.orm import Session

from app.core.settings_store import get_llm_connection
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
    # True zero for Ollama (local, no per-call cost). For a paid OpenAI-compatible
    # provider this is NOT a real cost figure - per-token pricing varies by vendor
    # and model and changes over time, so this deliberately doesn't guess at one
    # rather than show a number that could be wrong. prompt_tokens/completion_tokens
    # above are the real, verifiable signal; multiply by your provider's published
    # rate if you need an actual cost.
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
            # 180s was tight enough to get hit for real on a large file's
            # classification pass under sustained GPU load (many back-to-back
            # calls on one consumer GPU) - confirmed live on a 47MB real file
            # (`Ifc2x3_SampleCastle.ifc`), where a single call legitimately
            # took longer than 180s and killed an otherwise-healthy job at
            # 87% progress. 480s gives real headroom per call while still
            # leaving most of the job-level 1200s budget (app/routers/
            # projects.py) for the many other calls in the same run.
            timeout=480.0,
        )
        # Bare raise_for_status() discards Ollama's actual error body, leaving
        # only httpx's generic "500 Internal Server Error" in stored job
        # errors - confirmed live against a real classification failure where
        # that generic message gave no way to diagnose what actually went
        # wrong upstream.
        if response.is_error:
            raise httpx.HTTPStatusError(
                f"Ollama chat request failed: {response.status_code} - {response.text[:500]}",
                request=response.request,
                response=response,
            )
        body = response.json()
        parsed = json.loads(body["message"]["content"])
        return (
            parsed,
            body.get("prompt_eval_count", 0),
            body.get("eval_count", 0),
        )


class OpenAICompatibleLLMClient:
    """Any provider speaking the OpenAI chat-completions API shape: OpenAI itself,
    OpenRouter, Groq, Together, or a local server like LM Studio/vLLM that mimics it.

    Uses response_format={"type": "json_object"} rather than the stricter
    json_schema/structured-outputs mode Ollama supports - schema-constrained
    generation isn't universally supported across this ecosystem (patchy on
    smaller/local servers especially), while plain JSON mode is close to
    universal. classify_v1.txt's prompt now spells out every field by name for
    exactly this reason (it used to lean on Ollama's schema to fill in fields it
    never named), and classify_with_llm()'s existing retry-on-bad-JSON loop
    covers a model that still gets the shape wrong.
    """

    def __init__(self, base_url: str, model: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def chat(self, prompt: str) -> tuple[dict, int, int]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            headers=headers,
            # Same reasoning as OllamaLLMClient's 480s - a classification pass
            # makes many back-to-back calls within one job's larger timeout
            # budget (app/routers/projects.py), so a single call needs real
            # headroom without eating the whole job's budget alone.
            timeout=480.0,
        )
        if response.is_error:
            raise httpx.HTTPStatusError(
                f"Chat completion request failed: {response.status_code} - "
                f"{response.text[:500]}",
                request=response.request,
                response=response,
            )
        body = response.json()
        parsed = json.loads(body["choices"][0]["message"]["content"])
        usage = body.get("usage", {})
        return (
            parsed,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )


def get_llm_client(db: Session) -> OllamaLLMClient | OpenAICompatibleLLMClient:
    # DB-backed - see app/ai/embedder.py's get_embedder() for why.
    connection = get_llm_connection(db)
    if connection.provider == "openai_compatible":
        return OpenAICompatibleLLMClient(
            connection.base_url, connection.llm_model, connection.api_key
        )
    return OllamaLLMClient(connection.base_url, connection.llm_model)


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
        except (
            json.JSONDecodeError,
            ValidationError,
            ValueError,
            KeyError,
            httpx.HTTPError,
        ) as exc:
            # httpx.HTTPError (covers HTTPStatusError and timeouts) wasn't
            # caught here before - confirmed live that it isn't just a
            # theoretical gap: a real 47MB file hit Ollama's own
            # "prediction aborted, token repeat limit reached" safety net on
            # one element group among 2000+, and because HTTPStatusError
            # wasn't in this tuple it propagated straight out of
            # classify_elements() and killed the entire otherwise-successful
            # job instead of retrying and failing safe on just that one
            # group, same as every other classification failure mode here.
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
