"""Add target language and glossary entries.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("target_language", sa.String(length=100)))
    op.create_table(
        "glossary_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_term", sa.String(length=500), nullable=False),
        sa.Column("source_term_key", sa.String(length=500), nullable=False),
        sa.Column("target_term", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("project_id", "source_term_key", name="uq_glossary_source_term"),
    )
    op.create_index("ix_glossary_entries_project_id", "glossary_entries", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_glossary_entries_project_id", table_name="glossary_entries")
    op.drop_table("glossary_entries")
    op.drop_column("projects", "target_language")
