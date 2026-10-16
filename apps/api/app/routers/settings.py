"""Admin-editable runtime settings (Phase 4.6: auto-accept threshold; this session:
LLM Connectivity). See app/core/settings_store.py for why these are DB-backed rather
than the env-sourced app/core/config.py Settings - an admin changing either needs it
to take effect on the next classification run, not after a restart.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.ollama_connectivity import test_ollama_connection
from app.core.deps import require_role
from app.core.settings_store import (
    OllamaConnection,
    get_auto_accept_threshold,
    get_ollama_connection,
    set_auto_accept_threshold,
    set_ollama_connection,
)
from app.db.models import User
from app.db.session import get_db
from app.schemas import (
    LLMConnectivityOut,
    LLMConnectivityTestOut,
    LLMConnectivityUpdate,
    ThresholdOut,
    ThresholdUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/threshold", response_model=ThresholdOut)
def get_threshold(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> ThresholdOut:
    return ThresholdOut(auto_accept_threshold=get_auto_accept_threshold(db))


@router.patch("/threshold", response_model=ThresholdOut)
def update_threshold(
    body: ThresholdUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> ThresholdOut:
    value = set_auto_accept_threshold(db, body.auto_accept_threshold)
    return ThresholdOut(auto_accept_threshold=value)


@router.get("/llm", response_model=LLMConnectivityOut)
def get_llm_connectivity(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> LLMConnectivityOut:
    connection = get_ollama_connection(db)
    return LLMConnectivityOut(
        base_url=connection.base_url,
        embedding_model=connection.embedding_model,
        llm_model=connection.llm_model,
    )


@router.patch("/llm", response_model=LLMConnectivityOut)
def update_llm_connectivity(
    body: LLMConnectivityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> LLMConnectivityOut:
    connection = set_ollama_connection(
        db,
        OllamaConnection(
            base_url=body.base_url,
            embedding_model=body.embedding_model,
            llm_model=body.llm_model,
        ),
    )
    return LLMConnectivityOut(
        base_url=connection.base_url,
        embedding_model=connection.embedding_model,
        llm_model=connection.llm_model,
    )


@router.post("/llm/test", response_model=LLMConnectivityTestOut)
def test_llm_connectivity(
    body: LLMConnectivityUpdate,
    user: User = Depends(require_role("admin")),
) -> LLMConnectivityTestOut:
    # Tests the submitted values directly, not whatever's already saved - lets an
    # admin verify a candidate connection before committing to it.
    return test_ollama_connection(body.base_url, body.embedding_model, body.llm_model)
