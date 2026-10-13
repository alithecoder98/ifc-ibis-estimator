"""Sub-phase 2.2: element extraction.

test_extract_elements_* exercise app/ifc/extract.py directly against both fixtures -
no DB/network needed. test_process_ifc_file_* drive the real worker function end to
end (real DB, real Garage download) - same pattern as test_jobs.py's fake-queue test.
"""

from pathlib import Path

import ifcopenshell

from app.db.models import Element, IfcFile, Job, Project, Quantity, User
from app.db.session import SessionLocal
from app.ifc.extract import extract_elements
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_extract_elements_from_synthetic_fixture_finds_every_type() -> None:
    ifc_file = ifcopenshell.open(str(FIXTURES_DIR / "sample.ifc"))
    elements = list(extract_elements(ifc_file))

    assert len(elements) == 12
    classes = {e["ifc_class"] for e in elements}
    assert classes == {
        "IfcWall",
        "IfcSlab",
        "IfcRoof",
        "IfcFooting",
        "IfcColumn",
        "IfcBeam",
        "IfcStair",
        "IfcRailing",
        "IfcDoor",
        "IfcWindow",
        "IfcCovering",
        "IfcBuildingElementProxy",
    }

    wall = next(e for e in elements if e["ifc_class"] == "IfcWall")
    assert wall["global_id"]
    assert wall["name"] == "Exterior Wall 01"
    assert wall["predefined_type"] == "SOLIDWALL"
    assert wall["storey"] == "Ground Floor"
    assert wall["is_external"] is True
    assert wall["load_bearing"] is True
    assert wall["materials"] == [{"material": "Concrete", "thickness_mm": 200.0}]
    assert "Pset_WallCommon" in wall["psets"]


def test_extract_elements_deduplicates_by_entity_id() -> None:
    # IfcWall's by_type() query already includes IfcWallStandardCase etc.; explicitly
    # re-querying a class whose instances were already seen must not double-count.
    ifc_file = ifcopenshell.open(str(FIXTURES_DIR / "sample.ifc"))
    elements = list(extract_elements(ifc_file))
    global_ids = [e["global_id"] for e in elements]
    assert len(global_ids) == len(set(global_ids))


def test_extract_elements_from_real_sample_does_not_crash_on_real_world_messiness() -> (
    None
):
    # real_sample.ifc (public, see fixtures/README.md) has elements with no Pset at
    # all, materials with no layer thickness, and spatial containment that isn't
    # always a direct storey - extraction must handle all of that as None, not raise.
    ifc_file = ifcopenshell.open(str(FIXTURES_DIR / "real_sample.ifc"))
    elements = list(extract_elements(ifc_file))

    assert len(elements) == 13
    classes = {e["ifc_class"] for e in elements}
    assert classes == {"IfcWall", "IfcSlab", "IfcRoof", "IfcBuildingElementProxy"}
    assert sum(1 for e in elements if e["ifc_class"] == "IfcWall") == 4

    wall = next(e for e in elements if e["ifc_class"] == "IfcWall")
    assert wall["storey"] == "00 groundfloor"
    assert wall["materials"][0]["material"]  # has a material, even without a pset


def _create_user_and_project() -> tuple[User, Project]:
    db = SessionLocal()
    user = User(email="estimator-2.2@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Extraction Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    db.close()
    return user, project


def _cleanup(project_id: int, user_id: int) -> None:
    db = SessionLocal()
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    if ifc_file_ids:
        element_ids = [
            e.id
            for e in db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids))
        ]
        if element_ids:
            db.query(Quantity).filter(Quantity.element_id.in_(element_ids)).delete(
                synchronize_session=False
            )
        db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids)).delete(
            synchronize_session=False
        )
        db.query(Job).filter(Job.ifc_file_id.in_(ifc_file_ids)).delete(
            synchronize_session=False
        )
        db.query(IfcFile).filter(IfcFile.id.in_(ifc_file_ids)).delete(
            synchronize_session=False
        )
    # Jobs linked only via project_id (no ifc_file_id), e.g. the "missing file" test.
    db.query(Job).filter(Job.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def test_process_ifc_file_inserts_elements_and_updates_status() -> None:
    user, project = _create_user_and_project()
    db = SessionLocal()
    try:
        fixture_path = FIXTURES_DIR / "sample.ifc"
        storage_key = "tests/2.2/sample.ifc"
        with open(fixture_path, "rb") as fh:
            upload_fileobj(fh, storage_key)

        ifc_file = IfcFile(
            project_id=project.id,
            filename="sample.ifc",
            storage_key=storage_key,
            ifc_schema="IFC4",
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

        db.refresh(ifc_file)
        db.refresh(job)
        assert ifc_file.status == "extracted"
        assert job.status == "done"
        assert job.progress == 100

        elements = db.query(Element).filter(Element.ifc_file_id == ifc_file.id).all()
        assert len(elements) == 12
    finally:
        db.close()
        _cleanup(project.id, user.id)


def test_process_ifc_file_missing_ifc_file_returns_without_error() -> None:
    user, project = _create_user_and_project()
    db = SessionLocal()
    try:
        # ifc_file_id left null on the job row (it's nullable) - the nonexistent id is
        # passed directly to the function, not through the job's FK (which would reject it).
        job = Job(type="extract", project_id=project.id)
        db.add(job)
        db.commit()

        process_ifc_file(job.id, 999999999)  # should return early, not raise

        db.refresh(job)
        assert job.status == "queued"  # untouched - function returned before any update
    finally:
        db.close()
        _cleanup(project.id, user.id)
