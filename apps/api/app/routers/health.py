"""GET /health — checks the database and Redis, used by orchestration/monitoring."""

import logging

import redis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_database(db: Session) -> str:
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.exception("Database health check failed")
        return "error"


def _check_redis() -> str:
    settings = get_settings()
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        return "ok"
    except Exception:
        logger.exception("Redis health check failed")
        return "error"


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    database_status = _check_database(db)
    redis_status = _check_redis()
    overall = "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
    return {"status": overall, "database": database_status, "redis": redis_status}
