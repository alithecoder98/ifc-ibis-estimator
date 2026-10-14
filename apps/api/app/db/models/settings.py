"""A minimal key/value store for admin-editable runtime settings (Phase 4.6).

Starts with exactly one key (the auto-accept confidence threshold) rather than a
single dedicated column/table per setting, since PROMPTS.md's 4.6 spec only names
one admin-editable setting today and a generic key/value row avoids a migration
for the next one if it ever shows up.
"""

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


# AppSetting.key values.
AUTO_ACCEPT_THRESHOLD_KEY = "auto_accept_threshold"
