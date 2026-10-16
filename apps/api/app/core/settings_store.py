"""DB-backed overrides for a handful of runtime settings (Phase 4.6's admin area).

Distinct from app/core/config.py's Settings: those are env-var/.env-sourced and
fixed for a process's lifetime (pydantic-settings, lru_cached). An admin changing
the auto-accept threshold needs it to take effect on the very next classification
run, not after a restart - hence a tiny DB-backed override, checked first, falling
back to the env-sourced default when no row exists yet (e.g. a fresh database).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AppSetting
from app.db.models.settings import (
    AUTO_ACCEPT_THRESHOLD_KEY,
    LLM_API_KEY_KEY,
    LLM_PROVIDER_KEY,
    OLLAMA_BASE_URL_KEY,
    OLLAMA_EMBEDDING_MODEL_KEY,
    OLLAMA_LLM_MODEL_KEY,
)

OPENAI_COMPATIBLE_DEFAULT_BASE_URL = "https://api.openai.com/v1"
# NOT "text-embedding-3-small" - OpenAI's own embedding models default to 1536/3072
# dimensions, not the 1024 this database's pgvector column is fixed at (see
# app/ai/embedder.py's _check_dims), so suggesting one as the default would hand a
# first-time OpenAI-compatible user a value guaranteed to fail on the very next
# embedding call. "bge-m3" is dimension-safe and, unlike the Ollama default, is also
# commonly served over an OpenAI-compatible endpoint (text-embeddings-inference,
# Infinity, LM Studio, etc.) - a real, not just a safe-but-useless, placeholder.
OPENAI_COMPATIBLE_DEFAULT_EMBEDDING_MODEL = "bge-m3"
OPENAI_COMPATIBLE_DEFAULT_LLM_MODEL = "gpt-4o-mini"


def get_auto_accept_threshold(db: Session) -> float:
    row = db.get(AppSetting, AUTO_ACCEPT_THRESHOLD_KEY)
    if row is None:
        return get_settings().auto_accept_threshold
    return float(row.value)


def set_auto_accept_threshold(db: Session, value: float) -> float:
    row = db.get(AppSetting, AUTO_ACCEPT_THRESHOLD_KEY)
    if row is None:
        row = AppSetting(key=AUTO_ACCEPT_THRESHOLD_KEY, value=str(value))
        db.add(row)
    else:
        row.value = str(value)
    db.commit()
    return value


@dataclass
class LLMConnection:
    # "ollama" (no auth, self-hosted) or "openai_compatible" (any provider
    # speaking the OpenAI chat-completions/embeddings API shape - OpenAI itself,
    # OpenRouter, Groq, Together, or a local server like LM Studio/vLLM).
    provider: str
    base_url: str
    embedding_model: str
    llm_model: str
    api_key: str = ""


def _get_or_default(db: Session, key: str, default: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row is not None else default


def get_llm_connection(db: Session) -> LLMConnection:
    defaults = get_settings()
    provider = _get_or_default(db, LLM_PROVIDER_KEY, "ollama")
    is_ollama = provider != "openai_compatible"
    return LLMConnection(
        provider=provider,
        base_url=_get_or_default(
            db,
            OLLAMA_BASE_URL_KEY,
            (
                defaults.ollama_base_url
                if is_ollama
                else OPENAI_COMPATIBLE_DEFAULT_BASE_URL
            ),
        ),
        embedding_model=_get_or_default(
            db,
            OLLAMA_EMBEDDING_MODEL_KEY,
            (
                defaults.ollama_embedding_model
                if is_ollama
                else OPENAI_COMPATIBLE_DEFAULT_EMBEDDING_MODEL
            ),
        ),
        llm_model=_get_or_default(
            db,
            OLLAMA_LLM_MODEL_KEY,
            (
                defaults.ollama_llm_model
                if is_ollama
                else OPENAI_COMPATIBLE_DEFAULT_LLM_MODEL
            ),
        ),
        api_key=_get_or_default(db, LLM_API_KEY_KEY, ""),
    )


def set_llm_connection(
    db: Session, connection: LLMConnection, *, update_api_key: bool
) -> LLMConnection:
    # update_api_key=False means "leave whatever's already saved alone" - the
    # settings endpoint never echoes a saved key back to the frontend (see
    # LLMConnectivityOut), so there's no value for a save-without-changing-it
    # request to resubmit; treating a blank/omitted key as "don't touch" avoids
    # silently wiping a real key every time someone only changes the model name.
    fields = [
        (LLM_PROVIDER_KEY, connection.provider),
        (OLLAMA_BASE_URL_KEY, connection.base_url),
        (OLLAMA_EMBEDDING_MODEL_KEY, connection.embedding_model),
        (OLLAMA_LLM_MODEL_KEY, connection.llm_model),
    ]
    if update_api_key:
        fields.append((LLM_API_KEY_KEY, connection.api_key))
    for key, value in fields:
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return get_llm_connection(db)
