"""Add persisted segment translations.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "segment_translations",
        sa.Column(
            "segment_id",
            sa.String(length=36),
            sa.ForeignKey("transcript_segments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_language", sa.String(length=100), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("error", sa.String(length=2000)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_segment_translations_project_id", "segment_translations", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_segment_translations_project_id", table_name="segment_translations")
    op.drop_table("segment_translations")
