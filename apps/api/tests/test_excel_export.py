""".xlsx export alongside the existing CSV export (Phase P.3) - a partial
first step toward Phase 7.1, not Phase 6.6 (see app/ai/excel_export.py's
module docstring). Same data, same split-parent exclusion (Phase 6.2) - see
app/ai/excel_export.py and _export_rows() in app/routers/projects.py.
"""

import io
from pathlib import Path

import openpyxl
from fastapi.testclient import TestClient

from app.ai.excel_export import build_export_xlsx
from app.ai.export import FIELDNAMES
from app.core.security import create_access_token
from app.db.models import Classification, Element, IfcFile, Job, Project, Quantity, User
from app.db.session import SessionLocal
from app.main import app
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file
from tests.conftest import cleanup_project_cascade

FIXTURES_DIR = Path(__file__).parent / "fixtures"

client = TestClient(app)


def _read_rows(xlsx_bytes: bytes) -> list[dict]:
    workbook = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    header = next(rows_iter)
    assert list(header) == FIELDNAMES
    return [dict(zip(FIELDNAMES, row, strict=True)) for row in rows_iter]


def test_build_export_xlsx_includes_classification_and_quantities() -> None:
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

    xlsx_bytes = build_export_xlsx([(element, quantities, classification)])
    rows = _read_rows(xlsx_bytes)

    assert len(rows) == 1
    row = rows[0]
    assert row["global_id"] == "ABC123"
    assert row["ifc_class"] == "IfcWall"
    assert row["name"] == "Test Wall"
    assert row["quantities"] == "area_net=15.00m2, length=5.00m"
    assert row["suggested_ibis_code"] == "12.34"
    assert row["status"] == "auto_accepted"


def test_build_export_xlsx_handles_unclassified_element() -> None:
    element = Element(id=1, ifc_file_id=1, global_id="XYZ", ifc_class="IfcColumn")
    xlsx_bytes = build_export_xlsx([(element, [], None)])
    rows = _read_rows(xlsx_bytes)

    assert rows[0]["status"] == "not_classified"
    # Unlike the CSV export (which round-trips "" as ""), openpyxl reads an
    # empty-string cell back as None - a real Excel-format difference, not a
    # bug in build_export_xlsx.
    assert rows[0]["suggested_ibis_code"] is None


def test_build_export_xlsx_empty_rows_produces_header_only() -> None:
    xlsx_bytes = build_export_xlsx([])
    rows = _read_rows(xlsx_bytes)
    assert rows == []


def test_export_excel_endpoint_returns_xlsx_for_processed_project() -> None:
    db = SessionLocal()
    user = User(email="export-6.6@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Excel Export Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        fixture_path = FIXTURES_DIR / "sample.ifc"
        storage_key = "tests/6.6/sample.ifc"
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
        response = client.get(f"/projects/{project_id}/export.xlsx")
        assert response.status_code == 200
        assert response.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment" in response.headers["content-disposition"]
        assert response.headers["content-disposition"].endswith('.xlsx"')

        rows = _read_rows(response.content)
        assert len(rows) == 12  # matches sample.ifc's element count
        wall_row = next(r for r in rows if r["ifc_class"] == "IfcWall")
        assert wall_row["status"] == "needs_review"
    finally:
        client.cookies.clear()
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_export_excel_endpoint_404_for_missing_project() -> None:
    db = SessionLocal()
    user = User(email="export-6.6b@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    try:
        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.get("/projects/999999999/export.xlsx")
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        db = SessionLocal()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()
