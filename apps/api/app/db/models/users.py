"""users — login + role. Roles are fixed to admin/estimator/viewer per docs/PROMPTS.md
sub-phase 1.5; kept as a plain string (not a Postgres ENUM) so adding a role later is a
one-line change, not a migration that alters an enum type.
"""

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Allowed values for User.role — enforced in app code (Phase 1.5's require_role
# dependency), not a DB constraint, for the reason above.
ROLES = ("admin", "estimator", "viewer")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="estimator")
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
