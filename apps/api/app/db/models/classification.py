"""code_list, classifications, reviews, example_memory, rules — the Phase 3 AI
classification engine's tables, plus Phase 6's review/learning-loop tables.
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.constants import EMBEDDING_DIM
from app.db.base import Base


class CodeList(Base):
    """The client's internal standard element list + IBIS cost codes (Phase 2.1/3.1)."""

    __tablename__ = "code_list"

    id: Mapped[int] = mapped_column(primary_key=True)
    ibis_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    internal_element: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # foundation / wall / floor / roof / column / beam / stair / opening / finish / other
    family: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class Classification(Base):
    """The pipeline's suggestion for one element (Phase 2.6/3.6: rule/LLM/jev + confidence)."""

    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    element_id: Mapped[int] = mapped_column(
        ForeignKey("elements.id"), nullable=False, index=True
    )
    ibis_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    internal_element: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    self_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # e.g. ["missing_quantity", "proxy_element", "unknown_material"]
    flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # see below
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # rule / llm / jev
    # Only set on llm/jev rows written when the project's engine is "both" (Phase
    # 3.5): whether this row's ibis_code matched the other engine's, for that same
    # element, in that same run. Null for rule rows and single-engine runs - there's
    # nothing to agree or disagree with.
    agreement: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Only set on source="llm" rows (Phase 3.8, for the evaluation harness's "cost
    # per model" report) - null, not 0, for rule/jev rows: there's no token count
    # that applies to them at all, which is a different thing from "cost zero."
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


# Classification.status values — referenced by the auto-accept routing (Phase 2.6).
CLASSIFICATION_STATUSES = ("auto_accepted", "needs_review")


class Review(Base):
    """An estimator's approve/correct/split action on a classification (Phase 6.1)."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    classification_id: Mapped[int] = mapped_column(
        ForeignKey("classifications.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # approve/correct/split
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class ExampleMemory(Base):
    """Past approved/corrected elements, reused as few-shot examples (Phase 2.4/6.3)."""

    __tablename__ = "example_memory"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    final_ibis_code: Mapped[str] = mapped_column(String(50), nullable=False)
    final_internal_element: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class Rule(Base):
    """A deterministic classification rule — seeded manually or suggested from repeated
    corrections and approved by an admin (Phase 3.2/6.5).
    """

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False)
    result_ibis_code: Mapped[str] = mapped_column(String(50), nullable=False)
    result_internal_element: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # see below
    # Corrections that justified a *suggested* rule, for the admin approval UI (6.5).
    source_corrections: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


# Rule.status values.
RULE_STATUSES = ("suggested", "active")
