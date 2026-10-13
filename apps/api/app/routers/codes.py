"""Admin code-list import, listing, and similarity search (Phase 3.1)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.codes import import_codes as import_codes_rows
from app.ai.codes import parse_codes_csv, parse_codes_xlsx
from app.ai.codes import search_codes as search_codes_query
from app.ai.embedder import get_embedder
from app.core.deps import require_role
from app.db.models import CodeList, User
from app.db.session import get_db
from app.schemas import CodeListOut

router = APIRouter(prefix="/codes", tags=["codes"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


@router.post("/import", response_model=list[CodeListOut])
def import_codes(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> list[CodeList]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"unsupported file type '{suffix}' - expected one of "
                f"{sorted(ALLOWED_EXTENSIONS)}"
            ),
        )

    content = file.file.read()
    try:
        rows = (
            parse_codes_csv(content) if suffix == ".csv" else parse_codes_xlsx(content)
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid code list: {exc}",
        ) from exc

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="file has no rows"
        )

    code_rows = import_codes_rows(db, rows, get_embedder())
    db.commit()
    for row in code_rows:
        db.refresh(row)
    return code_rows


@router.get("", response_model=list[CodeListOut])
def list_codes(
    family: str | None = None,
    latest_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> list[CodeList]:
    q = db.query(CodeList)
    if family is not None:
        q = q.filter(CodeList.family == family)
    if latest_only:
        latest_version = (
            db.query(CodeList.version)
            .order_by(CodeList.version.desc())
            .limit(1)
            .scalar()
        )
        if latest_version is not None:
            q = q.filter(CodeList.version == latest_version)
    return q.order_by(CodeList.ibis_code).all()


@router.get("/search", response_model=list[CodeListOut])
def search_codes(
    q: str = Query(..., min_length=1),
    family: str | None = None,
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> list[CodeList]:
    return search_codes_query(db, q, get_embedder(), family=family, limit=limit)
