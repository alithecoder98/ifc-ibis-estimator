"""GET /jobs/{id} — poll job progress. POST /jobs/demo — enqueue the demo job (manual
testing / proving the worker is wired up; real jobs get their own trigger endpoints in
later phases, e.g. upload triggering extraction).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.db.models import Job, User
from app.db.session import get_db
from app.schemas import JobOut
from app.workers.demo import run_demo_job
from app.workers.jobs import create_job
from app.workers.queue import get_queue

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> Job:
    """Had no auth check at all until Phase 4.2 - any request, authenticated or
    not, could poll any job's progress/error. Matches the same role bar as every
    other read endpoint; true per-project authorization isn't a concept this app
    has anywhere else either (any estimator can already list every project via
    GET /projects), so this doesn't invent one just for jobs.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/demo")
def create_demo_job(db: Session = Depends(get_db)) -> dict:
    job = create_job(db, type="demo")
    db.commit()
    get_queue().enqueue(run_demo_job, job.id)
    return {"id": job.id}
