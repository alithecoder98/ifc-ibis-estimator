"""Phase P.3: minimal CSV results export.

test_build_export_csv_* exercise app/ai/export.py directly (no DB). test_export_*
drive the real endpoint end to end, through the full upload -> worker -> export chain.
"""

import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.export import build_export_csv
from app.core.security import create_access_token
from app.db.models import Classification, Element, IfcFile, Job, Project, Quantity, User
from app.db.session import SessionLocal
from app.main import app
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file
from tests.conftest import cleanup_project_cascade

FIXTURES_DIR = Path(__file__).parent / "fixtures"

client = TestClient(app)


def test_build_export_csv_includes_classification_and_quantities() -> None:
    element = Element(
        id=1,
        ifc_file_id=1,
        global_id="ABC123",
        ifc_class="IfcWall",
        name="Test Wall",
        storey="Ground Floor",
    )
    quantities = [
        Quantity(quantity_type="length", value=5.0, unit="m", source="qto"),
        Quantity(quantity_type="area_net", value=15.0, unit="m2", source="qto"),
    ]
    classification = Classification(
        ibis_code="12.34",
        internal_element="Buitenwand beton",
        confidence=0.9,
        status="auto_accepted",
        reasoning="test reasoning",
    )

    csv_text = build_export_csv([(element, quantities, classification)])
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert len(rows) == 1
    row = rows[0]
    assert row["global_id"] == "ABC123"
    assert row["ifc_class"] == "IfcWall"
    assert row["name"] == "Test Wall"
    assert row["quantities"] == "area_net=15.00m2, length=5.00m"
    assert row["suggested_ibis_code"] == "12.34"
    assert row["status"] == "auto_accepted"


def test_build_export_csv_handles_unclassified_element() -> None:
    element = Element(id=1, ifc_file_id=1, global_id="XYZ", ifc_class="IfcColumn")
    csv_text = build_export_csv([(element, [], None)])
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert rows[0]["status"] == "not_classified"
    assert rows[0]["suggested_ibis_code"] == ""
    assert rows[0]["quantities"] == ""


def test_build_export_csv_empty_rows_produces_header_only() -> None:
    csv_text = build_export_csv([])
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows == []


def test_export_endpoint_returns_csv_for_processed_project() -> None:
    db = SessionLocal()
    user = User(email="export-p3@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Export Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        fixture_path = FIXTURES_DIR / "sample.ifc"
        storage_key = "tests/P.3/sample.ifc"
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
        job = Job(type="extract", project_id=project.id, ifc_file_id=ifc_file.id)
        db.add(job)
        db.commit()

        process_ifc_file(job.id, ifc_file.id)

        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.get(f"/projects/{project_id}/export")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]

        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert len(rows) == 12  # matches sample.ifc's element count
        wall_row = next(r for r in rows if r["ifc_class"] == "IfcWall")
        assert wall_row["status"] == "needs_review"  # stub jev -> always needs_review
        assert "length=5.00m" in wall_row["quantities"]
    finally:
        client.cookies.clear()
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_export_endpoint_404_for_missing_project() -> None:
    db = SessionLocal()
    user = User(email="export-p3c@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    try:
        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.get("/projects/999999999/export")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    finally:
        client.cookies.clear()
        db = SessionLocal()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()


def test_export_endpoint_empty_csv_for_project_with_no_files() -> None:
    db = SessionLocal()
    user = User(email="export-p3b@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Empty Export Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    db.close()
    try:
        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.get(f"/projects/{project_id}/export")
        assert response.status_code == 200
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert rows == []
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, user_id)
