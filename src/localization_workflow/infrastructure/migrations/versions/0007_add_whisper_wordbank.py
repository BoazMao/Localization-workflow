"""Add optional per-project Whisper wordbank.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("whisper_wordbank", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "projects",
        sa.Column(
            "whisper_wordbank_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "whisper_wordbank_enabled")
    op.drop_column("projects", "whisper_wordbank")
