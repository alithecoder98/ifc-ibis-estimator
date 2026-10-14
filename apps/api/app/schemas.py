"""Pydantic request/response models shared across routers."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ai.rules import RuleCondition


class ElementRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    global_id: str
    name: str | None
    ifc_class: str
    storey: str | None
    material: str | None
    quantity: float | None
    unit: str | None
    family: str
    group_hash: str
    suggested_ibis_code: str | None
    internal_element: str | None
    confidence: float | None
    status: str | None


class QuantityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quantity_type: str
    value: float
    unit: str
    source: str


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ibis_code: str
    internal_element: str
    description: str | None
    score: float


class SimilarExampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_text: str
    final_ibis_code: str
    final_internal_element: str


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    comment: str | None
    created_at: datetime
    user_email: str


class ClassificationDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ibis_code: str | None
    internal_element: str | None
    reasoning: str | None
    self_score: float | None
    confidence: float | None
    flags: list[str] | None
    status: str
    source: str
    agreement: bool | None


class ElementDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    global_id: str
    name: str | None
    ifc_class: str
    predefined_type: str | None
    object_type: str | None
    storey: str | None
    is_external: bool | None
    load_bearing: bool | None
    psets: dict | None
    materials: list[dict] | None
    quantities: list[QuantityOut]
    classification: ClassificationDetailOut | None
    candidates: list[CandidateOut]
    similar_examples: list[SimilarExampleOut]
    reviews: list[ReviewOut]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    progress: int
    error: str | None


class CodeTotalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ibis_code: str
    internal_element: str
    unit: str | None
    quantity: float
    element_count: int


class ProjectWarningsOut(BaseModel):
    missing_quantity: int
    proxy_element: int
    unmapped: int


class ProjectSummaryOut(BaseModel):
    total_elements: int
    auto_accepted: int
    needs_review: int
    corrected: int
    warnings: ProjectWarningsOut
    totals_by_code: list[CodeTotalOut]


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
