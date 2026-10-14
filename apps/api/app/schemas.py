"""Pydantic request/response models shared across routers."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ai.rules import RuleCondition


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    progress: int
    error: str | None


class ProjectCreate(BaseModel):
    name: str


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    classification_engine: str
    created_by: int
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(BaseModel):
    name: str | None = None
    classification_engine: Literal["llm", "jev", "both"] | None = None


class IfcFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    filename: str
    ifc_schema: str | None
    size_bytes: int
    status: str
    uploaded_at: datetime
    # The latest Job for this file (Phase 4.2) - not an IfcFile column, so the
    # router builds this field itself rather than relying on from_attributes.
    # Without it the frontend has no way to know which job to poll after upload.
    job_id: int | None = None


class CodeListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ibis_code: str
    internal_element: str
    description: str | None
    unit: str | None
    family: str | None
    version: int
    created_at: datetime


class RuleCreate(BaseModel):
    conditions: list[RuleCondition]
    result_ibis_code: str
    result_internal_element: str
    priority: int = 0
    status: Literal["suggested", "active"] = "active"


class RuleUpdate(BaseModel):
    conditions: list[RuleCondition] | None = None
    result_ibis_code: str | None = None
    result_internal_element: str | None = None
    priority: int | None = None
    status: Literal["suggested", "active"] | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conditions: list[dict]
    result_ibis_code: str
    result_internal_element: str
    priority: int
    status: str
    created_at: datetime
