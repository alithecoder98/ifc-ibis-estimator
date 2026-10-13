"""add classification_engine to projects and agreement to classifications

Revision ID: b4df4b2fc6f1
Revises: 9d1ddcb204f4
Create Date: 2026-10-13 20:33:54.713421

"""

from collections.abc import Sequence

import pgvector.sqlalchemy  # noqa: F401 — autogenerate's Vector columns need this import
import sqlalchemy as sa

from alembic import op

#   but alembic doesn't detect it automatically; keep it here so every migration has it.


# revision identifiers, used by Alembic.
revision: str = "b4df4b2fc6f1"
down_revision: str | Sequence[str] | None = "9d1ddcb204f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "classifications", sa.Column("agreement", sa.Boolean(), nullable=True)
    )
    # server_default backfills any existing rows before the NOT NULL applies -
    # dropped right after so new inserts rely on the ORM-side default, not a DB one.
    op.add_column(
        "projects",
        sa.Column(
            "classification_engine",
            sa.String(length=10),
            nullable=False,
            server_default="jev",
        ),
    )
    op.alter_column("projects", "classification_engine", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("projects", "classification_engine")
    op.drop_column("classifications", "agreement")
