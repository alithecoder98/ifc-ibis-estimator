"""Phase 6.2: splitting a composite element (e.g. a multi-layer wall) into one real
Element row per material layer. See app/ai/composite_split.py's module docstring.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.composite_split import AlreadySplitError, NotCompositeError, split_element
from app.ai.elements import list_element_rows
from app.ai.summary import compute_summary
from app.core.security import create_access_token
from app.db.models import Element, IfcFile, Project, Quantity, User
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import cleanup_project_cascade

client = TestClient(app)


def _setup_project() -> tuple[int, int, int]:
    db = SessionLocal()
    user = User(
        email=f"split-6.2-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.flush()
    project = Project(name="Split Test Project", created_by=user.id)
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


def _composite_wall(ifc_file_id: int) -> int:
    db = SessionLocal()
    element = Element(
        ifc_file_id=ifc_file_id,
        global_id=f"G{uuid.uuid4().hex[:8]}",
        ifc_class="IfcWall",
        name="Composite Wall",
        storey="Ground Floor",
        materials=[
            {"material": "Brick", "thickness_mm": 100.0},
            {"material": "Insulation", "thickness_mm": 50.0},
            {"material": "Concrete", "thickness_mm": 150.0},
        ],
        group_hash=uuid.uuid4().hex,
    )
    db.add(element)
    db.flush()
    db.add(
        Quantity(
            element_id=element.id,
            quantity_type="area_net",
            value=30.0,
            unit="m2",
            source="qto",
        )
    )
    db.commit()
    element_id = element.id
    db.close()
    return element_id


def test_split_element_creates_one_child_per_material_layer() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    element_id = _composite_wall(ifc_file_id)
    db = SessionLocal()
    try:
        children = split_element(db, element_id)
        db.commit()
        assert len(children) == 3
        names = {c.name for c in children}
        assert names == {
            "Composite Wall - Brick",
            "Composite Wall - Insulation",
            "Composite Wall - Concrete",
        }
        for child in children:
            assert child.parent_element_id == element_id
            assert child.ifc_class == "IfcWall"
            assert child.storey == "Ground Floor"
            assert len(child.materials) == 1

        # thickness-proportional split: 100/50/150mm of a 30 m2 wall -> 10/5/15 m2
        quantities_by_child = {
            c.id: db.query(Quantity).filter(Quantity.element_id == c.id).one()
            for c in children
        }
        by_material = {c.materials[0]["material"]: c for c in children}
        assert quantities_by_child[by_material["Brick"].id].value == pytest.approx(10.0)
        assert quantities_by_child[by_material["Insulation"].id].value == pytest.approx(
            5.0
        )
        assert quantities_by_child[by_material["Concrete"].id].value == pytest.approx(
            15.0
        )
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_split_element_rejects_single_material_element() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = Element(
        ifc_file_id=ifc_file_id,
        global_id="G1",
        ifc_class="IfcWall",
        materials=[{"material": "Concrete", "thickness_mm": 200.0}],
        group_hash="hash-1",
    )
    db.add(element)
    db.commit()
    element_id = element.id
    db.close()

    db = SessionLocal()
    try:
        with pytest.raises(NotCompositeError):
            split_element(db, element_id)
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_split_element_rejects_resplitting() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    element_id = _composite_wall(ifc_file_id)
    db = SessionLocal()
    try:
        split_element(db, element_id)
        db.commit()
        with pytest.raises(AlreadySplitError):
            split_element(db, element_id)
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_elements_list_marks_split_parent_and_includes_children() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    element_id = _composite_wall(ifc_file_id)
    db = SessionLocal()
    try:
        split_element(db, element_id)
        db.commit()

        rows = list_element_rows(db, project_id)
        # 1 parent + 3 children
        assert len(rows) == 4
        parent_row = next(r for r in rows if r.id == element_id)
        assert parent_row.is_split_parent is True
        child_rows = [r for r in rows if r.id != element_id]
        assert len(child_rows) == 3
        assert all(not r.is_split_parent for r in child_rows)
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_summary_excludes_split_parent_quantity_from_double_counting() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    element_id = _composite_wall(ifc_file_id)
    db = SessionLocal()
    try:
        before = compute_summary(db, project_id)
        assert before.total_elements == 1

        split_element(db, element_id)
        db.commit()

        after = compute_summary(db, project_id)
        # parent excluded, 3 children included -> 3, not 4
        assert after.total_elements == 3
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def _estimator_client() -> int:
    db = SessionLocal()
    user = User(
        email=f"split-6.2-client-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    client.cookies.set(
        "access_token", create_access_token(user_id=user_id, role="estimator")
    )
    return user_id


def test_split_endpoint_success() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    element_id = _composite_wall(ifc_file_id)
    reviewer_id = _estimator_client()
    try:
        response = client.post(f"/projects/{project_id}/elements/{element_id}/split")
        assert response.status_code == 201
        body = response.json()
        assert len(body["child_element_ids"]) == 3
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_split_endpoint_rejects_single_material_element() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = Element(
        ifc_file_id=ifc_file_id,
        global_id="G1",
        ifc_class="IfcWall",
        materials=[{"material": "Concrete", "thickness_mm": 200.0}],
        group_hash="hash-1",
    )
    db.add(element)
    db.commit()
    element_id = element.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        response = client.post(f"/projects/{project_id}/elements/{element_id}/split")
        assert response.status_code == 400
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_split_endpoint_rejects_resplitting() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    element_id = _composite_wall(ifc_file_id)
    reviewer_id = _estimator_client()
    try:
        first = client.post(f"/projects/{project_id}/elements/{element_id}/split")
        assert first.status_code == 201
        second = client.post(f"/projects/{project_id}/elements/{element_id}/split")
        assert second.status_code == 409
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_split_endpoint_404_for_other_projects_element() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    other_project_id, other_owner_id, other_ifc_file_id = _setup_project()
    element_id = _composite_wall(other_ifc_file_id)
    reviewer_id = _estimator_client()
    try:
        response = client.post(f"/projects/{project_id}/elements/{element_id}/split")
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        cleanup_project_cascade(other_project_id, other_owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()
