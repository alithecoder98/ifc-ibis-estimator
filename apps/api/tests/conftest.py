"""Shared pytest fixtures.

Forces AUTH_DISABLED off for the whole test session, regardless of what's in the
developer's local .env — tests must exercise real auth (test_auth.py especially),
not whatever dev-convenience bypass happens to be set locally. See app/core/deps.py.
"""

import os

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True, scope="session")
def _force_real_auth_for_tests():
    os.environ["AUTH_DISABLED"] = "false"
    get_settings.cache_clear()
    yield
