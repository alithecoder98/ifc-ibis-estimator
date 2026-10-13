"""IFC processing job, triggered after a successful upload.

Currently a stub — it just marks the job done. Real element/quantity extraction
(ifcopenshell parsing) is built in Phase 2.2 and will replace the body of this
function; the job-row lifecycle (queued -> running -> done/failed) it sits in is
already real and already wired end to end from the upload endpoint.
"""

from app.db.models import IfcFile, Job
from app.db.session import SessionLocal


def process_ifc_file(job_id: int, ifc_file_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        ifc_file = db.get(IfcFile, ifc_file_id)
        if job is None or ifc_file is None:
            return

        job.status = "running"
        db.commit()

        # Phase 2.2 replaces this line with real element/quantity extraction.
        ifc_file.status = "uploaded"

        job.status = "done"
        job.progress = 100
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)
            db.commit()
        raise
    finally:
        db.close()
