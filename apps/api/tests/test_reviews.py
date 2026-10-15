"""Phase 6.1: approve/correct/undo. Every action writes a fresh Classification row
(never mutates the old one) plus a Review row - see app/ai/reviews.py's module
docstring for why no new Classification.status value was needed.
"""

import uuid

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.models import (
    Classification,
    CodeList,
    Element,
    IfcFile,
    Project,
    Review,
    User,
)
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import cleanup_project_cascade

client = TestClient(app)


def _setup_project() -> tuple[int, int, int]:
    db = SessionLocal()
    user = User(
        email=f"reviews-6.1-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.flush()
    project = Project(name="Reviews Test Project", created_by=user.id)
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


def _element(ifc_file_id: int, **overrides) -> Element:
    defaults = dict(
        ifc_file_id=ifc_file_id,
        global_id=f"G{uuid.uuid4().hex[:8]}",
        ifc_class="IfcWall",
        group_hash=uuid.uuid4().hex,
    )
    defaults.update(overrides)
    return Element(**defaults)


def _classification(element_id: int, **overrides) -> Classification:
    defaults = dict(
        element_id=element_id,
        ibis_code="21.10",
        internal_element="Buitenwand beton",
        status="needs_review",
        source="llm",
        confidence=0.5,
    )
    defaults.update(overrides)
    return Classification(**defaults)


def _estimator_client(role: str = "estimator"):
    db = SessionLocal()
    user = User(
        email=f"reviews-6.1-client-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    client.cookies.set("access_token", create_access_token(user_id=user_id, role=role))
    return user_id


def test_approve_element_writes_fresh_classification_and_review() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.flush()
    classification = _classification(element.id)
    db.add(classification)
    db.commit()
    element_id, old_classification_id = element.id, classification.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        response = client.post(
            f"/projects/{project_id}/elements/{element_id}/reviews",
            json={"action": "approve"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["classification"]["ibis_code"] == "21.10"
        assert body["classification"]["status"] == "auto_accepted"
        assert body["classification"]["source"] == "review"
        assert body["review"]["action"] == "approve"

        db = SessionLocal()
        classifications = (
            db.query(Classification)
            .filter(Classification.element_id == element_id)
            .all()
        )
        assert len(classifications) == 2  # old row untouched, new row added
        assert any(c.id == old_classification_id for c in classifications)
        review = db.query(Review).filter(Review.id == body["review"]["id"]).one()
        assert review.before["ibis_code"] == "21.10"
        assert review.before["status"] == "needs_review"
        assert review.after["status"] == "auto_accepted"
        db.close()
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_approve_element_without_code_fails() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.flush()
    db.add(_classification(element.id, ibis_code=None, internal_element=None))
    db.commit()
    element_id = element.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        response = client.post(
            f"/projects/{project_id}/elements/{element_id}/reviews",
            json={"action": "approve"},
        )
        assert response.status_code == 400
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_correct_element_uses_code_list_internal_element() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.flush()
    db.add(_classification(element.id))
    code = CodeList(
        ibis_code="41.10",
        internal_element="Dakconstructie hout",
        description="timber roof",
        family="roof",
    )
    db.add(code)
    db.commit()
    element_id, code_id = element.id, code.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        response = client.post(
            f"/projects/{project_id}/elements/{element_id}/reviews",
            json={"action": "correct", "ibis_code": "41.10", "comment": "wrong family"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["classification"]["ibis_code"] == "41.10"
        assert body["classification"]["internal_element"] == "Dakconstructie hout"
        assert body["review"]["comment"] == "wrong family"
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(CodeList).filter(CodeList.id == code_id).delete()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_correct_element_unknown_code_fails() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.flush()
    db.add(_classification(element.id))
    db.commit()
    element_id = element.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        response = client.post(
            f"/projects/{project_id}/elements/{element_id}/reviews",
            json={"action": "correct", "ibis_code": "99.99"},
        )
        assert response.status_code == 400
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_review_group_bulk_applies_to_every_element_sharing_group_hash() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    shared_hash = uuid.uuid4().hex
    el_a = _element(ifc_file_id, group_hash=shared_hash)
    el_b = _element(ifc_file_id, group_hash=shared_hash)
    el_other = _element(ifc_file_id)  # different group - must stay untouched
    db.add_all([el_a, el_b, el_other])
    db.flush()
    db.add(_classification(el_a.id))
    db.add(_classification(el_b.id))
    db.add(_classification(el_other.id))
    db.commit()
    el_a_id, el_b_id, el_other_id = el_a.id, el_b.id, el_other.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        response = client.post(
            f"/projects/{project_id}/groups/{shared_hash}/reviews",
            json={"action": "approve"},
        )
        assert response.status_code == 201
        body = response.json()
        assert len(body) == 2

        db = SessionLocal()
        assert (
            db.query(Classification)
            .filter(Classification.element_id == el_a_id)
            .count()
            == 2
        )
        assert (
            db.query(Classification)
            .filter(Classification.element_id == el_b_id)
            .count()
            == 2
        )
        assert (
            db.query(Classification)
            .filter(Classification.element_id == el_other_id)
            .count()
            == 1
        )
        db.close()
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_undo_review_restores_before_snapshot() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.flush()
    db.add(_classification(element.id, ibis_code="21.10"))
    code = CodeList(
        ibis_code="41.10",
        internal_element="Dakconstructie hout",
        description="timber roof",
        family="roof",
    )
    db.add(code)
    db.commit()
    element_id, code_id = element.id, code.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        correct_response = client.post(
            f"/projects/{project_id}/elements/{element_id}/reviews",
            json={"action": "correct", "ibis_code": "41.10"},
        )
        review_id = correct_response.json()["review"]["id"]

        undo_response = client.post(f"/projects/{project_id}/reviews/{review_id}/undo")
        assert undo_response.status_code == 200
        body = undo_response.json()
        assert body["classification"]["ibis_code"] == "21.10"
        assert body["review"]["action"] == "undo"

        db = SessionLocal()
        assert (
            db.query(Classification)
            .filter(Classification.element_id == element_id)
            .count()
            == 3  # original + correct + undo, nothing deleted
        )
        db.close()
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(CodeList).filter(CodeList.id == code_id).delete()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_undo_review_restores_a_null_code_needs_review_state() -> None:
    """A real bug caught only by live browser testing, not by the test above:
    undo originally refused to restore a prior state with no code at all
    (e.g. jev's stub result) - but that's a completely legitimate thing to
    undo back to, not an error. Every element real_sample.ifc classifies
    through jev starts exactly here, so this is the common case in practice,
    not an edge case.
    """
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.flush()
    db.add(_classification(element.id, ibis_code=None, internal_element=None))
    code = CodeList(
        ibis_code="21.10",
        internal_element="Buitenwand beton",
        description="concrete wall",
        family="wall",
    )
    db.add(code)
    db.commit()
    element_id, code_id = element.id, code.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        correct_response = client.post(
            f"/projects/{project_id}/elements/{element_id}/reviews",
            json={"action": "correct", "ibis_code": "21.10"},
        )
        review_id = correct_response.json()["review"]["id"]

        undo_response = client.post(f"/projects/{project_id}/reviews/{review_id}/undo")
        assert undo_response.status_code == 200
        body = undo_response.json()
        assert body["classification"]["ibis_code"] is None
        assert body["classification"]["status"] == "needs_review"
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(CodeList).filter(CodeList.id == code_id).delete()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_review_endpoint_404_for_element_in_wrong_project() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    other_project_id, other_owner_id, _ = _setup_project()
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.commit()
    element_id = element.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        response = client.post(
            f"/projects/{other_project_id}/elements/{element_id}/reviews",
            json={"action": "approve"},
        )
        assert response.status_code == 404
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        cleanup_project_cascade(other_project_id, other_owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_review_requires_estimator_or_admin() -> None:
    project_id, owner_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.flush()
    db.add(_classification(element.id))
    db.commit()
    element_id = element.id
    db.close()

    reviewer_id = _estimator_client(role="viewer")
    try:
        response = client.post(
            f"/projects/{project_id}/elements/{element_id}/reviews",
            json={"action": "approve"},
        )
        assert response.status_code == 403
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()


def test_summary_corrected_count_reflects_a_real_correction() -> None:
    """Closes the loop on 4.3's "corrected is always 0 today, honestly" gap -
    app/ai/summary.py's logic was already correct, just had nothing to count.

    Uses a unique ibis_code rather than a plausible-looking literal like
    "21.10" - this project's tests run against the same real database as live
    manual verification (no separate test DB), so a literal code can collide
    with rows a live curl/browser session left behind. correct_element()'s own
    validation against an unknown code is already covered by
    test_correct_element_unknown_code_fails, so this test doesn't need to
    re-prove that path too.
    """
    project_id, owner_id, ifc_file_id = _setup_project()
    code_value = f"TEST-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    element = _element(ifc_file_id)
    db.add(element)
    db.flush()
    db.add(_classification(element.id))
    db.add(
        CodeList(
            ibis_code=code_value,
            internal_element="Buitenwand beton",
            description="concrete wall",
            family="wall",
        )
    )
    db.commit()
    element_id = element.id
    db.close()

    reviewer_id = _estimator_client()
    try:
        response = client.post(
            f"/projects/{project_id}/elements/{element_id}/reviews",
            json={"action": "correct", "ibis_code": code_value},
        )
        assert response.status_code == 201

        summary_response = client.get(f"/projects/{project_id}/summary")
        assert summary_response.status_code == 200
        assert summary_response.json()["corrected"] == 1
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, owner_id)
        db = SessionLocal()
        db.query(CodeList).filter(CodeList.ibis_code == code_value).delete()
        db.query(User).filter(User.id == reviewer_id).delete()
        db.commit()
        db.close()
