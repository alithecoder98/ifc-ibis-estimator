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
    OLLAMA_BASE_URL_KEY,
    OLLAMA_EMBEDDING_MODEL_KEY,
    OLLAMA_LLM_MODEL_KEY,
)


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
class OllamaConnection:
    base_url: str
    embedding_model: str
    llm_model: str


def _get_or_default(db: Session, key: str, default: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row is not None else default


def get_ollama_connection(db: Session) -> OllamaConnection:
    defaults = get_settings()
    return OllamaConnection(
        base_url=_get_or_default(db, OLLAMA_BASE_URL_KEY, defaults.ollama_base_url),
        embedding_model=_get_or_default(
            db, OLLAMA_EMBEDDING_MODEL_KEY, defaults.ollama_embedding_model
        ),
        llm_model=_get_or_default(db, OLLAMA_LLM_MODEL_KEY, defaults.ollama_llm_model),
    )


def set_ollama_connection(
    db: Session, connection: OllamaConnection
) -> OllamaConnection:
    for key, value in (
        (OLLAMA_BASE_URL_KEY, connection.base_url),
        (OLLAMA_EMBEDDING_MODEL_KEY, connection.embedding_model),
        (OLLAMA_LLM_MODEL_KEY, connection.llm_model),
    ):
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return connection
