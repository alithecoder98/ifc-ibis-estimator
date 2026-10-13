"""Pydantic request/response models shared across routers."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ai.rules import RuleCondition


class ProjectCreate(BaseModel):
    name: str


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime


class IfcFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    filename: str
    ifc_schema: str | None
    size_bytes: int
    status: str
    uploaded_at: datetime


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
