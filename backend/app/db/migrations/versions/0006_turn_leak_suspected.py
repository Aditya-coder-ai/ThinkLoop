"""Add leak_suspected column to turns table.

Revision ID: 0006_turn_leak_suspected
Revises: 0005_mastery_table
Create Date: 2026-10-17 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_turn_leak_suspected"
down_revision: str | None = "0005_mastery_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "turns",
        sa.Column("leak_suspected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("turns", "leak_suspected")
