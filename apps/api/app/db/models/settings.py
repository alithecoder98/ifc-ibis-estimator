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
# This repo is published without the author's own local Ollama instance - a fresh
# clone needs its own connection configured from the UI (Admin > LLM Connectivity),
# not just apps/api/.env, since not everyone running this has shell access to the
# deployment. Three keys, not one JSON blob, so each can be read/updated independently
# the same way AUTO_ACCEPT_THRESHOLD_KEY already is.
OLLAMA_BASE_URL_KEY = "ollama_base_url"
OLLAMA_EMBEDDING_MODEL_KEY = "ollama_embedding_model"
OLLAMA_LLM_MODEL_KEY = "ollama_llm_model"
