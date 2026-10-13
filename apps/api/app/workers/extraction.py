"""IFC processing job, triggered after a successful upload.

Downloads the file from storage, extracts building elements (Phase 2.2), and inserts
them into the `elements` table in batches. Geometry is never touched here — keeps this
fast and low-memory regardless of file size; Qto-based quantities are 2.3's job,
geometry-computed quantities are 2.4's, profile_text/group_hash are 2.5's.
"""

import tempfile
from pathlib import Path

import ifcopenshell

from app.db.models import Element, IfcFile, Job
from app.db.session import SessionLocal
from app.ifc.extract import extract_elements
from app.storage import download_to_path

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
            elements = list(extract_elements(opened))

        total = len(elements)
        for start in range(0, total, BATCH_SIZE):
            batch = elements[start : start + BATCH_SIZE]
            db.add_all(Element(ifc_file_id=ifc_file_id, **data) for data in batch)
            db.flush()
            job.progress = (
                int(min(start + len(batch), total) / total * 100) if total else 100
            )
            db.commit()

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
