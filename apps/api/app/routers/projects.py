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
from app.db.models import Classification, Element, IfcFile, Project, Quantity, User
from app.db.session import get_db
from app.schemas import IfcFileOut, ProjectCreate, ProjectOut
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file
from app.workers.jobs import create_job
from app.workers.queue import get_queue

router = APIRouter(prefix="/projects", tags=["projects"])

ALLOWED_IFC_EXTENSIONS = {".ifc", ".ifczip", ".ifcxml"}


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

        return ifc_file
    finally:
        tmp_path.unlink(missing_ok=True)


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
