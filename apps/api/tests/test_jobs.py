"""Sub-phase 1.4: RQ worker + jobs table.

`test_demo_job_runs_via_fake_queue` uses fakeredis + RQ's synchronous mode (no real
Redis, no separate worker process needed) — the "fake queue" the plan asks for.
`test_get_job_endpoint` and `test_create_demo_job_endpoint` hit the real app/DB (same
pattern as test_health.py — requires docker-compose up).
"""

import fakeredis
from fastapi.testclient import TestClient
from rq import Queue

from app.core.security import create_access_token, hash_password
from app.db.models import Job, User
from app.db.session import SessionLocal
from app.main import app
from app.workers.demo import run_demo_job

client = TestClient(app)


def _create_user(email: str, role: str) -> User:
    db = SessionLocal()
    user = User(email=email, password_hash=hash_password("pw"), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def _login_as(user: User) -> None:
    client.cookies.set(
        "access_token", create_access_token(user_id=user.id, role=user.role)
    )


def _delete_user(user_id: int) -> None:
    db = SessionLocal()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def test_demo_job_runs_via_fake_queue_and_updates_job_row() -> None:
    db = SessionLocal()
    job_id: int | None = None
    try:
        job = Job(type="demo")
        db.add(job)
        db.commit()  # must be committed: run_demo_job opens its own session/connection
        job_id = job.id

        fake_connection = fakeredis.FakeStrictRedis()
        queue = Queue(connection=fake_connection, is_async=False)
        queue.enqueue(run_demo_job, job_id, 3, 0.01)

        db.refresh(job)
        assert job.status == "done"
        assert job.progress == 100
    finally:
        if job_id is not None:
            db.query(Job).filter(Job.id == job_id).delete()
            db.commit()
        db.close()


def test_get_job_endpoint_returns_status_and_progress() -> None:
    user = _create_user("estimator-4.2-jobs@example.com", "estimator")
    _login_as(user)
    db = SessionLocal()
    try:
        job = Job(type="demo", status="running", progress=42)
        db.add(job)
        db.commit()

        response = client.get(f"/jobs/{job.id}")
        assert response.status_code == 200
        assert response.json() == {
            "id": job.id,
            "type": "demo",
            "status": "running",
            "progress": 42,
            "error": None,
        }
    finally:
        client.cookies.clear()
        db.query(Job).filter(Job.id == job.id).delete()
        db.commit()
        db.close()
        _delete_user(user.id)


def test_get_job_endpoint_404_for_missing_job() -> None:
    user = _create_user("estimator-4.2-jobs-b@example.com", "estimator")
    _login_as(user)
    try:
        response = client.get("/jobs/999999999")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    finally:
        client.cookies.clear()
        _delete_user(user.id)


def test_get_job_endpoint_requires_login() -> None:
    response = client.get("/jobs/1")
    assert response.status_code == 401


def test_create_demo_job_endpoint_creates_a_queued_job_row() -> None:
    # Enqueues on the real Redis (no worker process running here to consume it, which
    # is fine — this only checks that the API creates the row and enqueues without
    # error; actually executing it end to end needs `rq worker`, see README).
    db = SessionLocal()
    response = client.post("/jobs/demo")
    try:
        assert response.status_code == 200
        job_id = response.json()["id"]

        job = db.get(Job, job_id)
        assert job is not None
        assert job.type == "demo"
        assert job.status == "queued"
    finally:
        db.query(Job).filter(Job.id == response.json()["id"]).delete()
        db.commit()
        db.close()
