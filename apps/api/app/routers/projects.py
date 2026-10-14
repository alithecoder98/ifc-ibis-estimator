"""Projects CRUD and IFC file upload.

Upload flow: simple server-proxied multipart upload (client -> FastAPI -> Garage), not
a presigned-URL direct-to-storage flow — there's no upload UI yet to pair that with
(Phase 4.2), and this is simpler to build/test in one sub-phase. Revisit if large files
prove slow routing through the API server.
"""

import tempfile
import uuid
from pathlib import Path

import ifcopenshell
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.ai.export import build_export_csv
from app.core.deps import require_role
from app.db.models import (
    Classification,
    Element,
    IfcFile,
    Job,
    Project,
    Quantity,
    User,
)
from app.db.session import get_db
from app.schemas import IfcFileOut, ProjectCreate, ProjectOut, ProjectUpdate
from app.storage import download_bytes, upload_fileobj
from app.workers.classification import reclassify_ifc_file
from app.workers.extraction import process_ifc_file
from app.workers.jobs import create_job
from app.workers.queue import get_queue

router = APIRouter(prefix="/projects", tags=["projects"])

ALLOWED_IFC_EXTENSIONS = {".ifc", ".ifczip", ".ifcxml"}


def _ifc_file_out(db: Session, ifc_file: IfcFile) -> IfcFileOut:
    latest_job = (
        db.query(Job)
        .filter(Job.ifc_file_id == ifc_file.id)
        .order_by(Job.created_at.desc())
        .first()
    )
    return IfcFileOut.model_validate(ifc_file).model_copy(
        update={"job_id": latest_job.id if latest_job else None}
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> Project:
    project = Project(name=body.name, created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> list[Project]:
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> Project:
    """Renaming (Phase 4.1) and changing classification_engine (Phase 3.5) share
    one endpoint - both are normal actions for whoever's running this project, not
    an admin-only concern, and this app has no multi-tenant/adversarial model to
    defend against (single client, their own estimators - see CLAUDE.md's
    non-goals), so there's no real reason to split permissions per field.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


@router.post(
    "/{project_id}/files",
    response_model=IfcFileOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_ifc_file(
    project_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> IfcFile:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IFC_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"unsupported file type '{suffix}' - expected one of "
                f"{sorted(ALLOWED_IFC_EXTENSIONS)}"
            ),
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := file.file.read(1024 * 1024):
            tmp.write(chunk)

    try:
        try:
            ifc = ifcopenshell.open(str(tmp_path))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="file could not be parsed as a valid IFC file",
            ) from exc

        size_bytes = tmp_path.stat().st_size
        storage_key = f"projects/{project_id}/{uuid.uuid4()}{suffix}"

        with open(tmp_path, "rb") as fh:
            upload_fileobj(fh, storage_key)

        ifc_file = IfcFile(
            project_id=project_id,
            filename=file.filename,
            storage_key=storage_key,
            ifc_schema=ifc.schema,
            size_bytes=size_bytes,
            uploaded_by=user.id,
            status="uploaded",
        )
        db.add(ifc_file)
        db.flush()

        job = create_job(
            db, type="extract", project_id=project_id, ifc_file_id=ifc_file.id
        )
        db.commit()
        db.refresh(ifc_file)

        get_queue().enqueue(process_ifc_file, job.id, ifc_file.id)

        # job.id is already known here - skip _ifc_file_out()'s extra query.
        return IfcFileOut.model_validate(ifc_file).model_copy(update={"job_id": job.id})
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/{project_id}/files", response_model=list[IfcFileOut])
def list_files(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> list[IfcFileOut]:
    """Phase 4.1 - the frontend has had no way to see a project's uploaded
    file(s)/their status at all until now (POST creates one, but nothing listed
    it back). project.status itself is never updated by the pipeline (still
    always "draft") - real per-upload progress lives on IfcFile.status, which is
    what this exposes. job_id (Phase 4.2) lets the frontend poll a still-running
    upload's real progress via GET /jobs/{id}.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )
    ifc_files = (
        db.query(IfcFile)
        .filter(IfcFile.project_id == project_id)
        .order_by(IfcFile.uploaded_at.desc())
        .all()
    )
    return [_ifc_file_out(db, f) for f in ifc_files]


@router.get("/{project_id}/export")
def export_project_csv(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> Response:
    """Phase P.3 — the minimal results output: every element in the project, its
    quantities, and its jev classification (if any), as a downloadable CSV.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )

    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    elements = (
        db.query(Element)
        .filter(Element.ifc_file_id.in_(ifc_file_ids))
        .order_by(Element.id)
        .all()
        if ifc_file_ids
        else []
    )

    rows = []
    for element in elements:
        quantities = db.query(Quantity).filter(Quantity.element_id == element.id).all()
        classification = (
            db.query(Classification)
            .filter(Classification.element_id == element.id)
            .order_by(Classification.created_at.desc())
            .first()
        )
        rows.append((element, quantities, classification))

    csv_text = build_export_csv(rows)
    filename = f"project-{project_id}-export.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/files/{file_id}/model")
def get_fragments_model(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> Response:
    """Phase 2.6 — the converted That Open fragments file for the (not-yet-built) 3D
    viewer. 404 until the file's processing job has reached the fragments step.
    """
    ifc_file = db.get(IfcFile, file_id)
    if ifc_file is None or ifc_file.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="file not found"
        )
    if ifc_file.fragments_storage_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="fragments model not available yet",
        )

    fragments_bytes = download_bytes(ifc_file.fragments_storage_key)
    return Response(content=fragments_bytes, media_type="application/octet-stream")


@router.post(
    "/{project_id}/files/{file_id}/classify", status_code=status.HTTP_202_ACCEPTED
)
def classify_file(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> dict:
    """Phase 3.7 — re-runs classification for an already-extracted file, e.g. after
    adding rules or code_list entries. Re-evaluates every element (force=True in
    app/workers/classification.py), not just ones missing a classification -
    "latest classification wins" is already the project's convention, so this adds
    fresher rows rather than deleting the old ones.
    """
    ifc_file = db.get(IfcFile, file_id)
    if ifc_file is None or ifc_file.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="file not found"
        )
    if ifc_file.status != "extracted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"file must be fully extracted before classifying (status: {ifc_file.status})",
        )

    job = create_job(db, type="classify", project_id=project_id, ifc_file_id=file_id)
    db.commit()

    get_queue().enqueue(reclassify_ifc_file, job.id, file_id)

    return {"id": job.id}
