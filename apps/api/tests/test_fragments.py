"""Phase 2.6: converts IFC to That Open fragments for the (not-yet-built) 3D viewer.

test_convert_to_fragments_* exercise app/ifc/fragments.py directly (real subprocess
call to node_fragments/convert.mjs, no mocking - there's no documented Python-side
contract to mock, same reasoning as every other IFC-touching module in this repo).
test_get_fragments_model_* drive the real endpoint end to end.
"""

from pathlib import Path

import ifcopenshell
import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.models import IfcFile, Job, Project, User
from app.db.session import SessionLocal
from app.ifc.fragments import convert_to_fragments
from app.main import app
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file
from tests.conftest import cleanup_project_cascade

FIXTURES_DIR = Path(__file__).parent / "fixtures"

client = TestClient(app)


def test_convert_to_fragments_produces_bytes_and_global_id_map() -> None:
    fragments_bytes, id_map = convert_to_fragments(FIXTURES_DIR / "sample.ifc")

    assert len(fragments_bytes) > 0
    assert len(id_map) > 0
    assert all(isinstance(v, int) for v in id_map.values())
    # sample.ifc's wall GlobalId (see test_extraction.py) must resolve to a real
    # fragment local ID, not just some IFC entity that happens to have a GlobalId.
    ifc_file = ifcopenshell.open(str(FIXTURES_DIR / "sample.ifc"))
    wall = ifc_file.by_type("IfcWall")[0]
    assert wall.GlobalId in id_map


def test_convert_to_fragments_raises_with_node_stderr_on_bad_input() -> None:
    with pytest.raises(RuntimeError, match="fragments conversion failed"):
        convert_to_fragments(Path("does-not-exist.ifc"))


def test_get_fragments_model_returns_binary_after_processing() -> None:
    db = SessionLocal()
    user = User(email="fragments-2.6@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Fragments Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        fixture_path = FIXTURES_DIR / "sample.ifc"
        storage_key = "tests/2.6/sample.ifc"
        with open(fixture_path, "rb") as fh:
            upload_fileobj(fh, storage_key)

        ifc_file = IfcFile(
            project_id=project.id,
            filename="sample.ifc",
            storage_key=storage_key,
            ifc_schema="IFC4",
            size_bytes=fixture_path.stat().st_size,
            uploaded_by=user.id,
            status="uploaded",
        )
        db.add(ifc_file)
        db.flush()
        file_id = ifc_file.id
        job = Job(type="extract", project_id=project.id, ifc_file_id=ifc_file.id)
        db.add(job)
        db.commit()

        process_ifc_file(job.id, ifc_file.id)

        db.refresh(ifc_file)
        assert ifc_file.fragments_storage_key is not None
        assert ifc_file.fragment_id_map  # at least one entry

        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.get(f"/projects/{project_id}/files/{file_id}/model")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"
        assert len(response.content) > 0
    finally:
        client.cookies.clear()
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_get_fragments_model_404_before_processing() -> None:
    db = SessionLocal()
    user = User(email="fragments-2.6b@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Fragments Not Ready Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        ifc_file = IfcFile(
            project_id=project.id,
            filename="sample.ifc",
            storage_key="unused",
            size_bytes=1,
            uploaded_by=user.id,
            status="uploaded",
        )
        db.add(ifc_file)
        db.commit()
        db.refresh(ifc_file)
        file_id = ifc_file.id

        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.get(f"/projects/{project_id}/files/{file_id}/model")
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_get_fragments_model_404_for_file_in_different_project() -> None:
    db = SessionLocal()
    user = User(email="fragments-2.6c@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project_a = Project(name="Fragments Project A", created_by=user.id)
    project_b = Project(name="Fragments Project B", created_by=user.id)
    db.add_all([project_a, project_b])
    db.commit()
    db.refresh(user)
    db.refresh(project_a)
    db.refresh(project_b)
    user_id, project_a_id, project_b_id = user.id, project_a.id, project_b.id
    try:
        ifc_file = IfcFile(
            project_id=project_a_id,
            filename="sample.ifc",
            storage_key="unused",
            size_bytes=1,
            uploaded_by=user_id,
            status="uploaded",
        )
        db.add(ifc_file)
        db.commit()
        db.refresh(ifc_file)
        file_id = ifc_file.id

        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.get(f"/projects/{project_b_id}/files/{file_id}/model")
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        db.close()
        cleanup_project_cascade(project_a_id, None)
        cleanup_project_cascade(project_b_id, user_id)
