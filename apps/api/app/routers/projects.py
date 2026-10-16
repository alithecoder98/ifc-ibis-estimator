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

from app.ai.composite_split import AlreadySplitError, NotCompositeError, split_element
from app.ai.element_detail import get_element_detail
from app.ai.elements import ElementRow, list_element_rows
from app.ai.embedder import get_embedder
from app.ai.excel_export import build_export_xlsx
from app.ai.export import build_export_csv
from app.ai.reviews import ReviewError, approve_element, correct_element, undo_review
from app.ai.summary import compute_summary, latest_classifications_by_element
from app.core.deps import require_role
from app.db.models import (
    Classification,
    Element,
    IfcFile,
    Job,
    Project,
    Quantity,
    Review,
    User,
)
from app.db.session import get_db
from app.schemas import (
    ElementDetailOut,
    ElementRowOut,
    IfcFileOut,
    JobIdOut,
    ProjectCreate,
    ProjectOut,
    ProjectSummaryOut,
    ProjectUpdate,
    ReviewActionOut,
    ReviewCreate,
    ReviewOut,
    SplitElementOut,
)
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

        # RQ's default job_timeout is 180s - confirmed live against real IFC
        # files that a file with many element groups (one LLM classification
        # call per group) blows well past that during classify, hard-killing
        # an otherwise-succeeding job ("Task exceeded maximum timeout value
        # (180 seconds)"). 1200s gives real headroom over the MVP's own
        # stated "100MB model processes in <10 min" target rather than
        # cutting it off at under half that.
        get_queue().enqueue(process_ifc_file, job.id, ifc_file.id, job_timeout=1200)

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


@router.get("/{project_id}/summary", response_model=ProjectSummaryOut)
def get_project_summary(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> ProjectSummaryOut:
    """Phase 4.3 - the Overview tab's stat cards, totals-per-code table, and
    warnings panel. `corrected` is always 0 today - no review/correction
    endpoint exists yet (Phase 6.1); an honest zero, not thin test data.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )
    summary = compute_summary(db, project_id)
    return ProjectSummaryOut(
        total_elements=summary.total_elements,
        auto_accepted=summary.auto_accepted,
        needs_review=summary.needs_review,
        corrected=summary.corrected,
        warnings={
            "missing_quantity": summary.missing_quantity_count,
            "proxy_element": summary.proxy_element_count,
            "unmapped": summary.unmapped_count,
        },
        totals_by_code=[
            {
                "ibis_code": t.ibis_code,
                "internal_element": t.internal_element,
                "unit": t.unit,
                "quantity": t.quantity,
                "element_count": t.element_count,
            }
            for t in summary.totals_by_code
        ],
    )


@router.get("/{project_id}/elements", response_model=list[ElementRowOut])
def list_elements(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> list[ElementRow]:
    """Phase 4.4 - the Elements tab's full row set. Returns everything in one
    response; filtering/sorting/grouping/search all happen client-side against
    this list (see CLAUDE.md's 4.4 entry for why - virtualisation, not server
    paging, is what actually solves the rendering-performance problem at
    realistic JSON sizes).
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )
    return list_element_rows(db, project_id)


@router.get("/{project_id}/elements/{element_id}", response_model=ElementDetailOut)
def get_element(
    project_id: int,
    element_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> ElementDetailOut:
    """Phase 4.5 - the side panel on row click: properties, material layers,
    quantities with source, AI reasoning, candidate codes with real
    cosine-similarity scores, similar past examples, review history. Candidates/
    examples are recomputed fresh against this element's current profile (see
    app/ai/element_detail.py's module docstring for why) - this always calls the
    real embedder, regardless of the project's classification_engine setting.
    """
    detail = get_element_detail(db, element_id, get_embedder(db))
    ifc_file = (
        db.get(IfcFile, detail.element.ifc_file_id) if detail is not None else None
    )
    if detail is None or ifc_file is None or ifc_file.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="element not found"
        )

    return ElementDetailOut(
        id=detail.element.id,
        global_id=detail.element.global_id,
        name=detail.element.name,
        ifc_class=detail.element.ifc_class,
        predefined_type=detail.element.predefined_type,
        object_type=detail.element.object_type,
        storey=detail.element.storey,
        is_external=detail.element.is_external,
        load_bearing=detail.element.load_bearing,
        psets=detail.element.psets,
        materials=detail.element.materials,
        quantities=detail.quantities,
        classification=detail.classification,
        candidates=detail.candidates,
        similar_examples=detail.similar_examples,
        reviews=detail.reviews,
        split_child_ids=detail.split_child_ids,
    )


@router.post(
    "/{project_id}/elements/{element_id}/split",
    response_model=SplitElementOut,
    status_code=status.HTTP_201_CREATED,
)
def split_element_endpoint(
    project_id: int,
    element_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> SplitElementOut:
    """Phase 6.2 - splits a composite element (e.g. a multi-layer wall) into
    one real Element row per material layer. See app/ai/composite_split.py
    for the quantity-splitting and double-counting-avoidance details.
    """
    element = db.get(Element, element_id)
    ifc_file = db.get(IfcFile, element.ifc_file_id) if element is not None else None
    if element is None or ifc_file is None or ifc_file.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="element not found"
        )

    try:
        children = split_element(db, element_id)
    except NotCompositeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except AlreadySplitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    db.commit()
    return SplitElementOut(child_element_ids=[c.id for c in children])


def _export_rows(
    db: Session, project_id: int
) -> list[tuple[Element, list[Quantity], Classification | None]]:
    """Shared by both export formats (CSV, Phase P.3; the .xlsx export below -
    a partial first step toward Phase 7.1, see app/ai/excel_export.py's
    module docstring) so the split-parent exclusion (Phase 6.2 - a split
    element's own quantity would otherwise double-count against its new
    children's) only lives in one place.
    """
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    split_parent_ids = (
        {
            row[0]
            for row in db.query(Element.parent_element_id)
            .filter(Element.parent_element_id.isnot(None))
            .distinct()
        }
        if ifc_file_ids
        else set()
    )
    elements = (
        db.query(Element)
        .filter(
            Element.ifc_file_id.in_(ifc_file_ids),
            Element.id.notin_(split_parent_ids) if split_parent_ids else True,
        )
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
    return rows


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

    csv_text = build_export_csv(_export_rows(db, project_id))
    filename = f"project-{project_id}-export.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/export.xlsx")
def export_project_excel(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> Response:
    """A partial first step toward Phase 7.1 (not Phase 6.6, which is "Audit
    trail" - a different, unbuilt feature - see app/ai/excel_export.py's
    module docstring for the full correction). Same data as the CSV export,
    as a real .xlsx workbook (frozen header, column widths, autofilter). Not
    the client's real IBIS import format or 7.1's full three-sheet spec -
    just a genuinely Excel-shaped single sheet to open today, swappable
    later without touching how rows are queried (see _export_rows above).
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )

    xlsx_bytes = build_export_xlsx(_export_rows(db, project_id))
    filename = f"project-{project_id}-export.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/files/{file_id}/model")
def get_fragments_model(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> Response:
    """Phase 2.6 — the converted That Open fragments file for the Phase 5.1
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


@router.get("/{project_id}/files/{file_id}/fragment-ids", response_model=dict[str, int])
def get_fragment_id_map(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> dict[str, int]:
    """Phase 5.1 — {global_id: local_id} for the fragments model above, kept as
    its own route rather than folded into IfcFileOut/the model response: it can
    be a large payload for big models and nothing needs it except the viewer
    actually being open (storey filter / isolate need it to map an element to
    its fragment; 5.2's table<->viewer click sync will reuse this same route).
    """
    ifc_file = db.get(IfcFile, file_id)
    if ifc_file is None or ifc_file.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="file not found"
        )
    if ifc_file.fragment_id_map is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="fragment id map not available yet",
        )
    return ifc_file.fragment_id_map


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

    # Same job_timeout reasoning as the extract enqueue above - reclassify
    # hits the same per-group LLM classification step.
    get_queue().enqueue(reclassify_ifc_file, job.id, file_id, job_timeout=1200)

    return {"id": job.id}


@router.post(
    "/{project_id}/files/{file_id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobIdOut,
)
def reprocess_file(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> JobIdOut:
    """Retries the full extract -> classify -> fragments pipeline for a file
    whose original job never finished. Found live: a file's upload-time job can
    be lost from the Redis queue (e.g. a Redis restart) while the file's own
    status row stays "uploaded" forever, with nothing in the UI to recover -
    the frontend's only trigger for this pipeline was the one-shot enqueue at
    upload time. Restricted to "uploaded"/"failed" - extraction isn't additive-
    safe (a re-run on an already-"extracted" file would insert a second set of
    duplicate Element rows), unlike /classify's append-only re-evaluation.
    """
    ifc_file = db.get(IfcFile, file_id)
    if ifc_file is None or ifc_file.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="file not found"
        )
    if ifc_file.status not in ("uploaded", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"file can't be reprocessed from status: {ifc_file.status}",
        )

    job = create_job(db, type="extract", project_id=project_id, ifc_file_id=file_id)
    db.commit()

    # Same job_timeout reasoning as the original upload-time enqueue above.
    get_queue().enqueue(process_ifc_file, job.id, file_id, job_timeout=1200)

    return JobIdOut(id=job.id)


def _get_project_element(
    db: Session, project_id: int, element_id: int
) -> Element | None:
    element = db.get(Element, element_id)
    if element is None:
        return None
    ifc_file = db.get(IfcFile, element.ifc_file_id)
    if ifc_file is None or ifc_file.project_id != project_id:
        return None
    return element


def _apply_review(
    db: Session, element: Element, body: ReviewCreate, user: User
) -> ReviewActionOut:
    current = latest_classifications_by_element(db, [element.id]).get(element.id)
    try:
        if body.action == "approve":
            result = approve_element(db, element, current, user, body.comment)
        else:
            if body.ibis_code is None:
                raise ReviewError("ibis_code is required for a correction")
            result = correct_element(
                db, element, current, body.ibis_code, user, body.comment
            )
    except ReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    # Review has no user_email column (and no ORM relationships exist anywhere
    # in this codebase to derive one) - every action here is the authenticated
    # user's own, so their already-loaded email is used directly rather than a
    # second query.
    return ReviewActionOut(
        classification=result.classification,
        review=ReviewOut(
            id=result.review.id,
            action=result.review.action,
            comment=result.review.comment,
            created_at=result.review.created_at,
            user_email=user.email,
        ),
    )


@router.post(
    "/{project_id}/elements/{element_id}/reviews",
    response_model=ReviewActionOut,
    status_code=status.HTTP_201_CREATED,
)
def review_element(
    project_id: int,
    element_id: int,
    body: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> ReviewActionOut:
    """Phase 6.1 - approve the current suggestion or correct it to a different
    code. Writes a fresh Classification row (never mutates the old one - see
    app/ai/reviews.py) plus a Review row logging the action.
    """
    element = _get_project_element(db, project_id, element_id)
    if element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="element not found"
        )
    result = _apply_review(db, element, body, user)
    db.commit()
    return result


@router.post(
    "/{project_id}/groups/{group_hash}/reviews",
    response_model=list[ReviewActionOut],
    status_code=status.HTTP_201_CREATED,
)
def review_group(
    project_id: int,
    group_hash: str,
    body: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> list[ReviewActionOut]:
    """Phase 6.1 bulk action - same approve/correct body applied to every
    element sharing this group_hash in the project (the same grouping concept
    jev/LLM/rules already batch by - see app/ai/classify.py).
    """
    elements = (
        db.query(Element)
        .join(IfcFile, IfcFile.id == Element.ifc_file_id)
        .filter(IfcFile.project_id == project_id, Element.group_hash == group_hash)
        .all()
    )
    if not elements:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="group not found"
        )

    results = [_apply_review(db, element, body, user) for element in elements]
    db.commit()
    return results


@router.post("/{project_id}/reviews/{review_id}/undo", response_model=ReviewActionOut)
def undo_review_action(
    project_id: int,
    review_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator")),
) -> ReviewActionOut:
    """Phase 6.1 - restores the classification to what it was before the given
    review (its `before` snapshot), as a fresh Classification row, plus a new
    Review row (action="undo") logging the undo. Nothing is deleted.
    """
    review = db.get(Review, review_id)
    classification = (
        db.get(Classification, review.classification_id) if review is not None else None
    )
    element = (
        _get_project_element(db, project_id, classification.element_id)
        if classification is not None
        else None
    )
    if review is None or element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="review not found"
        )

    try:
        result = undo_review(db, review, element, user)
    except ReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    db.commit()
    return ReviewActionOut(
        classification=result.classification,
        review=ReviewOut(
            id=result.review.id,
            action=result.review.action,
            comment=result.review.comment,
            created_at=result.review.created_at,
            user_email=user.email,
        ),
    )
