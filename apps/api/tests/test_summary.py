"""Phase 4.3: project summary (Overview tab stat cards, totals-by-code table,
warnings panel).
"""

import uuid

from app.ai.summary import (
    QUANTITY_PRECEDENCE,
    _primary_quantity,
    compute_summary,
    latest_classifications_by_element,
)
from app.db.models import (
    Classification,
    Element,
    IfcFile,
    Project,
    Quantity,
    Review,
    User,
)
from app.db.session import SessionLocal
from tests.conftest import cleanup_project_cascade


def _quantity(quantity_type: str, value: float, unit: str) -> Quantity:
    return Quantity(quantity_type=quantity_type, value=value, unit=unit, source="qto")


def test_primary_quantity_prefers_net_over_gross() -> None:
    quantities = [
        _quantity("area_gross", 50.0, "m2"),
        _quantity("area_net", 45.0, "m2"),
    ]
    assert _primary_quantity(quantities) == (45.0, "m2")


def test_primary_quantity_falls_back_through_precedence() -> None:
    quantities = [_quantity("count", 3.0, "st")]
    assert _primary_quantity(quantities) == (3.0, "st")
    assert QUANTITY_PRECEDENCE[-1] == "count"


def test_primary_quantity_none_when_no_quantities() -> None:
    assert _primary_quantity([]) is None


def _setup_project() -> tuple[int, int, int]:
    db = SessionLocal()
    # Unique per call, not a fixed literal - if one test fails before its own
    # cleanup runs, a shared email would make every later call collide on the
    # unique constraint too, cascading one failure into unrelated tests.
    user = User(
        email=f"summary-4.3-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.flush()
    project = Project(name="Summary Test Project", created_by=user.id)
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


def test_compute_summary_empty_project_has_no_elements() -> None:
    project_id, user_id, _ = _setup_project()
    db = SessionLocal()
    try:
        summary = compute_summary(db, project_id)
        assert summary.total_elements == 0
        assert summary.auto_accepted == 0
        assert summary.needs_review == 0
        assert summary.corrected == 0
        assert summary.totals_by_code == []
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_compute_summary_counts_statuses_warnings_and_totals() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    try:
        wall_a = Element(ifc_file_id=ifc_file_id, global_id="G1", ifc_class="IfcWall")
        wall_b = Element(ifc_file_id=ifc_file_id, global_id="G2", ifc_class="IfcWall")
        proxy = Element(
            ifc_file_id=ifc_file_id, global_id="G3", ifc_class="IfcBuildingElementProxy"
        )
        unmapped = Element(ifc_file_id=ifc_file_id, global_id="G4", ifc_class="IfcSlab")
        db.add_all([wall_a, wall_b, proxy, unmapped])
        db.flush()

        # wall_a: 200m2 gross + 180m2 net -> net wins, no double count.
        db.add_all(
            [
                Quantity(
                    element_id=wall_a.id,
                    quantity_type="area_gross",
                    value=200.0,
                    unit="m2",
                    source="qto",
                ),
                Quantity(
                    element_id=wall_a.id,
                    quantity_type="area_net",
                    value=180.0,
                    unit="m2",
                    source="qto",
                ),
                Quantity(
                    element_id=wall_b.id,
                    quantity_type="area_net",
                    value=20.0,
                    unit="m2",
                    source="qto",
                ),
            ]
        )

        db.add_all(
            [
                Classification(
                    element_id=wall_a.id,
                    ibis_code="21.10",
                    internal_element="Buitenwand beton",
                    status="auto_accepted",
                    source="rule",
                ),
                Classification(
                    element_id=wall_b.id,
                    ibis_code="21.10",
                    internal_element="Buitenwand beton",
                    status="needs_review",
                    source="llm",
                ),
                Classification(
                    element_id=proxy.id,
                    ibis_code="90.10",
                    internal_element="Overig",
                    status="needs_review",
                    source="llm",
                    flags=["proxy_element"],
                ),
                Classification(
                    element_id=unmapped.id,
                    ibis_code=None,
                    status="needs_review",
                    source="llm",
                    flags=["code_none", "missing_quantity"],
                ),
            ]
        )
        db.commit()

        summary = compute_summary(db, project_id)

        assert summary.total_elements == 4
        assert summary.auto_accepted == 1
        assert summary.needs_review == 3
        assert summary.proxy_element_count == 1
        assert summary.missing_quantity_count == 1
        assert summary.unmapped_count == 1
        assert summary.corrected == 0

        wall_total = next(t for t in summary.totals_by_code if t.ibis_code == "21.10")
        assert wall_total.unit == "m2"
        assert wall_total.element_count == 2
        assert wall_total.quantity == 200.0  # 180 (net, not 200 gross) + 20
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_compute_summary_counts_distinct_corrected_elements() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    try:
        element = Element(ifc_file_id=ifc_file_id, global_id="G1", ifc_class="IfcWall")
        db.add(element)
        db.flush()
        classification = Classification(
            element_id=element.id,
            ibis_code="21.10",
            internal_element="Buitenwand beton",
            status="auto_accepted",
            source="rule",
        )
        db.add(classification)
        db.flush()
        db.add_all(
            [
                Review(
                    classification_id=classification.id,
                    user_id=user_id,
                    action="correct",
                    before={},
                    after={},
                ),
                Review(
                    classification_id=classification.id,
                    user_id=user_id,
                    action="approve",
                    before={},
                    after={},
                ),
            ]
        )
        db.commit()

        summary = compute_summary(db, project_id)
        assert summary.corrected == 1
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_latest_classifications_by_element_tiebreaks_on_id_when_created_at_ties() -> (
    None
):
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    try:
        element = Element(ifc_file_id=ifc_file_id, global_id="G1", ifc_class="IfcWall")
        db.add(element)
        db.flush()
        # Both added before a single commit - same created_at (same transaction),
        # same "both"-engine shape classify.py actually produces.
        first = Classification(
            element_id=element.id, status="needs_review", source="jev"
        )
        second = Classification(
            element_id=element.id,
            ibis_code="21.10",
            status="auto_accepted",
            source="llm",
        )
        db.add_all([first, second])
        db.commit()
        assert first.created_at == second.created_at  # same transaction
        assert second.id > first.id

        latest = latest_classifications_by_element(db, [element.id])
        assert latest[element.id].id == second.id
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
