"""Pydantic request/response models shared across routers."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
