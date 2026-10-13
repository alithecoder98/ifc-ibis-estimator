"""Phase 3.3: retrieval - shortlisted codes + similar examples for the (not-yet-built)
3.4 LLM prompt.

Seeds real CodeList/ExampleMemory rows and uses FakeEmbedder (same bag-of-words
hashing as test_codes.py) so similarity rankings are deterministic and assertable,
per the plan's "tests with seeded examples return expected neighbours."
"""

from app.ai.embedder import FakeEmbedder
from app.ai.retrieval import (
    clear_cache,
    guess_family,
    shortlist_and_examples,
    shortlist_codes,
    similar_examples,
)
from app.core.constants import EMBEDDING_DIM
from app.db.models import CodeList, ExampleMemory, Project, User
from app.db.session import SessionLocal
from tests.conftest import cleanup_project_cascade


def test_guess_family_covers_every_supported_class() -> None:
    assert guess_family("IfcWall", None) == "wall"
    assert guess_family("IfcFooting", None) == "foundation"
    assert guess_family("IfcPile", None) == "foundation"
    assert guess_family("IfcDoor", None) == "opening"
    assert guess_family("IfcWindow", None) == "opening"
    assert guess_family("IfcCovering", None) == "finish"
    assert guess_family("IfcBuildingElementProxy", None) == "other"


def test_guess_family_disambiguates_slab_by_predefined_type() -> None:
    assert guess_family("IfcSlab", "ROOF") == "roof"
    assert guess_family("IfcSlab", "FLOOR") == "floor"
    assert guess_family("IfcSlab", None) == "floor"


def _seed_codes() -> list[CodeList]:
    rows = [
        CodeList(
            ibis_code="21.10",
            internal_element="Buitenwand beton",
            description="concrete exterior wall",
            family="wall",
            version=1,
        ),
        CodeList(
            ibis_code="21.20",
            internal_element="Binnenwand beton",
            description="concrete interior wall",
            family="wall",
            version=1,
        ),
        CodeList(
            ibis_code="41.10",
            internal_element="Dakconstructie hout",
            description="timber roof truss structure",
            family="roof",
            version=1,
        ),
    ]
    embedder = FakeEmbedder(EMBEDDING_DIM)
    for row, embedding in zip(
        rows, embedder.embed([r.description for r in rows]), strict=True
    ):
        row.embedding = embedding
    return rows


def test_shortlist_codes_filters_by_family_when_enough_results() -> None:
    db = SessionLocal()
    rows = _seed_codes()
    db.add_all(rows)
    db.commit()
    ids = [r.id for r in rows]
    try:
        results = shortlist_codes(
            db, "concrete wall", FakeEmbedder(EMBEDDING_DIM), family="wall", limit=1
        )
        assert len(results) == 1
        assert results[0].family == "wall"
    finally:
        db.query(CodeList).filter(CodeList.id.in_(ids)).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_shortlist_codes_falls_back_to_all_families_when_too_few() -> None:
    db = SessionLocal()
    rows = _seed_codes()
    db.add_all(rows)
    db.commit()
    ids = [r.id for r in rows]
    try:
        # Only 2 "wall" rows exist, but limit=15 - too few within family, so the
        # fallback must widen to all families and include the "roof" row too.
        results = shortlist_codes(
            db, "concrete wall", FakeEmbedder(EMBEDDING_DIM), family="wall", limit=15
        )
        assert {r.ibis_code for r in results} == {"21.10", "21.20", "41.10"}
    finally:
        db.query(CodeList).filter(CodeList.id.in_(ids)).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_similar_examples_ranks_shared_words_above_unrelated() -> None:
    db = SessionLocal()
    user = User(email="retrieval-3.3@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Retrieval Test Project", created_by=user.id)
    db.add(project)
    db.commit()
    project_id, user_id = project.id, user.id

    rows = [
        ExampleMemory(
            profile_text="concrete exterior wall",
            final_ibis_code="21.10",
            final_internal_element="Buitenwand beton",
            project_id=project_id,
        ),
        ExampleMemory(
            profile_text="timber roof truss structure",
            final_ibis_code="41.10",
            final_internal_element="Dakconstructie hout",
            project_id=project_id,
        ),
    ]
    embedder = FakeEmbedder(EMBEDDING_DIM)
    for row, embedding in zip(
        rows, embedder.embed([r.profile_text for r in rows]), strict=True
    ):
        row.embedding = embedding
    db.add_all(rows)
    db.commit()
    try:
        results = similar_examples(db, "concrete wall", FakeEmbedder(EMBEDDING_DIM))
        assert results[0].final_ibis_code == "21.10"
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_shortlist_and_examples_caches_per_group_hash() -> None:
    clear_cache()
    db = SessionLocal()
    rows = _seed_codes()
    db.add_all(rows)
    db.commit()
    ids = [r.id for r in rows]
    try:
        call_count = 0
        base_embedder = FakeEmbedder(EMBEDDING_DIM)

        class CountingEmbedder:
            def embed(self, texts: list[str]) -> list[list[float]]:
                nonlocal call_count
                call_count += 1
                return base_embedder.embed(texts)

        codes_a, examples_a = shortlist_and_examples(
            db, CountingEmbedder(), "group-1", "concrete wall", "IfcWall", None
        )
        assert call_count == 2  # one for codes, one for examples

        codes_b, examples_b = shortlist_and_examples(
            db, CountingEmbedder(), "group-1", "concrete wall", "IfcWall", None
        )
        assert call_count == 2  # same group_hash - no new embedder calls
        assert codes_a == codes_b
        assert examples_a == examples_b

        shortlist_and_examples(
            db, CountingEmbedder(), "group-2", "timber roof", "IfcRoof", None
        )
        assert call_count == 4  # different group_hash - cache miss
    finally:
        clear_cache()
        db.query(CodeList).filter(CodeList.id.in_(ids)).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()
