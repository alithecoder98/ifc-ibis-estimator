"""DB-backed overrides for a handful of runtime settings (Phase 4.6's admin area).

Distinct from app/core/config.py's Settings: those are env-var/.env-sourced and
fixed for a process's lifetime (pydantic-settings, lru_cached). An admin changing
the auto-accept threshold needs it to take effect on the very next classification
run, not after a restart - hence a tiny DB-backed override, checked first, falling
back to the env-sourced default when no row exists yet (e.g. a fresh database).
"""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AppSetting
from app.db.models.settings import AUTO_ACCEPT_THRESHOLD_KEY


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
