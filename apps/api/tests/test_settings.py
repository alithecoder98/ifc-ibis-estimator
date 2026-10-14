"""Phase 4.6: the admin-editable auto-accept confidence threshold.

test_get_/set_auto_accept_threshold_* exercise app/core/settings_store.py directly
against the real DB. test_classify_elements_uses_db_threshold_override proves
app/ai/classify.py actually reads the DB-backed value, not just confidence.py's
env-sourced default - the whole point of this sub-phase being DB-backed rather
than an env var is that a change takes effect on the next classification run
without a restart. test_*_endpoint_* cover the HTTP layer.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.classify import classify_elements
from app.ai.embedder import FakeEmbedder
from app.ai.llm import LLMResult
from app.core.config import get_settings
from app.core.constants import EMBEDDING_DIM
from app.core.security import create_access_token
from app.core.settings_store import get_auto_accept_threshold, set_auto_accept_threshold
from app.db.models import (
    AppSetting,
    Classification,
    CodeList,
    Element,
    IfcFile,
    Project,
    Quantity,
    User,
)
from app.db.models.settings import AUTO_ACCEPT_THRESHOLD_KEY
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import cleanup_project_cascade

client = TestClient(app)


def _clear_threshold_override() -> None:
    db = SessionLocal()
    db.query(AppSetting).filter(AppSetting.key == AUTO_ACCEPT_THRESHOLD_KEY).delete()
    db.commit()
    db.close()


def test_get_auto_accept_threshold_falls_back_to_settings_default() -> None:
    db = SessionLocal()
    try:
        _clear_threshold_override()
        assert get_auto_accept_threshold(db) == get_settings().auto_accept_threshold
    finally:
        db.close()


def test_set_and_get_auto_accept_threshold_persists() -> None:
    db = SessionLocal()
    try:
        set_auto_accept_threshold(db, 0.65)
        assert get_auto_accept_threshold(db) == 0.65

        # A fresh session must see it too - this is what makes it "DB-backed, not
        # a change to this process's own in-memory Settings singleton".
        db2 = SessionLocal()
        try:
            assert get_auto_accept_threshold(db2) == 0.65
        finally:
            db2.close()
    finally:
        _clear_threshold_override()
        db.close()


class _FakeLLMClient:
    def __init__(self, result: LLMResult):
        self.result = result

    def chat(self, prompt: str):
        return (
            {
                "ibis_code": self.result.ibis_code or "NONE",
                "internal_element": self.result.internal_element,
                "reasoning": self.result.reasoning,
                "self_score": self.result.self_score,
                "flags": self.result.flags,
            },
            10,
            5,
        )


def test_classify_elements_uses_db_threshold_override() -> None:
    """Same scoring inputs as test_classify.py's engine_llm_calls_llm_only test
    (self_score=0.9, one matching candidate, complete element data) - that combo
    scores 0.85 final confidence, auto_accepted at the 0.8 settings default.
    Raising the DB-backed threshold above 0.85 must flip the same inputs to
    needs_review, proving classify.py reads the override, not just the default.
    """
    db = SessionLocal()
    user = User(
        email=f"settings-4.6-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.flush()
    project = Project(
        name="Settings 4.6 Threshold Project",
        created_by=user.id,
        classification_engine="llm",
    )
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
    db.flush()
    element = Element(
        ifc_file_id=ifc_file.id,
        global_id="G1",
        ifc_class="IfcWall",
        is_external=True,
        materials=[{"material": "Concrete", "thickness_mm": 200.0}],
        profile_text="profile",
        group_hash=uuid.uuid4().hex,
    )
    db.add(element)
    db.flush()
    db.add(
        Quantity(
            element_id=element.id,
            quantity_type="area_net",
            value=10.0,
            unit="m2",
            source="qto",
        )
    )
    code = CodeList(
        ibis_code="21.10",
        internal_element="Buitenwand beton",
        description="concrete exterior wall",
        family="wall",
        embedding=FakeEmbedder(EMBEDDING_DIM).embed(["concrete exterior wall"])[0],
    )
    db.add(code)
    db.commit()
    project_id, user_id, element_id, code_id = project.id, user.id, element.id, code.id

    try:
        set_auto_accept_threshold(db, 0.9)  # above the 0.85 this element will score

        llm_client = _FakeLLMClient(
            LLMResult(
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                reasoning="matches",
                self_score=0.9,
                flags=[],
            )
        )

        import app.ai.classify as classify_module

        original_get_embedder = classify_module.get_embedder
        original_get_llm_client = classify_module.get_llm_client
        classify_module.get_embedder = lambda: FakeEmbedder(EMBEDDING_DIM)
        classify_module.get_llm_client = lambda: llm_client
        try:
            element = db.get(Element, element_id)
            classify_elements(db, [element])
        finally:
            classify_module.get_embedder = original_get_embedder
            classify_module.get_llm_client = original_get_llm_client
        db.commit()

        classification = (
            db.query(Classification)
            .filter(Classification.element_id == element_id)
            .one()
        )
        assert classification.confidence == pytest.approx(0.85)
        assert classification.status == "needs_review"
    finally:
        _clear_threshold_override()
        db.close()
        db2 = SessionLocal()
        db2.query(CodeList).filter(CodeList.id == code_id).delete()
        db2.commit()
        db2.close()
        cleanup_project_cascade(project_id, user_id)


@pytest.fixture
def admin_client():
    db = SessionLocal()
    user = User(
        email=f"settings-4.6-admin-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    client.cookies.set(
        "access_token", create_access_token(user_id=user_id, role="admin")
    )
    db.close()
    yield client
    client.cookies.clear()
    db = SessionLocal()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def test_get_threshold_endpoint(admin_client: TestClient) -> None:
    try:
        response = admin_client.get("/settings/threshold")
        assert response.status_code == 200
        assert response.json() == {
            "auto_accept_threshold": get_settings().auto_accept_threshold
        }
    finally:
        _clear_threshold_override()


def test_update_threshold_endpoint(admin_client: TestClient) -> None:
    try:
        response = admin_client.patch(
            "/settings/threshold", json={"auto_accept_threshold": 0.7}
        )
        assert response.status_code == 200
        assert response.json() == {"auto_accept_threshold": 0.7}

        get_response = admin_client.get("/settings/threshold")
        assert get_response.json() == {"auto_accept_threshold": 0.7}
    finally:
        _clear_threshold_override()


def test_update_threshold_endpoint_rejects_out_of_range_value(
    admin_client: TestClient,
) -> None:
    response = admin_client.patch(
        "/settings/threshold", json={"auto_accept_threshold": 1.5}
    )
    assert response.status_code == 422


def test_update_threshold_requires_admin() -> None:
    db = SessionLocal()
    user = User(
        email=f"settings-4.6-estimator-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    try:
        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.patch(
            "/settings/threshold", json={"auto_accept_threshold": 0.7}
        )
        assert response.status_code == 403
    finally:
        client.cookies.clear()
        _clear_threshold_override()
        db = SessionLocal()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()
