"""GET /jobs/{id} — poll job progress. POST /jobs/demo — enqueue the demo job (manual
testing / proving the worker is wired up; real jobs get their own trigger endpoints in
later phases, e.g. upload triggering extraction).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Job
from app.db.session import get_db
from app.workers.demo import run_demo_job
from app.workers.jobs import create_job
from app.workers.queue import get_queue

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
    }


@router.post("/demo")
def create_demo_job(db: Session = Depends(get_db)) -> dict:
    job = create_job(db, type="demo")
    db.commit()
    get_queue().enqueue(run_demo_job, job.id)
    return {"id": job.id}
