"""Phase P.4: accuracy comparison.

test_load_ground_truth_* exercises the CSV reader directly (no DB). test_compare_accuracy_*
is the self-test confirmed with the user: there is no real ground truth yet, so this proves
the comparison logic is correct against our own fixture, not that jev is 50% accurate.
Real accuracy measurement is still blocked on njderidder's reference calculations.
"""

from pathlib import Path

from app.ai.accuracy import compare_accuracy, load_ground_truth
from app.db.models import Element, IfcFile, Job, Project, User
from app.db.session import SessionLocal
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file
from tests.conftest import cleanup_project_cascade

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_load_ground_truth_reads_two_column_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "ground_truth.csv"
    csv_path.write_text(
        "global_id,expected_ibis_code\nABC123,21.10\nDEF456,33.40\n", encoding="utf-8"
    )

    ground_truth = load_ground_truth(csv_path)

    assert ground_truth == {"ABC123": "21.10", "DEF456": "33.40"}


def test_compare_accuracy_self_tested_against_real_sample_fixture() -> None:
    # Self-test, not a real measurement: jev is stubbed, so every real classification
    # already in the DB has ibis_code=None. We craft a ground truth by hand - one entry
    # expecting None (so it matches the stub) and one expecting a real code (so it
    # doesn't) - purely to prove compare_accuracy()'s counting and mismatch-reporting
    # logic is correct. This says nothing about jev's real accuracy.
    db = SessionLocal()
    user = User(email="accuracy-p4@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Accuracy Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        fixture_path = FIXTURES_DIR / "real_sample.ifc"
        storage_key = "tests/P.4/real_sample.ifc"
        with open(fixture_path, "rb") as fh:
            upload_fileobj(fh, storage_key)

        ifc_file = IfcFile(
            project_id=project.id,
            filename="real_sample.ifc",
            storage_key=storage_key,
            ifc_schema="IFC2X3",
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

        elements = (
            db.query(Element)
            .filter(Element.ifc_file_id == ifc_file.id)
            .order_by(Element.id)
            .all()
        )
        assert len(elements) == 13

        matching_element, mismatching_element = elements[0], elements[1]
        ground_truth = {
            matching_element.global_id: None,  # stub jev also returns None -> matches
            mismatching_element.global_id: "99.99",  # stub returns None -> mismatch
        }

        report = compare_accuracy(db, project_id, ground_truth)

        assert report["compared"] == 2
        assert report["correct"] == 1
        assert report["accuracy_percent"] == 50.0
        assert len(report["mismatches"]) == 1
        assert report["mismatches"][0]["global_id"] == mismatching_element.global_id
        assert report["mismatches"][0]["expected_ibis_code"] == "99.99"
        assert report["mismatches"][0]["actual_ibis_code"] is None
        assert len(report["elements_not_in_ground_truth"]) == 11
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_compare_accuracy_empty_project_reports_zero_without_dividing_by_zero() -> None:
    db = SessionLocal()
    user = User(email="accuracy-p4b@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Empty Accuracy Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        report = compare_accuracy(db, project_id, {"nonexistent-global-id": "21.10"})
        assert report == {
            "compared": 0,
            "correct": 0,
            "accuracy_percent": 0.0,
            "mismatches": [],
            "elements_not_in_ground_truth": [],
        }
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
