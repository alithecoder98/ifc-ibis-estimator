"""Sub-phase 2.4: geometry fallback.

test_* functions exercise app/ifc/geometry.py directly (no DB/network) and validate
the ±3% accuracy bar against both fixtures. test_process_ifc_file_* drives the real
worker, confirming geometry fallback only fires when Qto is actually absent.
"""

from pathlib import Path

import ifcopenshell
import pytest

from app.db.models import Element, IfcFile, Job, Project, Quantity, User
from app.db.session import SessionLocal
from app.ifc.geometry import compute_geometry_quantities
from app.ifc.quantities import extract_quantities
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_ifc():
    return ifcopenshell.open(str(FIXTURES_DIR / "sample.ifc"))


def test_wall_geometry_matches_its_own_qto_exactly(sample_ifc) -> None:
    # The fixture's wall is a plain 5m x 3m x 0.2m box with no opening - geometry and
    # Qto should agree exactly, not just within tolerance.
    wall = sample_ifc.by_type("IfcWall")[0]
    quantities = {
        q["quantity_type"]: q["value"] for q in compute_geometry_quantities(wall)
    }

    assert quantities["volume_net"] == pytest.approx(3.0)
    assert quantities["volume_gross"] == pytest.approx(3.0)
    assert quantities["length"] == pytest.approx(5.0)


def test_footing_opening_is_correctly_subtracted(sample_ifc) -> None:
    # 7m x 1m x 0.4m box (gross 2.8 m3) with a through-opening removing exactly 0.3 m3
    # -> net 2.5 m3. Matches the fixture's own hardcoded Qto values exactly.
    footing = sample_ifc.by_type("IfcFooting")[0]
    quantities = {
        q["quantity_type"]: q["value"] for q in compute_geometry_quantities(footing)
    }

    assert quantities["volume_gross"] == pytest.approx(2.8)
    assert quantities["volume_net"] == pytest.approx(2.5)


def test_column_has_geometry_but_no_qto(sample_ifc) -> None:
    # Deliberately has no Qto in the fixture - this is the element the worker's
    # fallback trigger is tested against.
    column = sample_ifc.by_type("IfcColumn")[0]
    assert extract_quantities(sample_ifc, column) == []

    geometry_quantities = compute_geometry_quantities(column)
    assert {q["quantity_type"] for q in geometry_quantities} == {
        "volume_net",
        "volume_gross",
        "area_gross",
        "length",
    }
    assert all(q["source"] == "geometry" for q in geometry_quantities)
    # 0.3 x 3.0 x 0.3 box, no opening -> net == gross.
    by_type = {q["quantity_type"]: q["value"] for q in geometry_quantities}
    assert by_type["volume_net"] == pytest.approx(0.27)
    assert by_type["volume_gross"] == pytest.approx(0.27)


def test_element_with_no_representation_returns_empty_list(sample_ifc) -> None:
    # The beam has no geometric representation at all in this fixture.
    beam = sample_ifc.by_type("IfcBeam")[0]
    assert compute_geometry_quantities(beam) == []


def test_real_sample_geometry_volume_within_3_percent_of_qto() -> None:
    f = ifcopenshell.open(str(FIXTURES_DIR / "real_sample.ifc"))
    compared = 0
    for element in f.by_type("IfcWall") + f.by_type("IfcSlab"):
        qto = {q["quantity_type"]: q["value"] for q in extract_quantities(f, element)}
        geo = {
            q["quantity_type"]: q["value"] for q in compute_geometry_quantities(element)
        }
        if "volume_net" not in qto or "volume_net" not in geo:
            continue
        compared += 1
        deviation = abs(geo["volume_net"] - qto["volume_net"]) / qto["volume_net"]
        assert deviation <= 0.03, f"{element.Name}: {deviation:.2%} deviation"
    assert compared == 7  # 4 walls + 3 slabs, all of which have both Qto and geometry


def _create_user_and_project() -> tuple[User, Project]:
    db = SessionLocal()
    user = User(email="estimator-2.4@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Geometry Test Project", created_by=user.id)
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


def test_process_ifc_file_uses_geometry_only_when_qto_is_absent() -> None:
    user, project = _create_user_and_project()
    db = SessionLocal()
    try:
        fixture_path = FIXTURES_DIR / "sample.ifc"
        storage_key = "tests/2.4/sample.ifc"
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
        wall_sources = {
            q.source
            for q in db.query(Quantity).filter(Quantity.element_id == wall_element.id)
        }
        assert wall_sources == {"qto"}

        column_element = (
            db.query(Element)
            .filter(
                Element.ifc_file_id == ifc_file.id, Element.ifc_class == "IfcColumn"
            )
            .one()
        )
        column_quantities = (
            db.query(Quantity).filter(Quantity.element_id == column_element.id).all()
        )
        assert {q.source for q in column_quantities} == {"geometry"}
        assert {q.quantity_type for q in column_quantities} == {
            "volume_net",
            "volume_gross",
            "area_gross",
            "length",
        }

        # Beam has no Qto and no geometry in the fixture - no quantity rows at all,
        # not an error.
        beam_element = (
            db.query(Element)
            .filter(Element.ifc_file_id == ifc_file.id, Element.ifc_class == "IfcBeam")
            .one()
        )
        assert (
            db.query(Quantity).filter(Quantity.element_id == beam_element.id).count()
            == 0
        )
    finally:
        db.close()
        _cleanup(project.id, user.id)
