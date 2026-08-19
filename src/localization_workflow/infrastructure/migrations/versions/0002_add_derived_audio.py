"""Add derived transcription-audio state."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "audio_status", sa.String(length=30), nullable=False, server_default="not_prepared"
        ),
    )
    op.add_column("projects", sa.Column("derived_audio_path", sa.String(length=1000)))
    op.add_column("projects", sa.Column("derived_audio_duration_ms", sa.Integer()))
    op.add_column("projects", sa.Column("audio_error", sa.String(length=1000)))


def downgrade() -> None:
    op.drop_column("projects", "audio_error")
    op.drop_column("projects", "derived_audio_duration_ms")
    op.drop_column("projects", "derived_audio_path")
    op.drop_column("projects", "audio_status")
