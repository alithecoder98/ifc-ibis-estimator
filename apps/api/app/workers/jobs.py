"""DB-side bookkeeping for the `jobs` table.

Creating a job row happens on the API's own DB session, before enqueueing. Progress/
status updates while a job *runs* happen inside the job function itself (see
app/workers/demo.py) — that runs in a separate worker process with its own session, so
it can't share the request's `db`.
"""

from sqlalchemy.orm import Session

from app.db.models import Job


def create_job(
    db: Session,
    *,
    type: str,
    project_id: int | None = None,
    ifc_file_id: int | None = None,
) -> Job:
    job = Job(type=type, project_id=project_id, ifc_file_id=ifc_file_id)
    db.add(job)
    db.flush()
    return job
