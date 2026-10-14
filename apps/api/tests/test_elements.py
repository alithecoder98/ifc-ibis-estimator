"""Phase 4.4: element rows for the Elements tab."""

import uuid

from app.ai.elements import list_element_rows
from app.db.models import Classification, Element, IfcFile, Project, Quantity, User
from app.db.session import SessionLocal
from tests.conftest import cleanup_project_cascade


def _setup_project() -> tuple[int, int, int]:
    db = SessionLocal()
    user = User(
        email=f"elements-4.4-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.flush()
    project = Project(name="Elements Test Project", created_by=user.id)
    db.add(project)
    db.flush()
    ifc_file = IfcFile(
        project_id=project.id,
        filename="x.ifc",
        storage_key="unused",
        size_bytes=1,
        uploaded_by=user.id,
    )
    db.add(ifc_file)
    db.commit()
    project_id, user_id, ifc_file_id = project.id, user.id, ifc_file.id
    db.close()
    return project_id, user_id, ifc_file_id


def test_list_element_rows_empty_project() -> None:
    project_id, user_id, _ = _setup_project()
    db = SessionLocal()
    try:
        assert list_element_rows(db, project_id) == []
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_list_element_rows_includes_full_row_shape() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    try:
        element = Element(
            ifc_file_id=ifc_file_id,
            global_id="G1",
            ifc_class="IfcWall",
            name="Outer wall",
            storey="00 Ground floor",
            materials=[{"material": "Concrete", "thickness_mm": 200.0}],
            group_hash="hash-1",
        )
        db.add(element)
        db.flush()
        db.add(
            Quantity(
                element_id=element.id,
                quantity_type="area_net",
                value=12.5,
                unit="m2",
                source="qto",
            )
        )
        db.add(
            Classification(
                element_id=element.id,
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                confidence=0.9,
                status="auto_accepted",
                source="rule",
            )
        )
        db.commit()

        rows = list_element_rows(db, project_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.global_id == "G1"
        assert row.name == "Outer wall"
        assert row.ifc_class == "IfcWall"
        assert row.storey == "00 Ground floor"
        assert row.material == "Concrete"
        assert row.quantity == 12.5
        assert row.unit == "m2"
        assert row.family == "wall"
        assert row.group_hash == "hash-1"
        assert row.suggested_ibis_code == "21.10"
        assert row.internal_element == "Buitenwand beton"
        assert row.confidence == 0.9
        assert row.status == "auto_accepted"
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_list_element_rows_handles_element_with_no_classification() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    try:
        element = Element(
            ifc_file_id=ifc_file_id,
            global_id="G1",
            ifc_class="IfcSlab",
            group_hash="hash-1",
        )
        db.add(element)
        db.commit()

        rows = list_element_rows(db, project_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.suggested_ibis_code is None
        assert row.status is None
        assert row.material is None
        assert row.quantity is None
        assert row.family == "floor"  # IfcSlab with no predefined_type
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
