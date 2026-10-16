"""Tests whether a candidate Ollama connection (Admin > LLM Connectivity) is actually
reachable and has the configured models pulled, before an admin saves it - saving bad
values and only finding out on the next classification run would be a worse experience
than a quick live check.
"""

import httpx

from app.schemas import LLMConnectivityTestOut

TIMEOUT_SECONDS = 5.0


def _has_model(available: list[str], wanted: str) -> bool:
    # Ollama's /api/tags names include a version tag (e.g. "bge-m3:latest") - match on
    # the part before ":" too, since the configured model name usually omits it.
    wanted_base = wanted.split(":")[0]
    return any(
        name == wanted or name.split(":")[0] == wanted_base for name in available
    )


def test_ollama_connection(
    base_url: str, embedding_model: str, llm_model: str
) -> LLMConnectivityTestOut:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = httpx.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.TimeoutException:
        return LLMConnectivityTestOut(
            ok=False, message=f"Timed out connecting to {base_url}."
        )
    except httpx.HTTPError as exc:
        return LLMConnectivityTestOut(
            ok=False, message=f"Couldn't reach {base_url}: {exc}"
        )

    available = [m.get("name", "") for m in response.json().get("models", [])]
    missing = [
        model
        for model in (embedding_model, llm_model)
        if not _has_model(available, model)
    ]
    if missing:
        return LLMConnectivityTestOut(
            ok=False,
            message=(
                f"Connected to {base_url}, but not pulled yet: {', '.join(missing)}. "
                f"Run `ollama pull <model>` on that host."
            ),
            available_models=available,
        )
    return LLMConnectivityTestOut(
        ok=True,
        message=f"Connected to {base_url} - both models are available.",
        available_models=available,
    )
