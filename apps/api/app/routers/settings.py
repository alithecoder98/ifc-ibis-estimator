"""Admin-editable runtime settings (Phase 4.6: auto-accept threshold; this session:
LLM Connectivity). See app/core/settings_store.py for why these are DB-backed rather
than the env-sourced app/core/config.py Settings - an admin changing either needs it
to take effect on the next classification run, not after a restart.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.connectivity_check import (
    test_ollama_connection,
    test_openai_compatible_connection,
)
from app.core.deps import require_role
from app.core.settings_store import (
    LLMConnection,
    get_auto_accept_threshold,
    get_llm_connection,
    set_auto_accept_threshold,
    set_llm_connection,
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
    connection = get_llm_connection(db)
    return LLMConnectivityOut(
        provider=connection.provider,
        base_url=connection.base_url,
        embedding_model=connection.embedding_model,
        llm_model=connection.llm_model,
        has_api_key=bool(connection.api_key),
    )


@router.patch("/llm", response_model=LLMConnectivityOut)
def update_llm_connectivity(
    body: LLMConnectivityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> LLMConnectivityOut:
    connection = set_llm_connection(
        db,
        LLMConnection(
            provider=body.provider,
            base_url=body.base_url,
            embedding_model=body.embedding_model,
            llm_model=body.llm_model,
            api_key=body.api_key or "",
        ),
        update_api_key=body.api_key is not None,
    )
    return LLMConnectivityOut(
        provider=connection.provider,
        base_url=connection.base_url,
        embedding_model=connection.embedding_model,
        llm_model=connection.llm_model,
        has_api_key=bool(connection.api_key),
    )


@router.post("/llm/test", response_model=LLMConnectivityTestOut)
def test_llm_connectivity(
    body: LLMConnectivityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> LLMConnectivityTestOut:
    # Tests the submitted values directly, not whatever's already saved - lets an
    # admin verify a candidate connection before committing to it. api_key=None
    # (field left blank, e.g. just testing a model-name change) falls back to
    # whatever's already saved, same "leave it alone" convention as the save
    # endpoint, rather than forcing a re-paste of the key just to re-test.
    if body.provider == "openai_compatible":
        api_key = body.api_key
        if api_key is None:
            api_key = get_llm_connection(db).api_key
        return test_openai_compatible_connection(
            body.base_url, body.embedding_model, body.llm_model, api_key
        )
    return test_ollama_connection(body.base_url, body.embedding_model, body.llm_model)
