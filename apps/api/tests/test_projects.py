"""Sub-phase 2.1: projects CRUD + IFC upload.

Runs against the real app/DB/Garage (same pattern as test_health.py/test_auth.py) -
requires docker-compose up and the Garage bucket/key provisioned (see README).
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.models import IfcFile, Job, Project, User
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _create_user(email: str, role: str) -> User:
    db = SessionLocal()
    user = User(email=email, password_hash=hash_password("pw"), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def _login_as(user: User) -> None:
    token = create_access_token(user_id=user.id, role=user.role)
    client.cookies.set("access_token", token)


def _cleanup_project(project_id: int) -> None:
    db = SessionLocal()
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    if ifc_file_ids:
        db.query(Job).filter(Job.ifc_file_id.in_(ifc_file_ids)).delete(
            synchronize_session=False
        )
        db.query(IfcFile).filter(IfcFile.id.in_(ifc_file_ids)).delete(
            synchronize_session=False
        )
    db.query(Job).filter(Job.project_id == project_id).delete()
    db.query(Project).filter(Project.id == project_id).delete()
    db.commit()
    db.close()


def _delete_user(user_id: int) -> None:
    db = SessionLocal()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def test_create_project_as_estimator_succeeds() -> None:
    user = _create_user("estimator-2.1a@example.com", "estimator")
    _login_as(user)
    try:
        response = client.post("/projects", json={"name": "Test Project A"})
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Test Project A"
        assert body["status"] == "draft"
        assert body["created_by"] == user.id
        _cleanup_project(body["id"])
    finally:
        client.cookies.clear()
        _delete_user(user.id)


def test_create_project_as_viewer_is_403() -> None:
    user = _create_user("viewer-2.1a@example.com", "viewer")
    _login_as(user)
    try:
        response = client.post("/projects", json={"name": "Should not be created"})
        assert response.status_code == 403
    finally:
        client.cookies.clear()
        _delete_user(user.id)


def test_list_and_get_project() -> None:
    user = _create_user("estimator-2.1b@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        create_response = client.post("/projects", json={"name": "Listable Project"})
        project_id = create_response.json()["id"]

        list_response = client.get("/projects")
        assert list_response.status_code == 200
        assert any(p["id"] == project_id for p in list_response.json())

        get_response = client.get(f"/projects/{project_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == "Listable Project"
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_get_project_404_for_missing() -> None:
    user = _create_user("estimator-2.1c@example.com", "estimator")
    _login_as(user)
    try:
        response = client.get("/projects/999999999")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    finally:
        client.cookies.clear()
        _delete_user(user.id)


def test_upload_valid_ifc_file_creates_record_and_job() -> None:
    user = _create_user("estimator-2.1d@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post("/projects", json={"name": "Upload Project"}).json()[
            "id"
        ]

        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            response = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["project_id"] == project_id
        assert body["filename"] == "sample.ifc"
        assert body["ifc_schema"] == "IFC4"
        assert body["size_bytes"] > 0
        assert body["status"] == "uploaded"

        db = SessionLocal()
        jobs = db.query(Job).filter(Job.ifc_file_id == body["id"]).all()
        assert len(jobs) == 1
        assert jobs[0].type == "extract"
        db.close()
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_upload_corrupt_file_returns_400() -> None:
    user = _create_user("estimator-2.1e@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Corrupt Upload Project"}
        ).json()["id"]

        with open(FIXTURES_DIR / "corrupt.ifc", "rb") as fh:
            response = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("corrupt.ifc", fh, "application/octet-stream")},
            )

        assert response.status_code == 400
        assert "valid IFC" in response.json()["error"]["message"]

        db = SessionLocal()
        assert db.query(IfcFile).filter(IfcFile.project_id == project_id).count() == 0
        db.close()
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_upload_wrong_extension_returns_400() -> None:
    user = _create_user("estimator-2.1f@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Wrong Extension Project"}
        ).json()["id"]

        response = client.post(
            f"/projects/{project_id}/files",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_upload_to_nonexistent_project_404() -> None:
    user = _create_user("estimator-2.1g@example.com", "estimator")
    _login_as(user)
    try:
        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            response = client.post(
                "/projects/999999999/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            )
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        _delete_user(user.id)
