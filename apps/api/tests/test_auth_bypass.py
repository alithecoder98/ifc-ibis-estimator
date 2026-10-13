"""Tests the AUTH_DISABLED dev-mode bypass (app/core/deps.py).

Toggles it on only within this test, restoring real auth immediately after -
conftest's session fixture otherwise keeps it off for every other test.
"""

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.deps import DEV_BYPASS_EMAIL
from app.db.models import User
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def test_me_works_without_cookie_when_auth_disabled() -> None:
    os.environ["AUTH_DISABLED"] = "true"
    get_settings.cache_clear()
    try:
        client.cookies.clear()
        response = client.get("/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == DEV_BYPASS_EMAIL
        assert body["role"] == "admin"
    finally:
        os.environ["AUTH_DISABLED"] = "false"
        get_settings.cache_clear()
        db = SessionLocal()
        db.query(User).filter(User.email == DEV_BYPASS_EMAIL).delete()
        db.commit()
        db.close()
