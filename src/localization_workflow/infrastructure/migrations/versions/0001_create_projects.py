"""Create projects table."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_language", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("media_path", sa.String(length=1000)),
        sa.Column("original_filename", sa.String(length=500)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("media_type", sa.String(length=20)),
        sa.Column("video_codec", sa.String(length=100)),
        sa.Column("audio_codec", sa.String(length=100)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("projects")
