"""Phase 3.1 — code list import (CSV/XLSX), versioning, and embedding-backed
similarity search over `code_list`.

Import format matches docs/PROMPTS.md's codes_clean.csv spec: ibis_code,
internal_element, description, unit, family. The offline cleaning step that produces
that file (Phase 0.2) is still blocked on the client's real lists, so this takes an
already-clean file as input and doesn't duplicate 0.2's own validation scope
(duplicate/unknown-unit reporting) - just the Pydantic shape check needed to embed
and store each row safely.
"""

import csv
import io
from typing import Literal, Protocol

import openpyxl
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import CodeList

Family = Literal[
    "foundation",
    "wall",
    "floor",
    "roof",
    "column",
    "beam",
    "stair",
    "opening",
    "finish",
    "other",
]


class CodeRow(BaseModel):
    ibis_code: str
    internal_element: str
    description: str
    unit: str
    family: Family


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def parse_codes_csv(content: bytes) -> list[CodeRow]:
    text = content.decode("utf-8")
    return [CodeRow(**row) for row in csv.DictReader(io.StringIO(text))]


def parse_codes_xlsx(content: bytes) -> list[CodeRow]:
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    header = [str(cell).strip() for cell in next(rows)]
    return [
        CodeRow(**dict(zip(header, row, strict=True)))
        for row in rows
        if any(cell is not None for cell in row)
    ]


def _embed_text(row: CodeRow) -> str:
    return f"{row.family} {row.internal_element} {row.description}"


def import_codes(
    db: Session, rows: list[CodeRow], embedder: Embedder
) -> list[CodeList]:
    """Every row in one call shares the same version number - versioning is per
    import batch, not per row.
    """
    next_version = (db.query(func.max(CodeList.version)).scalar() or 0) + 1
    embeddings = embedder.embed([_embed_text(row) for row in rows])
    code_rows = [
        CodeList(
            ibis_code=row.ibis_code,
            internal_element=row.internal_element,
            description=row.description,
            unit=row.unit,
            family=row.family,
            embedding=embedding,
            version=next_version,
        )
        for row, embedding in zip(rows, embeddings, strict=True)
    ]
    db.add_all(code_rows)
    db.flush()
    return code_rows


def latest_code_list_version(db: Session) -> int | None:
    """The max `CodeList.version` currently in the table, or None if it's empty -
    every import shares one version number across all its rows (see
    `import_codes_rows` above), so this is the same "current import" a re-import
    supersedes. `list_codes()` (app/routers/codes.py) already filtered browse
    results to this; every semantic-search query over `code_list` (this function,
    plus app/ai/retrieval.py's shortlist_codes()/shortlist_codes_with_scores())
    did not, so re-importing a code list (an explicitly supported, documented
    action - "Each import adds a new version") made every superseded version of
    every code show up as a duplicate candidate everywhere search touched
    `code_list` except the one place that had already been fixed for it.
    Confirmed live: a re-imported 3-row test list showed every code twice in the
    review picker, with React's own duplicate-key warnings confirming it wasn't
    just a rendering fluke.
    """
    return db.query(func.max(CodeList.version)).scalar()


def search_codes(
    db: Session,
    query: str,
    embedder: Embedder,
    family: str | None = None,
    limit: int = 15,
) -> list[CodeList]:
    [query_vector] = embedder.embed([query])
    q = db.query(CodeList)
    if family is not None:
        q = q.filter(CodeList.family == family)
    latest_version = latest_code_list_version(db)
    if latest_version is not None:
        q = q.filter(CodeList.version == latest_version)
    return (
        q.order_by(CodeList.embedding.cosine_distance(query_vector)).limit(limit).all()
    )
