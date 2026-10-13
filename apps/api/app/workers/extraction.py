"""IFC processing job, triggered after a successful upload.

Downloads the file from storage, extracts building elements (Phase 2.2) and their
quantities, and inserts both into the DB in batches. Quantities come from Qto sets
(Phase 2.3) where present; geometry (Phase 2.4, ifcopenshell.geom — the only step that
touches geometry, so it's the only one with any real memory/CPU cost) fills in only
for elements with no Qto data at all, never overriding real Qto data. Each element also
gets a profile_text and group_hash (Phase 2.5) once its quantities are known, then a
jev-based classification (Phase P.2, one jev call per group), and finally a That Open
fragments conversion for the not-yet-built 3D viewer (Phase 2.6).
"""

import tempfile
from pathlib import Path

import ifcopenshell

from app.ai.classify import classify_elements
from app.db.models import Element, IfcFile, Job, Quantity
from app.db.session import SessionLocal
from app.ifc.extract import build_element_data, iter_supported_elements
from app.ifc.fragments import convert_to_fragments
from app.ifc.geometry import compute_geometry_quantities
from app.ifc.profile import build_profile_text, compute_group_hash
from app.ifc.quantities import extract_quantities
from app.storage import download_to_path, upload_bytes

BATCH_SIZE = 500


def process_ifc_file(job_id: int, ifc_file_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        ifc_file = db.get(IfcFile, ifc_file_id)
        if job is None or ifc_file is None:
            return

        job.status = "running"
        ifc_file.status = "extracting"
        db.commit()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "input.ifc"
            download_to_path(ifc_file.storage_key, tmp_path)
            opened = ifcopenshell.open(str(tmp_path))
            fragments_bytes, local_id_by_global_id = convert_to_fragments(tmp_path)

            raw_elements = list(iter_supported_elements(opened))
            elements_data = [build_element_data(e) for e in raw_elements]
            quantities_by_global_id = {}
            for e in raw_elements:
                qto_quantities = extract_quantities(opened, e)
                quantities_by_global_id[e.GlobalId] = (
                    qto_quantities if qto_quantities else compute_geometry_quantities(e)
                )

            for data in elements_data:
                quantities = quantities_by_global_id[data["global_id"]]
                data["profile_text"] = build_profile_text(data, quantities)
                data["group_hash"] = compute_group_hash(data)

        total = len(elements_data)
        all_orm_elements: list[Element] = []
        for start in range(0, total, BATCH_SIZE):
            batch = elements_data[start : start + BATCH_SIZE]
            orm_elements = [Element(ifc_file_id=ifc_file_id, **data) for data in batch]
            db.add_all(orm_elements)
            db.flush()  # assigns .id to each, needed for the Quantity rows below
            all_orm_elements.extend(orm_elements)

            for orm_element, data in zip(orm_elements, batch, strict=True):
                quantities = quantities_by_global_id.get(data["global_id"], [])
                db.add_all(Quantity(element_id=orm_element.id, **q) for q in quantities)

            db.flush()
            # Extraction is 80% of the job; classification and fragments conversion
            # share the last 20%.
            job.progress = (
                int(min(start + len(batch), total) / total * 80) if total else 80
            )
            db.commit()

        # Classification is the next 10% (80-90%); fragments upload is the last 10%.
        def _report_classify_progress(processed: int, classify_total: int) -> None:
            job.progress = 80 + int(
                processed / classify_total * 10 if classify_total else 10
            )
            db.commit()

        classify_elements(
            db, all_orm_elements, progress_callback=_report_classify_progress
        )
        job.progress = 90
        db.commit()

        fragments_key = f"projects/{ifc_file.project_id}/fragments/{ifc_file_id}.frag"
        upload_bytes(fragments_bytes, fragments_key)
        ifc_file.fragments_storage_key = fragments_key
        ifc_file.fragment_id_map = local_id_by_global_id

        ifc_file.status = "extracted"
        job.status = "done"
        job.progress = 100
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(Job, job_id)
        ifc_file = db.get(IfcFile, ifc_file_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)
        if ifc_file is not None:
            ifc_file.status = "failed"
        db.commit()
        raise
    finally:
        db.close()
