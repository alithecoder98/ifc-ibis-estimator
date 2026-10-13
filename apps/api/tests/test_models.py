"""Model/schema tests for sub-phase 1.3.

Exercises every table through one realistic chain of related rows (user → project →
ifc_file → element → quantity/classification → review; code_list + example_memory with
embeddings; a rule; an export; a job) against the real local Postgres, then rolls back
so nothing persists. Requires docker-compose up (see README.md).
"""

from app.core.constants import EMBEDDING_DIM
from app.db.models import (
    Classification,
    CodeList,
    Element,
    ExampleMemory,
    Export,
    IfcFile,
    Job,
    Project,
    Quantity,
    Review,
    Rule,
    User,
)
from app.db.session import SessionLocal


def test_full_chain_round_trips_and_vector_columns_work() -> None:
    db = SessionLocal()
    try:
        user = User(
            email="estimator@example.com", password_hash="hashed", role="estimator"
        )
        db.add(user)
        db.flush()

        project = Project(name="Test Project", created_by=user.id)
        db.add(project)
        db.flush()

        ifc_file = IfcFile(
            project_id=project.id,
            filename="model.ifc",
            storage_key="projects/1/model.ifc",
            size_bytes=1024,
            uploaded_by=user.id,
        )
        db.add(ifc_file)
        db.flush()

        element = Element(
            ifc_file_id=ifc_file.id,
            global_id="1a2B3c4D5e6F7g8H9i0JkL",
            ifc_class="IfcWall",
            materials=[{"material": "Concrete", "thickness_mm": 200}],
            psets={"Pset_WallCommon": {"IsExternal": True}},
        )
        db.add(element)
        db.flush()

        quantity = Quantity(
            element_id=element.id,
            quantity_type="area_net",
            value=12.5,
            unit="m2",
            source="qto",
        )
        db.add(quantity)

        code = CodeList(
            ibis_code="12.34",
            internal_element="Buitenwand beton",
            family="wall",
            embedding=[0.1] * EMBEDDING_DIM,
        )
        db.add(code)

        example = ExampleMemory(
            profile_text="IfcWall, Concrete, 200mm, external",
            embedding=[0.2] * EMBEDDING_DIM,
            final_ibis_code="12.34",
            final_internal_element="Buitenwand beton",
            project_id=project.id,
        )
        db.add(example)

        rule = Rule(
            conditions=[{"field": "ifc_class", "operator": "==", "value": "IfcWall"}],
            result_ibis_code="12.34",
            result_internal_element="Buitenwand beton",
            status="active",
        )
        db.add(rule)

        classification = Classification(
            element_id=element.id,
            ibis_code="12.34",
            internal_element="Buitenwand beton",
            self_score=0.92,
            confidence=0.92,
            status="auto_accepted",
            source="rule",
        )
        db.add(classification)
        db.flush()

        review = Review(
            classification_id=classification.id,
            user_id=user.id,
            action="approve",
        )
        db.add(review)

        export = Export(
            project_id=project.id, file_path="exports/1.xlsx", generated_by=user.id
        )
        db.add(export)

        job = Job(type="extract", project_id=project.id, ifc_file_id=ifc_file.id)
        db.add(job)

        db.flush()

        # Round-trip checks, including the vector column.
        stored_element = db.get(Element, element.id)
        assert stored_element is not None
        assert stored_element.materials[0]["material"] == "Concrete"

        stored_code = db.get(CodeList, code.id)
        assert stored_code is not None
        assert len(stored_code.embedding) == EMBEDDING_DIM

        stored_quantity = db.get(Quantity, quantity.id)
        assert stored_quantity is not None
        assert float(stored_quantity.value) == 12.5

        stored_review = db.get(Review, review.id)
        assert stored_review is not None
        assert stored_review.action == "approve"

        stored_job = db.get(Job, job.id)
        assert stored_job is not None
        assert stored_job.status == "queued"
    finally:
        db.rollback()
        db.close()
