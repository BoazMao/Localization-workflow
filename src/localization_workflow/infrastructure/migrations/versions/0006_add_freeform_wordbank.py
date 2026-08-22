"""Add free-form project wordbank.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("wordbank", sa.Text(), nullable=False, server_default=""),
    )
    op.execute(
        """
        UPDATE projects
        SET wordbank = COALESCE((
            SELECT group_concat(source_term || ': ' || target_term, char(10))
            FROM glossary_entries
            WHERE glossary_entries.project_id = projects.id
        ), '')
        """
    )


def downgrade() -> None:
    op.drop_column("projects", "wordbank")
