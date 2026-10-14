"""Admin-editable runtime settings (Phase 4.6). Currently just the auto-accept
confidence threshold - see app/core/settings_store.py for why this is DB-backed
rather than the env-sourced app/core/config.py Settings.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.settings_store import get_auto_accept_threshold, set_auto_accept_threshold
from app.db.models import User
from app.db.session import get_db
from app.schemas import ThresholdOut, ThresholdUpdate

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
