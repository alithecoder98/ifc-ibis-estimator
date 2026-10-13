"""Sub-phase 2.5: element profiles + grouping.

test_build_profile_text_* and test_compute_group_hash_* exercise app/ifc/profile.py
directly (no DB/network). test_process_ifc_file_* drives the real worker, confirming
both columns actually get populated end to end.
"""

from pathlib import Path

import ifcopenshell

from app.db.models import Element, IfcFile, Job, Project, User
from app.db.session import SessionLocal
from app.ifc.extract import extract_elements
from app.ifc.profile import build_profile_text, compute_group_hash
from app.ifc.quantities import extract_quantities
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file
from tests.conftest import cleanup_project_cascade

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _wall_data_and_quantities():
    f = ifcopenshell.open(str(FIXTURES_DIR / "sample.ifc"))
    wall_raw = f.by_type("IfcWall")[0]
    wall_data = next(
        e for e in extract_elements(f) if e["global_id"] == wall_raw.GlobalId
    )
    quantities = extract_quantities(f, wall_raw)
    return wall_data, quantities


def test_build_profile_text_exact_snapshot() -> None:
    wall_data, quantities = _wall_data_and_quantities()

    assert build_profile_text(wall_data, quantities) == (
        "Class: IfcWall (SOLIDWALL)\n"
        "Name: Exterior Wall 01\n"
        "Materials: Concrete (200mm)\n"
        "Storey: Ground Floor\n"
        "External=True | LoadBearing=True\n"
        "Quantities: area_net=15.00m2, length=5.00m, volume_net=3.00m3\n"
        "Properties: FireRating=REI60"
    )


def test_build_profile_text_excludes_ifcopenshell_internal_id_key() -> None:
    # get_psets() always injects an "id" key (the pset entity's own STEP id, for
    # traceability) into every pset dict - it must never leak into the profile text
    # as if it were a real IFC property.
    wall_data, quantities = _wall_data_and_quantities()
    assert "id=" not in build_profile_text(wall_data, quantities)


def test_build_profile_text_is_deterministic() -> None:
    wall_data, quantities = _wall_data_and_quantities()
    first = build_profile_text(wall_data, quantities)
    second = build_profile_text(wall_data, quantities)
    assert first == second


def test_compute_group_hash_is_64_char_hex() -> None:
    wall_data, _ = _wall_data_and_quantities()
    group_hash = compute_group_hash(wall_data)
    assert len(group_hash) == 64
    assert all(c in "0123456789abcdef" for c in group_hash)


def test_compute_group_hash_ignores_instance_specific_fields() -> None:
    wall_data, _ = _wall_data_and_quantities()
    variant = dict(
        wall_data, global_id="DIFFERENT-ID", name="A Different Name", storey="Roof"
    )
    assert compute_group_hash(wall_data) == compute_group_hash(variant)


def test_compute_group_hash_differs_for_different_construction_types() -> None:
    wall_data, _ = _wall_data_and_quantities()
    different_material = dict(
        wall_data, materials=[{"material": "Timber", "thickness_mm": 100}]
    )
    assert compute_group_hash(wall_data) != compute_group_hash(different_material)


def test_grouping_reduces_element_count_on_real_sample() -> None:
    # 4 walls in real_sample.ifc: 3 share material+class+predefined_type, 1 doesn't -
    # grouping should reduce 4 elements down to 2 groups, not 4 or 1.
    f = ifcopenshell.open(str(FIXTURES_DIR / "real_sample.ifc"))
    walls = [e for e in extract_elements(f) if e["ifc_class"] == "IfcWall"]
    unique_groups = {compute_group_hash(w) for w in walls}

    assert len(walls) == 4
    assert len(unique_groups) == 2


def _create_user_and_project() -> tuple[User, Project]:
    db = SessionLocal()
    user = User(email="estimator-2.5@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Profile Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    db.close()
    return user, project


_cleanup = cleanup_project_cascade


def test_process_ifc_file_populates_profile_text_and_group_hash() -> None:
    user, project = _create_user_and_project()
    db = SessionLocal()
    try:
        fixture_path = FIXTURES_DIR / "sample.ifc"
        storage_key = "tests/2.5/sample.ifc"
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
        assert wall_element.profile_text is not None
        assert wall_element.profile_text.startswith("Class: IfcWall (SOLIDWALL)")
        assert wall_element.group_hash is not None
        assert len(wall_element.group_hash) == 64

        all_elements = (
            db.query(Element).filter(Element.ifc_file_id == ifc_file.id).all()
        )
        assert all(e.profile_text and e.group_hash for e in all_elements)
    finally:
        db.close()
        _cleanup(project.id, user.id)
