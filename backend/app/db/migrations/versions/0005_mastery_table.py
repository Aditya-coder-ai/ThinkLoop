"""Create mastery table.

Revision ID: 0005_mastery_table
Revises: 0004_misconception_events
Create Date: 2026-10-17 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_mastery_table"
down_revision: str | None = "0004_misconception_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mastery",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("concept_id", sa.String(), nullable=False),
        sa.Column("p_known", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name="fk_mastery_concept_id_concepts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_mastery_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "concept_id", name="pk_mastery"),
    )
    op.create_index("ix_mastery_user_id", "mastery", ["user_id"])
    op.create_index("ix_mastery_concept_id", "mastery", ["concept_id"])
    op.create_index("ix_mastery_updated_at", "mastery", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_mastery_updated_at", table_name="mastery")
    op.drop_index("ix_mastery_concept_id", table_name="mastery")
    op.drop_index("ix_mastery_user_id", table_name="mastery")
    op.drop_table("mastery")
