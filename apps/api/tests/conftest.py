"""Shared pytest fixtures and helpers.

Forces AUTH_DISABLED off for the whole test session, regardless of what's in the
developer's local .env — tests must exercise real auth (test_auth.py especially),
not whatever dev-convenience bypass happens to be set locally. See app/core/deps.py.
"""

import os

import pytest

from app.core.config import get_settings
from app.db.models import (
    Classification,
    Element,
    ExampleMemory,
    IfcFile,
    Job,
    Project,
    Quantity,
    User,
)
from app.db.session import SessionLocal


@pytest.fixture(autouse=True, scope="session")
def _force_real_auth_for_tests():
    os.environ["AUTH_DISABLED"] = "false"
    get_settings.cache_clear()
    yield


def cleanup_project_cascade(project_id: int, user_id: int | None = None) -> None:
    """Deletes a test project and everything that (transitively) FKs to it, in the
    correct order: quantities/classifications -> elements -> jobs -> ifc_files ->
    project -> user.

    One shared helper instead of a `_cleanup()` copy per test file — every new table
    that FKs onto `elements` (quantities in 2.3, classifications in Phase P) or
    straight onto `projects` (example_memory, added in 3.3's tests) has broken this
    logic at least once. Update this one function when that happens again, not four.
    """
    db = SessionLocal()
    try:
        ifc_file_ids = [
            f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
        ]
        if ifc_file_ids:
            element_ids = [
                e.id
                for e in db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids))
            ]
            if element_ids:
                db.query(Quantity).filter(Quantity.element_id.in_(element_ids)).delete(
                    synchronize_session=False
                )
                db.query(Classification).filter(
                    Classification.element_id.in_(element_ids)
                ).delete(synchronize_session=False)
            db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids)).delete(
                synchronize_session=False
            )
            db.query(Job).filter(Job.ifc_file_id.in_(ifc_file_ids)).delete(
                synchronize_session=False
            )
            db.query(IfcFile).filter(IfcFile.id.in_(ifc_file_ids)).delete(
                synchronize_session=False
            )
        db.query(Job).filter(Job.project_id == project_id).delete(
            synchronize_session=False
        )
        db.query(ExampleMemory).filter(ExampleMemory.project_id == project_id).delete(
            synchronize_session=False
        )
        db.query(Project).filter(Project.id == project_id).delete()
        if user_id is not None:
            db.query(User).filter(User.id == user_id).delete()
        db.commit()
    finally:
        db.close()
