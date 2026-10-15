"""Tests the AUTH_DISABLED dev-mode bypass (app/core/deps.py).

Toggles it on only within this test, restoring real auth immediately after -
conftest's session fixture otherwise keeps it off for every other test.
"""

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.deps import DEV_BYPASS_EMAIL
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
        # Deliberately not deleting the dev-bypass user here (this test used
        # to): app/core/deps.py's _get_or_create_dev_user() is a shared,
        # idempotent identity, not data this test owns - deleting it broke the
        # very first time someone actually used AUTH_DISABLED for real dev
        # work in the browser (real projects FK onto that user, so the delete
        # failed with a real ForeignKeyViolation, not a hypothetical one).
        # This test's own assertions above already prove the bypass works
        # correctly whether the row pre-existed or not - nothing here needs
        # the row gone afterward.
