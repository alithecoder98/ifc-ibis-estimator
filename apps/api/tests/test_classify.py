"""Phase P.1/P.2: jev client and classification.

test_jev_* exercise app/ai/jev.py directly (no DB/network). test_classify_elements_*
and test_process_ifc_file_classifies_* exercise the actual classification step,
including through the real worker.
"""

import os
import uuid
from pathlib import Path

import pytest

from app.ai.classify import AUTO_ACCEPT_THRESHOLD, classify_elements
from app.ai.embedder import FakeEmbedder
from app.ai.jev import JevClient, JevResult, StubJevClient, get_jev_client
from app.ai.llm import LLMResult
from app.core.config import get_settings
from app.core.constants import EMBEDDING_DIM
from app.db.models import Classification, CodeList, Element, IfcFile, Job, Project, User
from app.db.session import SessionLocal
from app.storage import upload_fileobj
from app.workers.extraction import process_ifc_file
from tests.conftest import cleanup_project_cascade

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_get_jev_client_returns_stub_when_unconfigured() -> None:
    os.environ["JEV_API_URL"] = ""
    os.environ["JEV_API_KEY"] = ""
    get_settings.cache_clear()
    try:
        assert isinstance(get_jev_client(), StubJevClient)
    finally:
        get_settings.cache_clear()


def test_get_jev_client_returns_real_client_once_configured() -> None:
    os.environ["JEV_API_URL"] = "https://example.com/jev"
    os.environ["JEV_API_KEY"] = "fake-key-for-this-test"
    get_settings.cache_clear()
    try:
        client = get_jev_client()
        assert isinstance(client, JevClient)
        # Confirms the real client isn't silently guessing at an API contract we
        # don't actually know - it must raise, not fabricate a result.
        with pytest.raises(NotImplementedError):
            client.classify("Class: IfcWall")
    finally:
        os.environ["JEV_API_URL"] = ""
        os.environ["JEV_API_KEY"] = ""
        get_settings.cache_clear()


def test_stub_jev_client_always_flags_itself() -> None:
    result = StubJevClient().classify("Class: IfcWall")
    assert result.is_stub is True
    assert result.confidence == 0.0
    assert result.ibis_code is None


def test_classify_elements_calls_jev_once_per_group_not_per_element() -> None:
    db = SessionLocal()
    project_id, user_id = None, None
    try:
        user = User(
            email="classify-p2@example.com", password_hash="x", role="estimator"
        )
        db.add(user)
        db.flush()
        user_id = user.id
        project = Project(name="Classify Test Project", created_by=user.id)
        db.add(project)
        db.flush()
        project_id = project.id
        ifc_file = IfcFile(
            project_id=project.id,
            filename="x.ifc",
            storage_key="unused",
            size_bytes=1,
            uploaded_by=user.id,
        )
        db.add(ifc_file)
        db.flush()

        # 3 elements, 2 distinct groups (A, A, B).
        elements = [
            Element(
                ifc_file_id=ifc_file.id,
                global_id=f"G{i}",
                ifc_class="IfcWall",
                profile_text=f"profile {i}",
                group_hash="group-A" if i < 2 else "group-B",
            )
            for i in range(3)
        ]
        db.add_all(elements)
        db.flush()

        call_count = 0

        class CountingStubClient:
            def classify(self, profile_text: str):
                nonlocal call_count
                call_count += 1
                return StubJevClient().classify(profile_text)

        import app.ai.classify as classify_module

        original_get_jev_client = classify_module.get_jev_client
        classify_module.get_jev_client = lambda: CountingStubClient()
        try:
            classify_elements(db, elements)
        finally:
            classify_module.get_jev_client = original_get_jev_client
        db.commit()

        assert call_count == 2  # one per unique group_hash, not one per element

        classifications = (
            db.query(Classification)
            .filter(Classification.element_id.in_([e.id for e in elements]))
            .all()
        )
        assert len(classifications) == 3  # every element still gets its own row
        assert all(c.source == "jev" for c in classifications)
        assert all(c.status == "needs_review" for c in classifications)  # stub -> 0.0
    finally:
        db.close()
        if project_id is not None:
            cleanup_project_cascade(project_id, user_id)


class _FakeLLMClient:
    def __init__(self, result: LLMResult):
        self.result = result
        self.call_count = 0

    def chat(self, prompt: str):
        self.call_count += 1
        return (
            {
                "ibis_code": self.result.ibis_code or "NONE",
                "internal_element": self.result.internal_element,
                "reasoning": self.result.reasoning,
                "self_score": self.result.self_score,
                "flags": self.result.flags,
            },
            10,
            5,
        )


def _setup_project_and_element(engine: str) -> tuple[int, int, Element, int]:
    """Also seeds one real CodeList row ("21.10", family "wall") so classify_with_llm
    has a valid candidate to accept - without it, every ibis_code the fake LLM
    returns would correctly fail validation as "not one of the candidates".
    """
    db = SessionLocal()
    user = User(
        email=f"classify-3.5-{engine}@example.com", password_hash="x", role="estimator"
    )
    db.add(user)
    db.flush()
    project = Project(
        name=f"Classify 3.5 {engine} Project",
        created_by=user.id,
        classification_engine=engine,
    )
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
    db.flush()
    # Unique per call, not a fixed literal: app/ai/retrieval.py caches its lookups
    # in-process keyed by group_hash, so two tests sharing one literal group_hash
    # would have the second reuse the first's cached CodeList rows - bound to a
    # session that test already closed.
    element = Element(
        ifc_file_id=ifc_file.id,
        global_id="G1",
        ifc_class="IfcWall",
        profile_text="profile",
        group_hash=uuid.uuid4().hex,
    )
    db.add(element)

    code = CodeList(
        ibis_code="21.10",
        internal_element="Buitenwand beton",
        description="concrete exterior wall",
        family="wall",
        embedding=FakeEmbedder(EMBEDDING_DIM).embed(["concrete exterior wall"])[0],
    )
    db.add(code)
    db.commit()
    return project.id, user.id, element, code.id


def _delete_code(code_id: int) -> None:
    db = SessionLocal()
    db.query(CodeList).filter(CodeList.id == code_id).delete()
    db.commit()
    db.close()


def test_classify_elements_engine_llm_calls_llm_only() -> None:
    project_id, user_id, element, code_id = _setup_project_and_element("llm")
    db = SessionLocal()
    try:
        llm_client = _FakeLLMClient(
            LLMResult(
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                reasoning="matches",
                self_score=0.9,
                flags=[],
            )
        )

        import app.ai.classify as classify_module

        original_get_embedder = classify_module.get_embedder
        original_get_llm_client = classify_module.get_llm_client
        classify_module.get_embedder = lambda: FakeEmbedder(EMBEDDING_DIM)
        classify_module.get_llm_client = lambda: llm_client
        try:
            classify_elements(db, [element])
        finally:
            classify_module.get_embedder = original_get_embedder
            classify_module.get_llm_client = original_get_llm_client
        db.commit()

        assert llm_client.call_count == 1
        classifications = (
            db.query(Classification)
            .filter(Classification.element_id == element.id)
            .all()
        )
        assert len(classifications) == 1
        assert classifications[0].source == "llm"
        assert classifications[0].ibis_code == "21.10"
        assert classifications[0].status == "auto_accepted"
        assert classifications[0].agreement is None
    finally:
        db.close()
        _delete_code(code_id)
        cleanup_project_cascade(project_id, user_id)


def test_classify_elements_engine_both_agree() -> None:
    project_id, user_id, element, code_id = _setup_project_and_element("both")
    db = SessionLocal()
    try:
        llm_client = _FakeLLMClient(
            LLMResult(
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                reasoning="matches",
                self_score=0.9,
                flags=[],
            )
        )

        class AgreeingJevClient:
            def classify(self, profile_text: str):
                return JevResult(
                    ibis_code="21.10",
                    internal_element="Buitenwand beton",
                    confidence=0.7,
                    reasoning="jev agrees",
                )

        import app.ai.classify as classify_module

        original_get_embedder = classify_module.get_embedder
        original_get_llm_client = classify_module.get_llm_client
        original_get_jev_client = classify_module.get_jev_client
        classify_module.get_embedder = lambda: FakeEmbedder(EMBEDDING_DIM)
        classify_module.get_llm_client = lambda: llm_client
        classify_module.get_jev_client = lambda: AgreeingJevClient()
        try:
            classify_elements(db, [element])
        finally:
            classify_module.get_embedder = original_get_embedder
            classify_module.get_llm_client = original_get_llm_client
            classify_module.get_jev_client = original_get_jev_client
        db.commit()

        classifications = {
            c.source: c
            for c in db.query(Classification)
            .filter(Classification.element_id == element.id)
            .all()
        }
        assert set(classifications.keys()) == {"llm", "jev"}
        assert classifications["llm"].agreement is True
        assert classifications["jev"].agreement is True
    finally:
        db.close()
        _delete_code(code_id)
        cleanup_project_cascade(project_id, user_id)


def test_classify_elements_engine_both_disagree() -> None:
    project_id, user_id, element, code_id = _setup_project_and_element("both")
    db = SessionLocal()
    try:
        llm_client = _FakeLLMClient(
            LLMResult(
                ibis_code="21.10",
                internal_element="Buitenwand beton",
                reasoning="matches",
                self_score=0.9,
                flags=[],
            )
        )

        class DisagreeingJevClient:
            def classify(self, profile_text: str):
                return JevResult(
                    ibis_code="99.99",
                    internal_element="Something else",
                    confidence=0.7,
                    reasoning="jev disagrees",
                )

        import app.ai.classify as classify_module

        original_get_embedder = classify_module.get_embedder
        original_get_llm_client = classify_module.get_llm_client
        original_get_jev_client = classify_module.get_jev_client
        classify_module.get_embedder = lambda: FakeEmbedder(EMBEDDING_DIM)
        classify_module.get_llm_client = lambda: llm_client
        classify_module.get_jev_client = lambda: DisagreeingJevClient()
        try:
            classify_elements(db, [element])
        finally:
            classify_module.get_embedder = original_get_embedder
            classify_module.get_llm_client = original_get_llm_client
            classify_module.get_jev_client = original_get_jev_client
        db.commit()

        classifications = {
            c.source: c
            for c in db.query(Classification)
            .filter(Classification.element_id == element.id)
            .all()
        }
        assert classifications["llm"].agreement is False
        assert classifications["jev"].agreement is False
    finally:
        db.close()
        _delete_code(code_id)
        cleanup_project_cascade(project_id, user_id)


def test_process_ifc_file_creates_classifications_grouped_correctly() -> None:
    db = SessionLocal()
    user = User(email="classify-p2b@example.com", password_hash="x", role="estimator")
    db.add(user)
    db.flush()
    project = Project(name="Classify Worker Test", created_by=user.id)
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(project)
    project_id, user_id = project.id, user.id
    try:
        fixture_path = FIXTURES_DIR / "real_sample.ifc"
        storage_key = "tests/P.2/real_sample.ifc"
        with open(fixture_path, "rb") as fh:
            upload_fileobj(fh, storage_key)

        ifc_file = IfcFile(
            project_id=project.id,
            filename="real_sample.ifc",
            storage_key=storage_key,
            ifc_schema="IFC2X3",
            size_bytes=fixture_path.stat().st_size,
            uploaded_by=user.id,
            status="uploaded",
        )
        db.add(ifc_file)
        db.flush()
        job = Job(type="extract", project_id=project.id, ifc_file_id=ifc_file.id)
        db.add(job)
        db.commit()

        process_ifc_file(job.id, ifc_file.id)

        db.refresh(job)
        assert job.status == "done"
        assert job.progress == 100

        elements = db.query(Element).filter(Element.ifc_file_id == ifc_file.id).all()
        classifications = (
            db.query(Classification)
            .filter(Classification.element_id.in_([e.id for e in elements]))
            .all()
        )
        # Every element gets exactly one classification row.
        assert len(classifications) == len(elements) == 13
        assert all(c.source == "jev" for c in classifications)
        assert all(c.flags == ["jev_stub"] for c in classifications)
        # Stub confidence (0.0) is always below AUTO_ACCEPT_THRESHOLD.
        assert all(
            c.confidence is not None and c.confidence < AUTO_ACCEPT_THRESHOLD
            for c in classifications
        )
        assert all(c.status == "needs_review" for c in classifications)
    finally:
        db.close()
        cleanup_project_cascade(project_id, user_id)
