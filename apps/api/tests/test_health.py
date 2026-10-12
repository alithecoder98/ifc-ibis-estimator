"""Integration test for GET /health — requires the local docker-compose services
(postgres, redis) to be running. See README.md "Local setup"."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_database_and_redis() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"status", "database", "redis"}
    # With docker-compose up, both dependencies should be reachable.
    assert body["database"] == "ok"
    assert body["redis"] == "ok"
    assert body["status"] == "ok"
