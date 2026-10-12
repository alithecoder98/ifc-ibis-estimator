"""Redis connection + RQ queue used to enqueue background jobs."""

import redis
from rq import Queue

from app.core.config import get_settings


def get_redis_connection() -> redis.Redis:
    return redis.from_url(get_settings().redis_url)


def get_queue(connection: redis.Redis | None = None) -> Queue:
    return Queue(connection=connection or get_redis_connection())
