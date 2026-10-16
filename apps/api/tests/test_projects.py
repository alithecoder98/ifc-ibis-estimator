"""Sub-phase 2.1: projects CRUD + IFC upload.

Runs against the real app/DB/Garage (same pattern as test_health.py/test_auth.py) -
requires docker-compose up and the Garage bucket/key provisioned (see README).
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.models import Element, IfcFile, Job, User
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import cleanup_project_cascade

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
    """This file had its own copy of this logic for a long time, from back when
    its tests only ever created Job/IfcFile/Project rows - never Element, so the
    gap never surfaced. 4.5's element-detail tests are the first in this file to
    create an Element directly, hit exactly the FK-violation class CLAUDE.md
    warns about, and found a second, forgotten copy of the exact duplication the
    shared cleanup_project_cascade() was built in Phase P to avoid. Delegating
    here instead of maintaining a second copy of the fix.
    """
    cleanup_project_cascade(project_id)


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


def test_update_project_classification_engine_as_admin() -> None:
    admin = _create_user("admin-3.5a@example.com", "admin")
    _login_as(admin)
    project_id = None
    try:
        create_response = client.post("/projects", json={"name": "Engine Project"})
        project_id = create_response.json()["id"]
        assert create_response.json()["classification_engine"] == "jev"

        patch_response = client.patch(
            f"/projects/{project_id}", json={"classification_engine": "both"}
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["classification_engine"] == "both"

        get_response = client.get(f"/projects/{project_id}")
        assert get_response.json()["classification_engine"] == "both"
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(admin.id)


def test_update_project_allowed_for_estimator_too() -> None:
    """Phase 4.1: renaming and changing classification_engine share one endpoint,
    and renaming is a normal estimator action - not admin-only like 3.5 first
    scoped this endpoint. See app/routers/projects.py's update_project() docstring.
    """
    estimator = _create_user("estimator-3.5b@example.com", "estimator")
    _login_as(estimator)
    project_id = None
    try:
        create_response = client.post("/projects", json={"name": "Engine Project B"})
        project_id = create_response.json()["id"]

        patch_response = client.patch(
            f"/projects/{project_id}",
            json={"name": "Renamed by estimator", "classification_engine": "llm"},
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["name"] == "Renamed by estimator"
        assert patch_response.json()["classification_engine"] == "llm"
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(estimator.id)


def test_update_project_requires_admin_or_estimator() -> None:
    admin = _create_user("admin-4.1a@example.com", "admin")
    _login_as(admin)
    project_id = client.post("/projects", json={"name": "Engine Project D"}).json()[
        "id"
    ]
    client.cookies.clear()

    viewer = _create_user("viewer-4.1a@example.com", "viewer")
    _login_as(viewer)
    try:
        patch_response = client.patch(
            f"/projects/{project_id}", json={"name": "Should not work"}
        )
        assert patch_response.status_code == 403
    finally:
        client.cookies.clear()
        _delete_user(viewer.id)
        _cleanup_project(project_id)
        _delete_user(admin.id)


def test_update_project_rejects_invalid_engine_value() -> None:
    admin = _create_user("admin-3.5c@example.com", "admin")
    _login_as(admin)
    project_id = None
    try:
        create_response = client.post("/projects", json={"name": "Engine Project C"})
        project_id = create_response.json()["id"]

        patch_response = client.patch(
            f"/projects/{project_id}", json={"classification_engine": "not-a-engine"}
        )
        assert patch_response.status_code == 422
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(admin.id)


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
        # Phase 4.2: the frontend needs this to know which job to poll.
        assert body["job_id"] == jobs[0].id
        db.close()
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_list_files_includes_latest_job_id() -> None:
    user = _create_user("estimator-4.2a@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Job Id List Project"}
        ).json()["id"]

        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            upload_response = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            )
        expected_job_id = upload_response.json()["job_id"]
        assert expected_job_id is not None

        list_response = client.get(f"/projects/{project_id}/files")
        assert list_response.status_code == 200
        assert list_response.json()[0]["job_id"] == expected_job_id
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


def test_list_files_returns_uploaded_files_newest_first() -> None:
    user = _create_user("estimator-4.1b@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "List Files Project"}
        ).json()["id"]

        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            first_id = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("first.ifc", fh, "application/octet-stream")},
            ).json()["id"]
        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            second_id = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("second.ifc", fh, "application/octet-stream")},
            ).json()["id"]

        response = client.get(f"/projects/{project_id}/files")
        assert response.status_code == 200
        body = response.json()
        assert [f["id"] for f in body] == [second_id, first_id]  # newest first
        assert all(f["project_id"] == project_id for f in body)
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_list_files_404_for_nonexistent_project() -> None:
    user = _create_user("estimator-4.1c@example.com", "estimator")
    _login_as(user)
    try:
        response = client.get("/projects/999999999/files")
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        _delete_user(user.id)


def test_list_elements_returns_empty_list_for_project_with_no_elements() -> None:
    user = _create_user("estimator-4.4a@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Elements Endpoint Project"}
        ).json()["id"]
        response = client.get(f"/projects/{project_id}/elements")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_list_elements_404_for_nonexistent_project() -> None:
    user = _create_user("estimator-4.4b@example.com", "estimator")
    _login_as(user)
    try:
        response = client.get("/projects/999999999/elements")
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        _delete_user(user.id)


def test_get_element_endpoint_returns_full_detail() -> None:
    """get_element always calls the real embedder (see app/ai/element_detail.py's
    module docstring - no "jev-only, stay offline" path here), so this
    monkeypatches app.routers.projects.get_embedder the same way test_classify.py
    monkeypatches classify.py's, to keep CI offline.
    """
    user = _create_user("estimator-4.5a@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Element Detail Endpoint Project"}
        ).json()["id"]

        db = SessionLocal()
        ifc_file = IfcFile(
            project_id=project_id,
            filename="x.ifc",
            storage_key="unused",
            size_bytes=1,
            uploaded_by=user.id,
        )
        db.add(ifc_file)
        db.flush()
        element = Element(
            ifc_file_id=ifc_file.id,
            global_id="G1",
            ifc_class="IfcWall",
            profile_text="concrete exterior wall",
        )
        db.add(element)
        db.commit()
        element_id = element.id
        db.close()

        import app.routers.projects as projects_module
        from app.ai.embedder import FakeEmbedder
        from app.core.constants import EMBEDDING_DIM

        original_get_embedder = projects_module.get_embedder
        projects_module.get_embedder = lambda db: FakeEmbedder(EMBEDDING_DIM)
        try:
            response = client.get(f"/projects/{project_id}/elements/{element_id}")
        finally:
            projects_module.get_embedder = original_get_embedder

        assert response.status_code == 200
        body = response.json()
        assert body["global_id"] == "G1"
        assert body["candidates"] == []  # no code_list rows seeded
        assert body["reviews"] == []
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_get_element_endpoint_404_for_element_in_wrong_project() -> None:
    user = _create_user("estimator-4.5b@example.com", "estimator")
    _login_as(user)
    project_id, other_project_id = None, None
    try:
        project_id = client.post(
            "/projects", json={"name": "Element Detail 404 Project"}
        ).json()["id"]
        other_project_id = client.post(
            "/projects", json={"name": "Element Detail 404 Other Project"}
        ).json()["id"]

        db = SessionLocal()
        ifc_file = IfcFile(
            project_id=project_id,
            filename="x.ifc",
            storage_key="unused",
            size_bytes=1,
            uploaded_by=user.id,
        )
        db.add(ifc_file)
        db.flush()
        element = Element(ifc_file_id=ifc_file.id, global_id="G1", ifc_class="IfcWall")
        db.add(element)
        db.commit()
        element_id = element.id
        db.close()

        response = client.get(f"/projects/{other_project_id}/elements/{element_id}")
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        if other_project_id is not None:
            _cleanup_project(other_project_id)
        _delete_user(user.id)


def test_classify_endpoint_requires_extracted_file() -> None:
    """Phase 3.7: re-running classification before extraction has even finished
    makes no sense - there are no elements yet.
    """
    user = _create_user("estimator-3.7a@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Classify 400 Project"}
        ).json()["id"]
        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            file_id = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            ).json()["id"]

        response = client.post(f"/projects/{project_id}/files/{file_id}/classify")
        assert response.status_code == 400
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_classify_endpoint_404_for_file_in_wrong_project() -> None:
    user = _create_user("estimator-3.7b@example.com", "estimator")
    _login_as(user)
    project_id, other_project_id = None, None
    try:
        project_id = client.post(
            "/projects", json={"name": "Classify 404 Project"}
        ).json()["id"]
        other_project_id = client.post(
            "/projects", json={"name": "Classify 404 Other Project"}
        ).json()["id"]
        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            file_id = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            ).json()["id"]

        response = client.post(f"/projects/{other_project_id}/files/{file_id}/classify")
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        if other_project_id is not None:
            _cleanup_project(other_project_id)
        _delete_user(user.id)


def test_classify_endpoint_requires_estimator_or_admin() -> None:
    user = _create_user("estimator-3.7c@example.com", "estimator")
    _login_as(user)
    project_id = client.post("/projects", json={"name": "Classify 403 Project"}).json()[
        "id"
    ]
    with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
        file_id = client.post(
            f"/projects/{project_id}/files",
            files={"file": ("sample.ifc", fh, "application/octet-stream")},
        ).json()["id"]
    client.cookies.clear()

    viewer = _create_user("viewer-3.7c@example.com", "viewer")
    _login_as(viewer)
    try:
        response = client.post(f"/projects/{project_id}/files/{file_id}/classify")
        assert response.status_code == 403
    finally:
        client.cookies.clear()
        _delete_user(viewer.id)
        _cleanup_project(project_id)
        _delete_user(user.id)


def test_classify_endpoint_enqueues_job_for_extracted_file() -> None:
    user = _create_user("estimator-3.7d@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Classify 202 Project"}
        ).json()["id"]
        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            file_id = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            ).json()["id"]

        db = SessionLocal()
        ifc_file = db.get(IfcFile, file_id)
        ifc_file.status = "extracted"
        db.commit()
        db.close()

        response = client.post(f"/projects/{project_id}/files/{file_id}/classify")
        assert response.status_code == 202
        job_id = response.json()["id"]

        db = SessionLocal()
        job = db.get(Job, job_id)
        assert job.type == "classify"
        assert job.ifc_file_id == file_id
        db.close()
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_reprocess_endpoint_rejects_already_extracted_file() -> None:
    """A real file can be stuck "uploaded" forever if its original job is lost
    from the queue (e.g. a Redis restart) - /reprocess exists to recover from
    that. It must stay restricted to uploaded/failed: unlike /classify's
    append-only re-evaluation, re-running extraction on an already-"extracted"
    file would insert a second, duplicate set of Element rows.
    """
    user = _create_user("estimator-reprocess-a@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Reprocess 400 Project"}
        ).json()["id"]
        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            file_id = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            ).json()["id"]

        db = SessionLocal()
        ifc_file = db.get(IfcFile, file_id)
        ifc_file.status = "extracted"
        db.commit()
        db.close()

        response = client.post(f"/projects/{project_id}/files/{file_id}/reprocess")
        assert response.status_code == 400
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)


def test_reprocess_endpoint_404_for_file_in_wrong_project() -> None:
    user = _create_user("estimator-reprocess-b@example.com", "estimator")
    _login_as(user)
    project_id, other_project_id = None, None
    try:
        project_id = client.post(
            "/projects", json={"name": "Reprocess 404 Project"}
        ).json()["id"]
        other_project_id = client.post(
            "/projects", json={"name": "Reprocess 404 Other Project"}
        ).json()["id"]
        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            file_id = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            ).json()["id"]

        response = client.post(
            f"/projects/{other_project_id}/files/{file_id}/reprocess"
        )
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        if other_project_id is not None:
            _cleanup_project(other_project_id)
        _delete_user(user.id)


def test_reprocess_endpoint_requires_estimator_or_admin() -> None:
    user = _create_user("estimator-reprocess-c@example.com", "estimator")
    _login_as(user)
    project_id = client.post(
        "/projects", json={"name": "Reprocess 403 Project"}
    ).json()["id"]
    with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
        file_id = client.post(
            f"/projects/{project_id}/files",
            files={"file": ("sample.ifc", fh, "application/octet-stream")},
        ).json()["id"]
    client.cookies.clear()

    viewer = _create_user("viewer-reprocess-c@example.com", "viewer")
    _login_as(viewer)
    try:
        response = client.post(f"/projects/{project_id}/files/{file_id}/reprocess")
        assert response.status_code == 403
    finally:
        client.cookies.clear()
        _delete_user(viewer.id)
        _cleanup_project(project_id)
        _delete_user(user.id)


def test_reprocess_endpoint_enqueues_job_for_uploaded_file() -> None:
    user = _create_user("estimator-reprocess-d@example.com", "estimator")
    _login_as(user)
    project_id = None
    try:
        project_id = client.post(
            "/projects", json={"name": "Reprocess 202 Project"}
        ).json()["id"]
        with open(FIXTURES_DIR / "sample.ifc", "rb") as fh:
            file_id = client.post(
                f"/projects/{project_id}/files",
                files={"file": ("sample.ifc", fh, "application/octet-stream")},
            ).json()["id"]

        # The file's own original upload-time job is irrelevant here - this
        # proves /reprocess enqueues a genuinely new one on top of it, which
        # is exactly what recovers a file whose first job was lost.
        response = client.post(f"/projects/{project_id}/files/{file_id}/reprocess")
        assert response.status_code == 202
        job_id = response.json()["id"]

        db = SessionLocal()
        job = db.get(Job, job_id)
        assert job.type == "extract"
        assert job.ifc_file_id == file_id
        db.close()
    finally:
        client.cookies.clear()
        if project_id is not None:
            _cleanup_project(project_id)
        _delete_user(user.id)
