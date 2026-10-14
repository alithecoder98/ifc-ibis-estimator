"""Import every model here so `Base.metadata` is complete wherever `app.db.models` is
imported (Alembic's env.py relies on this for autogenerate).
"""

from app.db.models.classification import (
    Classification,
    CodeList,
    ExampleMemory,
    Review,
    Rule,
)
from app.db.models.exports import Export
from app.db.models.ifc import Element, IfcFile, Quantity
from app.db.models.jobs import Job
from app.db.models.projects import Project
from app.db.models.settings import AppSetting
from app.db.models.users import User

__all__ = [
    "User",
    "Project",
    "IfcFile",
    "Element",
    "Quantity",
    "CodeList",
    "Classification",
    "Review",
    "ExampleMemory",
    "Rule",
    "Export",
    "Job",
    "AppSetting",
]
