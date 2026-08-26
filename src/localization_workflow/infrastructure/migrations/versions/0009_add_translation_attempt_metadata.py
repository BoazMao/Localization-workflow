"""Add translation attempt metadata.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "segment_translations",
        sa.Column("last_attempt_error", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "segment_translations",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("segment_translations", "last_attempt_at")
    op.drop_column("segment_translations", "last_attempt_error")

