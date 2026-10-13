"""Phase 2.7: extraction comparison report.

test_load_ground_truth_* exercises the Pydantic-validated CSV loader directly (no DB).
test_compare_extraction_* is the self-test confirmed with the user: there is no real
ground truth yet, so this proves the coverage/missing/deviation logic against our own
fixture - matched, missing-but-present-in-IFC (IfcProject, a class we don't extract),
missing-and-not-in-IFC (a bogus GlobalId), and a real quantity deviation - not that
real_sample.ifc's extraction is 100% accurate against client data.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db.models import IfcFile, Job, Project, User
from app.db.session import SessionLocal
from app.ifc.extraction_report import (
    GroundTruthRow,
    compare_extraction,
    load_ground_truth,
    render_markdown_report,
)
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file
from tests.conftest import cleanup_project_cascade

FIXTURES_DIR = Path(__file__).parent / "fixtures"

WALL_GLOBAL_ID = "1AQAupaRP1txwK1AGiN61V"  # area_net=6.35m2 in real_sample.ifc
PROJECT_ENTITY_GLOBAL_ID = "2Ndyd$OSX7s9A04nc4lyye"  # IfcProject - not extracted
BOGUS_GLOBAL_ID = "0000000000000000000000"  # not in the IFC file at all


def test_load_ground_truth_reads_and_validates_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "ground_truth.csv"
    csv_path.write_text(
        "file,global_id,expected_ibis_code,expected_internal_element,"
        "expected_quantity,unit,notes\n"
        "real_sample.ifc,ABC123,21.10,Buitenwand,6.35,m2,\n",
        encoding="utf-8",
    )

    rows = load_ground_truth(csv_path)

    assert rows == [
        GroundTruthRow(
            file="real_sample.ifc",
            global_id="ABC123",
            expected_ibis_code="21.10",
            expected_internal_element="Buitenwand",
            expected_quantity=6.35,
            unit="m2",
            notes=None,
        )
    ]


def test_load_ground_truth_rejects_non_numeric_quantity(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "file,global_id,expected_ibis_code,expected_internal_element,"
        "expected_quantity,unit,notes\n"
        "real_sample.ifc,ABC123,21.10,Buitenwand,not-a-number,m2,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_ground_truth(csv_path)


def test_compare_extraction_self_tested_against_real_sample_fixture(
    tmp_path: Path,
) -> None:
    db = SessionLocal()
    user = User(
        email="extraction-report-2.7@example.com", password_hash="x", role="estimator"
    )
    db.add(user)
    db.flush()
    project = Project(name="Extraction Report Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        fixture_path = FIXTURES_DIR / "real_sample.ifc"
        storage_key = "tests/2.7/real_sample.ifc"
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

        ground_truth = [
            GroundTruthRow(
                file="real_sample.ifc",
                global_id=WALL_GLOBAL_ID,
                expected_ibis_code="21.10",
                expected_quantity=6.35,
                unit="m2",
            ),
            GroundTruthRow(
                file="real_sample.ifc",
                global_id=PROJECT_ENTITY_GLOBAL_ID,
                expected_ibis_code="99.99",
            ),
            GroundTruthRow(
                file="real_sample.ifc",
                global_id=BOGUS_GLOBAL_ID,
                expected_ibis_code="88.88",
            ),
            GroundTruthRow(
                file="a-file-not-in-this-project.ifc",
                global_id="whatever",
            ),
        ]

        report = compare_extraction(db, project_id, ground_truth, tmp_path)

        assert report["total_rows"] == 4
        assert report["unmatched_files"] == ["a-file-not-in-this-project.ifc"]
        assert report["comparable_rows"] == 3
        assert report["matched"] == 1
        assert report["element_coverage_percent"] == pytest.approx(100 / 3)

        assert len(report["missing"]) == 2
        missing_by_global_id = {m["global_id"]: m for m in report["missing"]}
        assert missing_by_global_id[PROJECT_ENTITY_GLOBAL_ID]["ifc_class"] == (
            "IfcProject"
        )
        assert missing_by_global_id[BOGUS_GLOBAL_ID]["ifc_class"] is None
        assert report["missing_by_class"] == {"IfcProject": 1, "not in IFC file": 1}

        assert len(report["deviations"]) == 1
        deviation = report["deviations"][0]
        assert deviation["global_id"] == WALL_GLOBAL_ID
        assert deviation["actual_quantity"] == pytest.approx(6.35, abs=0.01)
        assert deviation["deviation_percent"] == pytest.approx(0.0, abs=0.5)
        assert report["avg_deviation_percent_by_code"]["21.10"] == pytest.approx(
            0.0, abs=0.5
        )

        markdown = render_markdown_report(report, project_id)
        assert "IfcProject" in markdown
        assert "21.10" in markdown
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_compare_extraction_empty_project_reports_zero_without_dividing_by_zero(
    tmp_path: Path,
) -> None:
    db = SessionLocal()
    user = User(
        email="extraction-report-2.7b@example.com", password_hash="x", role="estimator"
    )
    db.add(user)
    db.flush()
    project = Project(name="Empty Extraction Report Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        ground_truth = [
            GroundTruthRow(file="nonexistent.ifc", global_id="whatever"),
        ]
        report = compare_extraction(db, project_id, ground_truth, tmp_path)

        assert report["comparable_rows"] == 0
        assert report["element_coverage_percent"] == 0.0
        assert report["missing"] == []
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
