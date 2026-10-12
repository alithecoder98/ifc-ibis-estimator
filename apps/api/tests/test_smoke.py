"""Smoke test for sub-phase 1.1 — confirms the app imports and boots."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_ok() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"service": "ifc-ibis-api", "status": "ok"}
