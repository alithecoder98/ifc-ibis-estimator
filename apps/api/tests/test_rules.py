"""Phase 3.2: rule engine.

test_rule_matches_*/test_match_rule_* exercise app/ai/rules.py directly against
plain (unpersisted) Element instances - pure logic, no DB needed, per the plan's own
"thorough unit tests" instruction covering match/no-match/priority.
test_load_rules_from_json_* and test_classify_elements_rules_* /
test_*_endpoint_* need the real DB.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.classify import classify_elements
from app.ai.jev import StubJevClient
from app.ai.rules import load_rules_from_json, match_rule, rule_matches
from app.core.security import create_access_token
from app.db.models import Classification, Element, IfcFile, Project, Rule, User
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import cleanup_project_cascade

client = TestClient(app)


def _wall(**overrides) -> Element:
    defaults = dict(
        ifc_file_id=1,
        global_id="G1",
        ifc_class="IfcWall",
        predefined_type="SOLIDWALL",
        is_external=True,
        load_bearing=True,
        storey="Ground Floor",
        materials=[{"material": "Concrete", "thickness_mm": 200.0}],
    )
    defaults.update(overrides)
    return Element(**defaults)


def _rule(**overrides) -> Rule:
    defaults = dict(
        conditions=[{"field": "ifc_class", "operator": "==", "value": "IfcWall"}],
        result_ibis_code="21.10",
        result_internal_element="Buitenwand beton",
        priority=0,
        status="active",
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_rule_matches_exact_field() -> None:
    assert rule_matches(_wall(), _rule()) is True
    assert rule_matches(_wall(ifc_class="IfcSlab"), _rule()) is False


def test_rule_matches_material_keyword_is_case_insensitive() -> None:
    rule = _rule(
        conditions=[
            {"field": "material_keyword", "operator": "contains", "value": "CONCRETE"}
        ]
    )
    assert rule_matches(_wall(), rule) is True
    assert (
        rule_matches(
            _wall(materials=[{"material": "Timber", "thickness_mm": 50.0}]), rule
        )
        is False
    )


def test_rule_matches_thickness_between() -> None:
    rule = _rule(
        conditions=[
            {"field": "thickness_mm", "operator": "between", "value": [150, 250]}
        ]
    )
    assert rule_matches(_wall(), rule) is True  # 200mm
    assert (
        rule_matches(
            _wall(materials=[{"material": "Concrete", "thickness_mm": 50.0}]), rule
        )
        is False
    )


def test_rule_matches_boolean_fields() -> None:
    rule = _rule(
        conditions=[{"field": "is_external", "operator": "==", "value": False}]
    )
    assert rule_matches(_wall(is_external=False), rule) is True
    assert rule_matches(_wall(is_external=True), rule) is False


def test_rule_matches_storey_keyword() -> None:
    rule = _rule(
        conditions=[
            {"field": "storey_keyword", "operator": "contains", "value": "ground"}
        ]
    )
    assert rule_matches(_wall(storey="00 Ground Floor"), rule) is True
    assert rule_matches(_wall(storey="First Floor"), rule) is False


def test_rule_matches_missing_field_never_matches() -> None:
    rule = _rule(
        conditions=[{"field": "storey_keyword", "operator": "contains", "value": "x"}]
    )
    assert rule_matches(_wall(storey=None), rule) is False


def test_rule_matches_requires_all_conditions_and() -> None:
    rule = _rule(
        conditions=[
            {"field": "ifc_class", "operator": "==", "value": "IfcWall"},
            {"field": "is_external", "operator": "==", "value": True},
        ]
    )
    assert rule_matches(_wall(), rule) is True
    assert rule_matches(_wall(is_external=False), rule) is False


def test_match_rule_picks_highest_priority_among_matches() -> None:
    low = _rule(priority=1, result_ibis_code="low")
    high = _rule(priority=10, result_ibis_code="high")
    result = match_rule(_wall(), [low, high])
    assert result.result_ibis_code == "high"


def test_match_rule_returns_none_when_nothing_matches() -> None:
    rule = _rule(
        conditions=[{"field": "ifc_class", "operator": "==", "value": "IfcSlab"}]
    )
    assert match_rule(_wall(), [rule]) is None


def test_load_rules_from_json_inserts_validated_rows(tmp_path: Path) -> None:
    json_path = tmp_path / "rules.json"
    json_path.write_text(
        """
        [
          {
            "conditions": [{"field": "ifc_class", "operator": "==", "value": "IfcWall"}],
            "result_ibis_code": "21.10",
            "result_internal_element": "Buitenwand beton",
            "priority": 5
          }
        ]
        """,
        encoding="utf-8",
    )
    db = SessionLocal()
    rule_ids: list[int] = []
    try:
        rules = load_rules_from_json(db, json_path)
        db.commit()
        rule_ids = [r.id for r in rules]
        assert len(rules) == 1
        assert rules[0].result_ibis_code == "21.10"
        assert rules[0].priority == 5
        assert rules[0].status == "active"
    finally:
        db.query(Rule).filter(Rule.id.in_(rule_ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_classify_elements_rule_match_skips_jev_entirely() -> None:
    db = SessionLocal()
    project_id, user_id, rule_id = None, None, None
    try:
        user = User(email="rules-3.2@example.com", password_hash="x", role="estimator")
        db.add(user)
        db.flush()
        user_id = user.id
        project = Project(name="Rules Test Project", created_by=user.id)
        db.add(project)
        db.flush()
        project_id = project.id
        ifc_file = IfcFile(
            project_id=project.id,
            filename="x.ifc",
            storage_key="unused",
            size_bytes=1,
            uploaded_by=user.id,
        )
        db.add(ifc_file)
        db.flush()

        rule = _rule()
        db.add(rule)
        db.flush()
        rule_id = rule.id

        matching = Element(
            ifc_file_id=ifc_file.id,
            global_id="MATCH1",
            ifc_class="IfcWall",
            is_external=True,
            load_bearing=True,
            materials=[{"material": "Concrete", "thickness_mm": 200.0}],
            profile_text="profile-match",
            group_hash="group-match",
        )
        non_matching = Element(
            ifc_file_id=ifc_file.id,
            global_id="NOMATCH1",
            ifc_class="IfcSlab",
            profile_text="profile-nomatch",
            group_hash="group-nomatch",
        )
        db.add_all([matching, non_matching])
        db.flush()

        call_count = 0

        class CountingStubClient:
            def classify(self, profile_text: str):
                nonlocal call_count
                call_count += 1
                return StubJevClient().classify(profile_text)

        import app.ai.classify as classify_module

        original_get_jev_client = classify_module.get_jev_client
        classify_module.get_jev_client = lambda: CountingStubClient()
        try:
            classify_elements(db, [matching, non_matching])
        finally:
            classify_module.get_jev_client = original_get_jev_client
        db.commit()

        assert call_count == 1  # only the non-matching element needed jev

        classifications = {
            c.element_id: c
            for c in db.query(Classification)
            .filter(Classification.element_id.in_([matching.id, non_matching.id]))
            .all()
        }
        rule_classification = classifications[matching.id]
        assert rule_classification.source == "rule"
        assert rule_classification.confidence == 1.0
        assert rule_classification.status == "auto_accepted"
        assert rule_classification.ibis_code == "21.10"

        jev_classification = classifications[non_matching.id]
        assert jev_classification.source == "jev"
    finally:
        db.close()
        if rule_id is not None:
            db = SessionLocal()
            db.query(Rule).filter(Rule.id == rule_id).delete()
            db.commit()
            db.close()
        if project_id is not None:
            cleanup_project_cascade(project_id, user_id)


@pytest.fixture
def admin_client():
    db = SessionLocal()
    user = User(email="rules-3.2b@example.com", password_hash="x", role="admin")
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


def test_rules_crud_endpoints(admin_client: TestClient) -> None:
    create_response = admin_client.post(
        "/rules",
        json={
            "conditions": [
                {"field": "ifc_class", "operator": "==", "value": "IfcWall"}
            ],
            "result_ibis_code": "21.10",
            "result_internal_element": "Buitenwand beton",
            "priority": 5,
        },
    )
    assert create_response.status_code == 201
    rule_id = create_response.json()["id"]

    try:
        list_response = admin_client.get("/rules")
        assert list_response.status_code == 200
        assert any(r["id"] == rule_id for r in list_response.json())

        get_response = admin_client.get(f"/rules/{rule_id}")
        assert get_response.status_code == 200
        assert get_response.json()["result_ibis_code"] == "21.10"

        patch_response = admin_client.patch(f"/rules/{rule_id}", json={"priority": 99})
        assert patch_response.status_code == 200
        assert patch_response.json()["priority"] == 99
    finally:
        delete_response = admin_client.delete(f"/rules/{rule_id}")
        assert delete_response.status_code == 204
        assert admin_client.get(f"/rules/{rule_id}").status_code == 404


def test_rules_create_requires_admin() -> None:
    db = SessionLocal()
    user = User(email="rules-3.2c@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    try:
        client.cookies.set(
            "access_token", create_access_token(user_id=user_id, role="estimator")
        )
        response = client.post(
            "/rules",
            json={
                "conditions": [],
                "result_ibis_code": "21.10",
                "result_internal_element": "x",
            },
        )
        assert response.status_code == 403
    finally:
        client.cookies.clear()
        db = SessionLocal()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()
