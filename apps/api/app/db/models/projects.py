"""projects — one per IFC estimating job."""

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free-form status string (e.g. "draft", "processing", "reviewing", "exported") —
    # not a DB enum; the exact set is a 4.1 frontend concern (status badges), not fixed yet.
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    # llm / jev / both - which AI engine(s) classify_elements() calls (Phase 3.5).
    # Defaults to "jev" (the stub) rather than "llm" deliberately: every worker
    # integration test exercises process_ifc_file() end to end, and a default of
    # "llm" would make routine test/CI runs call the real multi-GB local Ollama
    # model instead of the fast deterministic stub - a real regression risk, not a
    # style choice. Set a project to "llm" or "both" explicitly via PATCH /projects/{id}.
    classification_engine: Mapped[str] = mapped_column(
        String(10), nullable=False, default="jev"
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
