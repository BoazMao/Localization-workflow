"""Add translation review states.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("UPDATE segment_translations SET status = 'draft' WHERE status = 'ready'")


def downgrade() -> None:
    op.execute(
        "UPDATE segment_translations SET status = 'ready' "
        "WHERE status IN ('draft', 'reviewed', 'approved', 'outdated')"
    )
