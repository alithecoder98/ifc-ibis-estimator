"""initial (empty) baseline

Revision ID: 34dae119ac75
Revises:
Create Date: 2026-10-13 00:11:50.782502

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "34dae119ac75"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
