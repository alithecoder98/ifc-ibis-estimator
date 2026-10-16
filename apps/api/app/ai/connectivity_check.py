"""Tests whether a candidate LLM connection (Admin > LLM Connectivity) is actually
reachable and has the configured models available, before an admin saves it - saving
bad values and only finding out on the next classification run would be a worse
experience than a quick live check. Covers both supported providers: Ollama (local,
no auth, "pulled or not" is unambiguous) and any OpenAI-compatible API (a provider's
/models listing is a weaker signal - some proxies don't implement it fully - so that
path reports what it can confirm without being falsely certain about what it can't).
"""

import httpx

from app.schemas import LLMConnectivityTestOut

TIMEOUT_SECONDS = 5.0


def _model_matches(available: str, wanted: str) -> bool:
    # Ollama's /api/tags names include a version tag (e.g. "bge-m3:latest") - match
    # on the part before ":" too, since the configured model name usually omits it.
    return available == wanted or available.split(":")[0] == wanted.split(":")[0]


def _has_model(available: list[str], wanted: str) -> bool:
    return any(_model_matches(name, wanted) for name in available)


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


def test_openai_compatible_connection(
    base_url: str, embedding_model: str, llm_model: str, api_key: str
) -> LLMConnectivityTestOut:
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        return LLMConnectivityTestOut(
            ok=False, message=f"Timed out connecting to {base_url}."
        )
    except httpx.HTTPError as exc:
        return LLMConnectivityTestOut(
            ok=False, message=f"Couldn't reach {base_url}: {exc}"
        )

    if response.status_code in (401, 403):
        return LLMConnectivityTestOut(
            ok=False,
            message=f"{base_url} rejected the request ({response.status_code}) - "
            f"check the API key.",
        )
    if response.is_error:
        return LLMConnectivityTestOut(
            ok=False,
            message=f"Couldn't reach {base_url}: {response.status_code} - "
            f"{response.text[:300]}",
        )

    available = [m.get("id", "") for m in response.json().get("data", [])]
    missing = [
        model
        for model in (embedding_model, llm_model)
        if not _has_model(available, model)
    ]
    if missing:
        # Connection + auth genuinely worked (we got a 200), but unlike Ollama's
        # local "pulled or not" this listing isn't a guaranteed-complete signal
        # for every provider - said as a caveat, not a hard failure claim.
        return LLMConnectivityTestOut(
            ok=False,
            message=(
                f"Connected to {base_url}, but didn't see in its model list: "
                f"{', '.join(missing)}. If you're sure the name is right, some "
                f"providers don't list every model here - try it for real."
            ),
            available_models=available,
        )
    return LLMConnectivityTestOut(
        ok=True,
        message=f"Connected to {base_url} - both models are listed.",
        available_models=available,
    )
