"""Phase 3.6: threshold calibration.

test_pick_threshold_* is a pure self-test over hand-built (confidence, is_correct)
rows - no real ground truth exists yet (same blocker as P.4/2.7), so this proves the
threshold-sweep logic is correct, not a real calibrated threshold.
test_gather_scored_rows_* needs the real DB.
"""

from app.ai.calibrate import gather_scored_rows, pick_threshold
from app.db.models import Classification, Element, IfcFile, Project, User
from app.db.session import SessionLocal
from tests.conftest import cleanup_project_cascade


def test_pick_threshold_picks_lowest_clearing_target() -> None:
    # 10 rows at confidence 0.9 (7 correct, 3 wrong -> 70% precision if included -
    # clearly below 95%), 10 rows at confidence 0.95 (all correct). Accepting
    # everything (threshold 0.0 or 0.9) only reaches 17/20 = 85% precision, so the
    # lowest threshold that actually clears 95% is 0.95, not a lower one.
    rows = [(0.9, True)] * 7 + [(0.9, False)] * 3 + [(0.95, True)] * 10

    result = pick_threshold(rows, target_precision=0.95)

    assert result["achieved"] is True
    assert result["threshold"] == 0.95
    assert result["precision"] == 1.0
    assert result["auto_accept_rate"] == 10 / 20


def test_pick_threshold_returns_not_achieved_when_nothing_clears_target() -> None:
    rows = [(0.9, True)] * 5 + [(0.9, False)] * 5  # 50% precision, can't reach 95%

    result = pick_threshold(rows, target_precision=0.95)

    assert result["achieved"] is False
    assert result["auto_accept_rate"] == 0.0


def test_pick_threshold_empty_input() -> None:
    result = pick_threshold([], target_precision=0.95)
    assert result["achieved"] is False
    assert result["threshold"] == 1.0


def test_pick_threshold_all_correct_picks_lowest_threshold() -> None:
    rows = [(0.1, True), (0.5, True), (0.9, True)]

    result = pick_threshold(rows, target_precision=0.95)

    # Every row is correct regardless of confidence, so even the lowest threshold
    # (0.0 - accept everything) already has 100% precision.
    assert result["threshold"] == 0.0
    assert result["auto_accept_rate"] == 1.0


def test_gather_scored_rows_matches_by_global_id_and_latest_classification() -> None:
    db = SessionLocal()
    user = User(email="calibrate-3.6@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Calibrate Test Project", created_by=user.id)
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

    correct_element = Element(
        ifc_file_id=ifc_file.id, global_id="G1", ifc_class="IfcWall"
    )
    wrong_element = Element(
        ifc_file_id=ifc_file.id, global_id="G2", ifc_class="IfcWall"
    )
    unmatched_element = Element(
        ifc_file_id=ifc_file.id, global_id="G3", ifc_class="IfcWall"
    )
    db.add_all([correct_element, wrong_element, unmatched_element])
    db.flush()

    db.add_all(
        [
            Classification(
                element_id=correct_element.id,
                ibis_code="21.10",
                confidence=0.9,
                status="auto_accepted",
                source="llm",
            ),
            Classification(
                element_id=wrong_element.id,
                ibis_code="99.99",
                confidence=0.85,
                status="auto_accepted",
                source="llm",
            ),
        ]
    )
    db.commit()
    project_id, user_id = project.id, user.id

    try:
        ground_truth = {"G1": "21.10", "G2": "21.10"}  # G3 deliberately not covered
        rows = gather_scored_rows(db, project_id, ground_truth)

        assert sorted(rows) == sorted([(0.9, True), (0.85, False)])
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
