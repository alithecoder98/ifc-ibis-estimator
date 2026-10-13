"""Phase 3.8: evaluation harness.

test_evaluate_* is a pure self-test over hand-built EvaluationRow lists - no real
ground truth exists yet (same blocker as P.4/2.7/3.6), so this proves the metric
logic is correct, not a real accuracy number. test_gather_evaluation_rows_* and
test_total_tokens_for_project_* need the real DB.
"""

from app.ai.evaluate import (
    EvaluationRow,
    evaluate,
    gather_evaluation_rows,
    render_markdown,
    total_tokens_for_project,
)
from app.db.models import Classification, Element, IfcFile, Project, User
from app.db.session import SessionLocal
from tests.conftest import cleanup_project_cascade


def _row(**overrides) -> EvaluationRow:
    defaults = dict(
        global_id="G1",
        family="wall",
        expected_ibis_code="21.10",
        actual_ibis_code="21.10",
        is_correct=True,
        status="auto_accepted",
        source="llm",
        prompt_tokens=10,
        completion_tokens=5,
    )
    defaults.update(overrides)
    return EvaluationRow(**defaults)


def test_evaluate_empty_rows_returns_zeros_without_dividing_by_zero() -> None:
    report = evaluate([], 0, 0)
    assert report.n_compared == 0
    assert report.overall_accuracy == 0.0
    assert report.auto_accept_rate == 0.0
    assert report.auto_accept_precision is None
    assert report.unflagged_error_rate == 0.0


def test_evaluate_overall_accuracy() -> None:
    rows = [_row(is_correct=True), _row(is_correct=True), _row(is_correct=False)]
    report = evaluate(rows, 0, 0)
    assert report.overall_accuracy == 2 / 3


def test_evaluate_auto_accept_rate_and_precision() -> None:
    rows = [
        _row(status="auto_accepted", is_correct=True),
        _row(status="auto_accepted", is_correct=False),  # wrong but auto-accepted
        _row(status="needs_review", is_correct=False),
    ]
    report = evaluate(rows, 0, 0)
    assert report.auto_accept_rate == 2 / 3
    assert report.auto_accept_precision == 1 / 2  # 1 of 2 auto-accepted was correct


def test_evaluate_auto_accept_precision_is_none_when_nothing_auto_accepted() -> None:
    rows = [_row(status="needs_review", is_correct=False)]
    report = evaluate(rows, 0, 0)
    assert report.auto_accept_precision is None


def test_evaluate_unflagged_error_rate_counts_only_wrong_auto_accepted() -> None:
    rows = [
        _row(status="auto_accepted", is_correct=True),  # fine
        _row(status="auto_accepted", is_correct=False),  # unflagged error - dangerous
        _row(status="needs_review", is_correct=False),  # wrong, but flagged for review
    ]
    report = evaluate(rows, 0, 0)
    assert report.unflagged_error_rate == 1 / 3


def test_evaluate_accuracy_by_family() -> None:
    rows = [
        _row(family="wall", is_correct=True),
        _row(family="wall", is_correct=False),
        _row(family="roof", is_correct=True),
    ]
    report = evaluate(rows, 0, 0)
    assert report.accuracy_by_family == {"wall": 0.5, "roof": 1.0}


def test_evaluate_passes_through_token_totals() -> None:
    report = evaluate([_row()], 1234, 567)
    assert report.total_prompt_tokens == 1234
    assert report.total_completion_tokens == 567
    assert report.cost_usd == 0.0


def test_render_markdown_includes_key_metrics() -> None:
    report = evaluate([_row(family="wall")], 100, 50)
    markdown = render_markdown(report, project_id=42, generated_at="2026-10-13T000000Z")
    assert "project 42" in markdown
    assert "Overall accuracy" in markdown
    assert "wall" in markdown
    assert "100 prompt" in markdown


def test_gather_evaluation_rows_matches_latest_classification_and_family() -> None:
    db = SessionLocal()
    user = User(email="evaluate-3.8@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Evaluate Test Project", created_by=user.id)
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

    element = Element(ifc_file_id=ifc_file.id, global_id="G1", ifc_class="IfcWall")
    unmatched = Element(ifc_file_id=ifc_file.id, global_id="G2", ifc_class="IfcRoof")
    db.add_all([element, unmatched])
    db.flush()

    db.add(
        Classification(
            element_id=element.id,
            ibis_code="99.99",
            status="needs_review",
            source="jev",
        )
    )
    # A real commit, not just flush - two inserts in the same transaction share
    # Postgres's now() for that transaction, so "latest by created_at" would tie.
    db.commit()
    db.add(
        Classification(
            element_id=element.id,
            ibis_code="21.10",
            status="auto_accepted",
            source="llm",
            prompt_tokens=10,
            completion_tokens=5,
        )
    )
    db.commit()
    project_id, user_id = project.id, user.id

    try:
        rows = gather_evaluation_rows(db, project_id, {"G1": "21.10"})
        assert len(rows) == 1
        assert rows[0].family == "wall"
        assert rows[0].actual_ibis_code == "21.10"  # the later (llm) row, not jev
        assert rows[0].is_correct is True
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_total_tokens_for_project_sums_all_llm_rows_not_just_latest() -> None:
    db = SessionLocal()
    user = User(email="evaluate-3.8b@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Evaluate Tokens Project", created_by=user.id)
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
    element = Element(ifc_file_id=ifc_file.id, global_id="G1", ifc_class="IfcWall")
    db.add(element)
    db.flush()

    # A superseded (re-run) llm row still cost real tokens, plus a current one, plus
    # a jev row that must NOT be counted.
    db.add_all(
        [
            Classification(
                element_id=element.id,
                status="needs_review",
                source="llm",
                prompt_tokens=100,
                completion_tokens=20,
            ),
            Classification(
                element_id=element.id,
                status="auto_accepted",
                source="llm",
                prompt_tokens=50,
                completion_tokens=10,
            ),
            Classification(element_id=element.id, status="needs_review", source="jev"),
        ]
    )
    db.commit()
    project_id, user_id = project.id, user.id

    try:
        prompt_tokens, completion_tokens = total_tokens_for_project(db, project_id)
        assert prompt_tokens == 150
        assert completion_tokens == 30
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
