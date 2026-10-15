"""Phase 6.5: repeated correction patterns become suggested rules. See
app/ai/rule_suggestions.py's module docstring.
"""

import uuid

from fastapi.testclient import TestClient

from app.ai.reviews import correct_element
from app.ai.rule_suggestions import MIN_OCCURRENCES, generate_rule_suggestions
from app.core.security import create_access_token
from app.db.models import (
    Classification,
    CodeList,
    Element,
    IfcFile,
    Project,
    Rule,
    User,
)
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import cleanup_project_cascade

client = TestClient(app)


def _setup_project() -> tuple[int, int, int]:
    db = SessionLocal()
    user = User(
        email=f"rulesug-6.5-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.flush()
    project = Project(name="Rule Suggestion Test Project", created_by=user.id)
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


def _seed_repeated_corrections(
    ifc_file_id: int, user_id: int, ibis_code: str, count: int, group_hash: str
) -> list[int]:
    """Creates `count` elements sharing `group_hash`, each with a needs_review
    classification, then corrects every one of them to `ibis_code` - exactly
    the real-world shape a repeated correction pattern takes.
    """
    db = SessionLocal()
    code = db.query(CodeList).filter(
        CodeList.ibis_code == ibis_code
    ).first() or CodeList(
        ibis_code=ibis_code,
        internal_element="Buitenwand beton",
        description="concrete wall",
        family="wall",
    )
    if code.id is None:
        db.add(code)
        db.flush()
    user = db.get(User, user_id)

    review_ids = []
    for _ in range(count):
        element = Element(
            ifc_file_id=ifc_file_id,
            global_id=f"G{uuid.uuid4().hex[:8]}",
            ifc_class="IfcWall",
            predefined_type="SOLIDWALL",
            materials=[{"material": "Concrete", "thickness_mm": 200.0}],
            group_hash=group_hash,
        )
        db.add(element)
        db.flush()
        classification = Classification(
            element_id=element.id,
            ibis_code=None,
            internal_element=None,
            status="needs_review",
            source="llm",
            confidence=0.3,
        )
        db.add(classification)
        db.flush()
        result = correct_element(db, element, classification, ibis_code, user, None)
        review_ids.append(result.review.id)
    db.commit()
    db.close()
    return review_ids


def test_generate_rule_suggestions_creates_rule_after_min_occurrences() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    group_hash = uuid.uuid4().hex
    _seed_repeated_corrections(
        ifc_file_id, user_id, "21.10", MIN_OCCURRENCES, group_hash
    )

    db = SessionLocal()
    try:
        result = generate_rule_suggestions(db)
        db.commit()
        assert len(result.created) == 1
        rule = result.created[0]
        assert rule.status == "suggested"
        assert rule.result_ibis_code == "21.10"
        assert {"field": "ifc_class", "operator": "==", "value": "IfcWall"} in (
            rule.conditions
        )
        assert len(rule.source_corrections) == MIN_OCCURRENCES
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
        db = SessionLocal()
        db.query(Rule).filter(Rule.result_ibis_code == "21.10").delete()
        db.query(CodeList).filter(CodeList.ibis_code == "21.10").delete()
        db.commit()
        db.close()


def test_generate_rule_suggestions_skips_below_threshold() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    group_hash = uuid.uuid4().hex
    _seed_repeated_corrections(
        ifc_file_id, user_id, "21.10", MIN_OCCURRENCES - 1, group_hash
    )

    db = SessionLocal()
    try:
        result = generate_rule_suggestions(db)
        db.commit()
        assert result.created == []
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
        db = SessionLocal()
        db.query(CodeList).filter(CodeList.ibis_code == "21.10").delete()
        db.commit()
        db.close()


def test_generate_rule_suggestions_skips_already_covered_pattern() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    group_hash = uuid.uuid4().hex
    _seed_repeated_corrections(
        ifc_file_id, user_id, "21.10", MIN_OCCURRENCES, group_hash
    )

    db = SessionLocal()
    existing_rule = Rule(
        conditions=[
            {"field": "ifc_class", "operator": "==", "value": "IfcWall"},
            {"field": "predefined_type", "operator": "==", "value": "SOLIDWALL"},
            {"field": "material_keyword", "operator": "contains", "value": "Concrete"},
        ],
        result_ibis_code="21.10",
        result_internal_element="Buitenwand beton",
        priority=0,
        status="active",
    )
    db.add(existing_rule)
    db.commit()
    existing_rule_id = existing_rule.id
    db.close()

    db = SessionLocal()
    try:
        result = generate_rule_suggestions(db)
        db.commit()
        assert result.created == []
        assert result.already_covered_count == 1
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
        db = SessionLocal()
        db.query(Rule).filter(Rule.id == existing_rule_id).delete()
        db.query(CodeList).filter(CodeList.ibis_code == "21.10").delete()
        db.commit()
        db.close()


def _admin_client() -> int:
    db = SessionLocal()
    user = User(
        email=f"rulesug-6.5-admin-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    client.cookies.set(
        "access_token", create_access_token(user_id=user_id, role="admin")
    )
    return user_id


def test_suggest_rules_endpoint_creates_rule() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    group_hash = uuid.uuid4().hex
    _seed_repeated_corrections(
        ifc_file_id, user_id, "21.10", MIN_OCCURRENCES, group_hash
    )

    admin_id = _admin_client()
    try:
        response = client.post("/rules/suggest")
        assert response.status_code == 201
        body = response.json()
        assert len(body["created"]) == 1
        assert body["created"][0]["status"] == "suggested"
        assert body["created"][0]["result_ibis_code"] == "21.10"
    finally:
        client.cookies.clear()
        cleanup_project_cascade(project_id, user_id)
        db = SessionLocal()
        db.query(Rule).filter(Rule.result_ibis_code == "21.10").delete()
        db.query(CodeList).filter(CodeList.ibis_code == "21.10").delete()
        db.query(User).filter(User.id == admin_id).delete()
        db.commit()
        db.close()


def test_suggest_rules_endpoint_requires_admin() -> None:
    db = SessionLocal()
    user = User(
        email=f"rulesug-6.5-estimator-{uuid.uuid4().hex}@example.com",
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
    try:
        response = client.post("/rules/suggest")
        assert response.status_code == 403
    finally:
        client.cookies.clear()
        db = SessionLocal()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()
