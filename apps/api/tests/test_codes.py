"""Phase 3.1: code list import, versioning, and similarity search.

test_parse_* and test_import_codes_*/test_search_codes_* exercise app/ai/codes.py
directly against a real DB with FakeEmbedder (per the plan's own instruction: "Tests
with a fake embedder") - no Ollama needed for these. test_import_endpoint_* /
test_search_endpoint_* drive the real admin endpoints end to end, still with
FakeEmbedder injected (get_embedder monkeypatched), since nothing here needs to prove
Ollama's real output - only that the endpoints wire the pieces together correctly.
"""

import io
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.routers.codes as codes_router_module
from app.ai.codes import (
    CodeRow,
    import_codes,
    parse_codes_csv,
    parse_codes_xlsx,
    search_codes,
)
from app.ai.embedder import FakeEmbedder
from app.core.constants import EMBEDDING_DIM
from app.core.security import create_access_token
from app.db.models import CodeList, User
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _cleanup_codes(code_ids: list[int]) -> None:
    db = SessionLocal()
    db.query(CodeList).filter(CodeList.id.in_(code_ids)).delete(
        synchronize_session=False
    )
    db.commit()
    db.close()


def test_parse_codes_csv_valid_rows() -> None:
    content = (
        b"ibis_code,internal_element,description,unit,family\n"
        b"21.10,Buitenwand beton,Concrete exterior wall,m2,wall\n"
    )
    rows = parse_codes_csv(content)
    assert rows == [
        CodeRow(
            ibis_code="21.10",
            internal_element="Buitenwand beton",
            description="Concrete exterior wall",
            unit="m2",
            family="wall",
        )
    ]


def test_parse_codes_csv_rejects_unknown_family() -> None:
    content = (
        b"ibis_code,internal_element,description,unit,family\n"
        b"21.10,Buitenwand beton,Concrete exterior wall,m2,not-a-real-family\n"
    )
    with pytest.raises(ValidationError):
        parse_codes_csv(content)


def test_parse_codes_xlsx_valid_rows() -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["ibis_code", "internal_element", "description", "unit", "family"])
    sheet.append(
        ["33.40", "Dakbedekking bitumen", "Bitumen roof covering", "m2", "roof"]
    )
    buffer = io.BytesIO()
    workbook.save(buffer)

    rows = parse_codes_xlsx(buffer.getvalue())
    assert rows == [
        CodeRow(
            ibis_code="33.40",
            internal_element="Dakbedekking bitumen",
            description="Bitumen roof covering",
            unit="m2",
            family="roof",
        )
    ]


def test_import_codes_assigns_shared_version_and_embeds_each_row() -> None:
    db = SessionLocal()
    code_ids: list[int] = []
    try:
        rows = [
            CodeRow(
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                description="Concrete exterior wall",
                unit="m2",
                family="wall",
            ),
            CodeRow(
                ibis_code="21.20",
                internal_element="Binnenwand beton",
                description="Concrete interior wall",
                unit="m2",
                family="wall",
            ),
        ]
        imported = import_codes(db, rows, FakeEmbedder(EMBEDDING_DIM))
        db.commit()
        code_ids = [c.id for c in imported]

        assert len(imported) == 2
        assert imported[0].version == imported[1].version
        assert all(len(c.embedding) == EMBEDDING_DIM for c in imported)

        # A second import batch gets the next version number, not a fresh 1.
        more = import_codes(
            db,
            [
                CodeRow(
                    ibis_code="41.10",
                    internal_element="Dakconstructie hout",
                    description="Timber roof structure",
                    unit="m2",
                    family="roof",
                )
            ],
            FakeEmbedder(EMBEDDING_DIM),
        )
        db.commit()
        code_ids += [c.id for c in more]
        assert more[0].version == imported[0].version + 1
    finally:
        db.close()
        _cleanup_codes(code_ids)


def test_search_codes_ranks_shared_words_above_unrelated_text() -> None:
    db = SessionLocal()
    code_ids: list[int] = []
    try:
        rows = [
            CodeRow(
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                description="concrete exterior wall",
                unit="m2",
                family="wall",
            ),
            CodeRow(
                ibis_code="41.10",
                internal_element="Dakconstructie hout",
                description="timber roof truss structure",
                unit="m2",
                family="roof",
            ),
        ]
        imported = import_codes(db, rows, FakeEmbedder(EMBEDDING_DIM))
        db.commit()
        code_ids = [c.id for c in imported]

        results = search_codes(
            db, "concrete wall", FakeEmbedder(EMBEDDING_DIM), limit=2
        )

        assert results[0].ibis_code == "21.10"  # shares words with the query
        assert results[1].ibis_code == "41.10"
    finally:
        db.close()
        _cleanup_codes(code_ids)


def test_search_codes_filters_by_family() -> None:
    db = SessionLocal()
    code_ids: list[int] = []
    try:
        rows = [
            CodeRow(
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                description="concrete exterior wall",
                unit="m2",
                family="wall",
            ),
            CodeRow(
                ibis_code="21.99",
                internal_element="Wall-ish roof thing",
                description="concrete exterior wall",  # identical text, other family
                unit="m2",
                family="roof",
            ),
        ]
        imported = import_codes(db, rows, FakeEmbedder(EMBEDDING_DIM))
        db.commit()
        code_ids = [c.id for c in imported]

        results = search_codes(
            db, "concrete exterior wall", FakeEmbedder(EMBEDDING_DIM), family="roof"
        )

        assert [r.ibis_code for r in results] == ["21.99"]
    finally:
        db.close()
        _cleanup_codes(code_ids)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def admin_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        codes_router_module, "get_embedder", lambda db: FakeEmbedder(EMBEDDING_DIM)
    )
    db = SessionLocal()
    user = User(email="codes-3.1@example.com", password_hash="x", role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    client.cookies.set(
        "access_token", create_access_token(user_id=user_id, role="admin")
    )
    db.close()
    yield client
    client.cookies.clear()
    db = SessionLocal()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def test_import_endpoint_returns_imported_codes(admin_client: TestClient) -> None:
    csv_content = (
        b"ibis_code,internal_element,description,unit,family\n"
        b"21.10,Buitenwand beton,Concrete exterior wall,m2,wall\n"
    )
    code_ids: list[int] = []
    try:
        response = admin_client.post(
            "/codes/import",
            files={"file": ("codes.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["ibis_code"] == "21.10"
        code_ids = [row["id"] for row in body]
    finally:
        _cleanup_codes(code_ids)


def test_import_endpoint_rejects_unsupported_extension(
    admin_client: TestClient,
) -> None:
    response = admin_client.post(
        "/codes/import",
        files={"file": ("codes.txt", b"whatever", "text/plain")},
    )
    assert response.status_code == 400


def test_search_endpoint_returns_matches(admin_client: TestClient) -> None:
    csv_content = (
        b"ibis_code,internal_element,description,unit,family\n"
        b"21.10,Buitenwand beton,concrete exterior wall,m2,wall\n"
    )
    code_ids: list[int] = []
    try:
        import_response = admin_client.post(
            "/codes/import",
            files={"file": ("codes.csv", csv_content, "text/csv")},
        )
        code_ids = [row["id"] for row in import_response.json()]

        response = admin_client.get("/codes/search", params={"q": "concrete wall"})
        assert response.status_code == 200
        results = response.json()
        assert any(r["ibis_code"] == "21.10" for r in results)
    finally:
        _cleanup_codes(code_ids)
