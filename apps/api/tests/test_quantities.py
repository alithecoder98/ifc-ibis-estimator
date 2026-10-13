"""Sub-phase 2.3: quantities from Qto.

test_extract_quantities_* exercise app/ifc/quantities.py directly (no DB/network).
test_process_ifc_file_* drive the real worker end to end, confirming Quantity rows
land correctly linked to their Element rows.
"""

from pathlib import Path

import ifcopenshell
import pytest

from app.db.models import Element, IfcFile, Job, Project, Quantity, User
from app.db.session import SessionLocal
from app.ifc.quantities import extract_quantities
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_ifc():
    return ifcopenshell.open(str(FIXTURES_DIR / "sample.ifc"))


def test_wall_quantities_from_synthetic_fixture(sample_ifc) -> None:
    wall = sample_ifc.by_type("IfcWall")[0]
    quantities = {q["quantity_type"]: q for q in extract_quantities(sample_ifc, wall)}

    assert quantities["length"] == {
        "quantity_type": "length",
        "value": 5.0,
        "unit": "m",
        "source": "qto",
    }
    assert quantities["area_net"]["value"] == 15.0
    assert quantities["area_net"]["unit"] == "m2"
    assert quantities["volume_net"]["value"] == 3.0
    assert quantities["volume_net"]["unit"] == "m3"
    # Height isn't one of our canonical quantity_types - shouldn't appear at all.
    assert "height" not in quantities


def test_slab_quantities_from_synthetic_fixture(sample_ifc) -> None:
    slab = sample_ifc.by_type("IfcSlab")[0]
    quantities = {
        q["quantity_type"]: q["value"] for q in extract_quantities(sample_ifc, slab)
    }

    assert quantities == {"area_net": 40.0, "area_gross": 42.0, "volume_net": 10.0}


def test_footing_quantities_from_synthetic_fixture(sample_ifc) -> None:
    footing = sample_ifc.by_type("IfcFooting")[0]
    quantities = {
        q["quantity_type"]: q["value"] for q in extract_quantities(sample_ifc, footing)
    }

    assert quantities == {"volume_net": 2.5, "volume_gross": 2.8}


def test_element_with_no_qto_returns_empty_list(sample_ifc) -> None:
    # IfcColumn in the synthetic fixture has no Qto set at all.
    column = sample_ifc.by_type("IfcColumn")[0]
    assert extract_quantities(sample_ifc, column) == []


def test_real_sample_wall_quantities_convert_to_plausible_si_values() -> None:
    # real_sample.ifc declares millimetre length but plain square/cubic-metre area and
    # volume units independently (not derived from the length unit) - this is the
    # real-world quirk that motivated computing each unit type's scale separately
    # rather than assuming area = length_scale**2.
    f = ifcopenshell.open(str(FIXTURES_DIR / "real_sample.ifc"))
    wall = f.by_type("IfcWall")[0]
    quantities = {q["quantity_type"]: q["value"] for q in extract_quantities(f, wall)}

    # A real house wall: length in single-digit metres, not thousands (which is what
    # you'd get if the millimetre length scale were wrongly applied to area/volume).
    assert 0.5 < quantities["length"] < 20
    assert 1 < quantities["area_net"] < 50
    assert 0.05 < quantities["volume_net"] < 10


def _create_user_and_project() -> tuple[User, Project]:
    db = SessionLocal()
    user = User(email="estimator-2.3@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Quantities Test Project", created_by=user.id)
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
    db.query(Job).filter(Job.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project_id).delete()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def test_process_ifc_file_inserts_quantities_linked_to_elements() -> None:
    user, project = _create_user_and_project()
    db = SessionLocal()
    try:
        fixture_path = FIXTURES_DIR / "sample.ifc"
        storage_key = "tests/2.3/sample.ifc"
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

        wall_element = (
            db.query(Element)
            .filter(Element.ifc_file_id == ifc_file.id, Element.ifc_class == "IfcWall")
            .one()
        )
        wall_quantities = {
            q.quantity_type: float(q.value)
            for q in db.query(Quantity).filter(Quantity.element_id == wall_element.id)
        }
        assert wall_quantities == {"length": 5.0, "area_net": 15.0, "volume_net": 3.0}

        # Column has no Qto in the fixture - element exists, no quantity rows for it.
        column_element = (
            db.query(Element)
            .filter(
                Element.ifc_file_id == ifc_file.id, Element.ifc_class == "IfcColumn"
            )
            .one()
        )
        assert (
            db.query(Quantity).filter(Quantity.element_id == column_element.id).count()
            == 0
        )
    finally:
        db.close()
        _cleanup(project.id, user.id)
