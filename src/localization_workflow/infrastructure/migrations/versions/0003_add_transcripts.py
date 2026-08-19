"""Add transcription state and source segments.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "transcription_status",
            sa.String(length=30),
            nullable=False,
            server_default="not_started",
        ),
    )
    op.add_column("projects", sa.Column("transcription_model", sa.String(length=500)))
    op.add_column("projects", sa.Column("transcription_error", sa.String(length=1000)))
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_transcript_segments_project_id", "transcript_segments", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_transcript_segments_project_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_column("projects", "transcription_error")
    op.drop_column("projects", "transcription_model")
    op.drop_column("projects", "transcription_status")
