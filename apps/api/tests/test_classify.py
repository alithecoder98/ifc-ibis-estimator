"""Phase P.1/P.2: jev client and classification.

test_jev_* exercise app/ai/jev.py directly (no DB/network). test_classify_elements_*
and test_process_ifc_file_classifies_* exercise the actual classification step,
including through the real worker.
"""

import os
from pathlib import Path

import pytest

from app.ai.classify import AUTO_ACCEPT_THRESHOLD, classify_elements
from app.ai.jev import JevClient, StubJevClient, get_jev_client
from app.core.config import get_settings
from app.db.models import Classification, Element, IfcFile, Job, Project, User
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
