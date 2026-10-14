"""Phase 4.5: element detail panel (properties, materials, quantities, AI
reasoning, candidates with scores, similar examples, review history).
"""

import uuid

from app.ai.element_detail import get_element_detail
from app.ai.embedder import FakeEmbedder
from app.ai.retrieval import shortlist_codes_with_scores
from app.core.constants import EMBEDDING_DIM
from app.db.models import (
    Classification,
    CodeList,
    Element,
    ExampleMemory,
    IfcFile,
    Project,
    Quantity,
    Review,
    User,
)
from app.db.session import SessionLocal
from tests.conftest import cleanup_project_cascade


def _setup_project() -> tuple[int, int, int]:
    db = SessionLocal()
    user = User(
        email=f"element-detail-4.5-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role="estimator",
    )
    db.add(user)
    db.flush()
    project = Project(name="Element Detail Test Project", created_by=user.id)
    db.add(project)
    db.flush()
    ifc_file = IfcFile(
        project_id=project.id,
        filename="x.ifc",
        storage_key="unused",
        size_bytes=1,
        uploaded_by=user.id,
    )
    db.add(ifc_file)
    db.commit()
    project_id, user_id, ifc_file_id = project.id, user.id, ifc_file.id
    db.close()
    return project_id, user_id, ifc_file_id


def test_shortlist_codes_with_scores_orders_best_match_first() -> None:
    db = SessionLocal()
    embedder = FakeEmbedder(EMBEDDING_DIM)
    rows = [
        CodeList(
            ibis_code="21.10",
            internal_element="Buitenwand beton",
            description="concrete exterior wall",
            family="wall",
        ),
        CodeList(
            ibis_code="41.10",
            internal_element="Dakconstructie hout",
            description="timber roof truss structure",
            family="roof",
        ),
    ]
    for row, embedding in zip(
        rows, embedder.embed([r.description for r in rows]), strict=True
    ):
        row.embedding = embedding
    db.add_all(rows)
    db.commit()
    ids = [r.id for r in rows]
    try:
        scored = shortlist_codes_with_scores(db, "concrete wall", embedder)
        assert scored[0][0].ibis_code == "21.10"
        assert all(isinstance(score, float) for _, score in scored)
        assert scored[0][1] >= scored[1][1]  # best match scores highest
    finally:
        db.query(CodeList).filter(CodeList.id.in_(ids)).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_get_element_detail_returns_none_for_missing_element() -> None:
    db = SessionLocal()
    try:
        assert get_element_detail(db, 999999999, FakeEmbedder(EMBEDDING_DIM)) is None
    finally:
        db.close()


def test_get_element_detail_full_shape() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    embedder = FakeEmbedder(EMBEDDING_DIM)
    code_id = None
    try:
        element = Element(
            ifc_file_id=ifc_file_id,
            global_id="G1",
            ifc_class="IfcWall",
            predefined_type=None,
            storey="00 Ground floor",
            is_external=True,
            load_bearing=True,
            psets={"Pset_WallCommon": {"IsExternal": True}},
            materials=[{"material": "Concrete", "thickness_mm": 200.0}],
            profile_text="concrete exterior wall",
            group_hash="hash-1",
        )
        db.add(element)
        db.flush()
        db.add(
            Quantity(
                element_id=element.id,
                quantity_type="area_net",
                value=45.5,
                unit="m2",
                source="qto",
            )
        )
        db.add(
            Classification(
                element_id=element.id,
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                reasoning="matches concrete exterior wall",
                self_score=0.9,
                confidence=0.9,
                status="auto_accepted",
                source="rule",
            )
        )

        code = CodeList(
            ibis_code="21.10",
            internal_element="Buitenwand beton",
            description="concrete exterior wall",
            family="wall",
            embedding=embedder.embed(["concrete exterior wall"])[0],
        )
        db.add(code)

        example = ExampleMemory(
            profile_text="concrete exterior wall 200mm",
            final_ibis_code="21.10",
            final_internal_element="Buitenwand beton",
            project_id=project_id,
            embedding=embedder.embed(["concrete exterior wall 200mm"])[0],
        )
        db.add(example)
        db.commit()
        code_id = code.id

        detail = get_element_detail(db, element.id, embedder)

        assert detail is not None
        assert detail.element.global_id == "G1"
        assert detail.element.materials == [
            {"material": "Concrete", "thickness_mm": 200.0}
        ]
        assert len(detail.quantities) == 1
        assert detail.quantities[0].value == 45.5
        assert detail.classification is not None
        assert detail.classification.reasoning == "matches concrete exterior wall"
        assert len(detail.candidates) == 1
        assert detail.candidates[0].ibis_code == "21.10"
        assert isinstance(detail.candidates[0].score, float)
        assert len(detail.similar_examples) == 1
        assert detail.similar_examples[0].final_ibis_code == "21.10"
        assert detail.reviews == []
    finally:
        db.close()
        if code_id is not None:
            db2 = SessionLocal()
            db2.query(CodeList).filter(CodeList.id == code_id).delete()
            db2.commit()
            db2.close()
        cleanup_project_cascade(project_id, user_id)


def test_get_element_detail_handles_no_profile_text() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    try:
        element = Element(
            ifc_file_id=ifc_file_id,
            global_id="G1",
            ifc_class="IfcWall",
            profile_text=None,
        )
        db.add(element)
        db.commit()

        detail = get_element_detail(db, element.id, FakeEmbedder(EMBEDDING_DIM))
        assert detail is not None
        assert detail.candidates == []
        assert detail.similar_examples == []
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)


def test_get_element_detail_includes_review_history() -> None:
    project_id, user_id, ifc_file_id = _setup_project()
    db = SessionLocal()
    try:
        element = Element(ifc_file_id=ifc_file_id, global_id="G1", ifc_class="IfcWall")
        db.add(element)
        db.flush()
        classification = Classification(
            element_id=element.id,
            ibis_code="21.10",
            status="auto_accepted",
            source="rule",
        )
        db.add(classification)
        db.flush()
        db.add(
            Review(
                classification_id=classification.id,
                user_id=user_id,
                action="correct",
                comment="Should be sand-lime, not concrete",
                before={},
                after={},
            )
        )
        db.commit()

        detail = get_element_detail(db, element.id, FakeEmbedder(EMBEDDING_DIM))
        assert detail is not None
        assert len(detail.reviews) == 1
        assert detail.reviews[0].action == "correct"
        assert detail.reviews[0].comment == "Should be sand-lime, not concrete"
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
