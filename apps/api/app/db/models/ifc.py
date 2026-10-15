"""ifc_files, elements, quantities — the extraction pipeline's tables (Phase 2)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class IfcFile(Base):
    __tablename__ = "ifc_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    # IFC2X3 / IFC4 / etc. — filled in once the file is opened and validated (Phase 2.1).
    ifc_schema: Mapped[str | None] = mapped_column(String(20), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    # uploaded / extracting / extracted / classifying / done / failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    # Storage key of the converted That Open fragments file (Phase 2.6) — null until
    # conversion runs.
    fragments_storage_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    # Maps each element's GlobalId to its fragment local ID, for the (not-yet-built)
    # viewer's table <-> model sync (Phase 5.2). Inverse of what the Node conversion
    # script produces (local ID -> GlobalId) — inverted once here since lookups will
    # always start from an element's GlobalId, not a fragment ID.
    fragment_id_map: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Element(Base):
    """One building element extracted from an IFC file (a wall, slab, roof, ...)."""

    __tablename__ = "elements"

    id: Mapped[int] = mapped_column(primary_key=True)
    ifc_file_id: Mapped[int] = mapped_column(
        ForeignKey("ifc_files.id"), nullable=False, index=True
    )
    # Set only on a row created by splitting a composite element into its
    # material layers (Phase 6.2) - each split-out layer is a real Element of
    # its own (own quantities, own classification, own review lifecycle),
    # pointing back at the original row it was split from. Null for every
    # element that was never split and for every element that hasn't been
    # split *into* (i.e. isn't itself a layer).
    parent_element_id: Mapped[int | None] = mapped_column(
        ForeignKey("elements.id"), nullable=True, index=True
    )
    global_id: Mapped[str] = mapped_column(String(22), nullable=False, index=True)
    ifc_class: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    predefined_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storey: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_external: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    load_bearing: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Material layer set, e.g. [{"material": "...", "thickness_mm": 100}, ...]
    materials: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # All IFC property sets, keyed by Pset name.
    psets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Deterministic compact text built from the fields above — the classification
    # pipeline's input and embedding source (Phase 2.5/2.3).
    profile_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Groups identical element types so they're classified once (Phase 2.5).
    group_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_elements_ifc_file_id_global_id", "ifc_file_id", "global_id"),
    )


class Quantity(Base):
    """A single measured quantity for an element — one row per quantity type, so an
    element can have length + area + volume side by side, and a composite element can
    have one row per material layer (Phase 2.4).
    """

    __tablename__ = "quantities"

    id: Mapped[int] = mapped_column(primary_key=True)
    element_id: Mapped[int] = mapped_column(
        ForeignKey("elements.id"), nullable=False, index=True
    )
    # length / area_net / area_gross / volume_net / volume_gross / count
    quantity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # qto (read from the IFC's own quantity sets) / geometry (computed fallback)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
