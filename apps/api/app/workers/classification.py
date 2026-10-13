"""Phase 3.7: re-runs classification for an already-extracted file, triggered by
POST /projects/{project_id}/files/{file_id}/classify - e.g. after an admin adds new
rules or code_list entries and wants existing elements re-evaluated against them.
Does not touch extraction, quantities, or the fragments conversion - those are
app/workers/extraction.py's job and are assumed to already be done.
"""

from app.ai.classify import classify_elements
from app.db.models import Element, IfcFile, Job
from app.db.session import SessionLocal


def reclassify_ifc_file(job_id: int, ifc_file_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        ifc_file = db.get(IfcFile, ifc_file_id)
        if job is None or ifc_file is None:
            return

        job.status = "running"
        db.commit()

        elements = db.query(Element).filter(Element.ifc_file_id == ifc_file_id).all()

        def _report(processed: int, classify_total: int) -> None:
            job.progress = (
                int(processed / classify_total * 100) if classify_total else 100
            )
            db.commit()

        # force=True: the whole point of this endpoint is to re-evaluate elements
        # that already have a classification, unlike the normal upload path.
        classify_elements(db, elements, force=True, progress_callback=_report)

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
