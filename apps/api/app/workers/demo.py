"""Demo job — proves the RQ worker + jobs table wiring end to end (sub-phase 1.4).

Real jobs (IFC extraction, classification, ...) follow the same shape in later phases:
open its own session (it runs in a separate worker process), mark running, update
progress as it goes, mark done/failed.
"""

import time

from app.db.models import Job
from app.db.session import SessionLocal


def run_demo_job(job_id: int, steps: int = 5, delay_seconds: float = 0.2) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return

        job.status = "running"
        db.commit()

        for step in range(1, steps + 1):
            time.sleep(delay_seconds)
            job.progress = int(step / steps * 100)
            db.commit()

        job.status = "done"
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
