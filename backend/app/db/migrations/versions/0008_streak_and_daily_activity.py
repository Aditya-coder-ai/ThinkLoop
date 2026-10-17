"""Create user_streak_state and daily_activity tables.

Revision ID: 0008_streak_and_daily_activity
Revises: 0007_preferences_and_activity
Create Date: 2026-10-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_streak_and_daily_activity"
down_revision: str | None = "0007_preferences_and_activity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. user_streak_state table
    op.create_table(
        "user_streak_state",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("freezes_available", sa.Integer(), server_default="1", nullable=False),
        sa.Column("freezes_used_dates", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("longest_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_user_streak_state_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_streak_state")),
        sa.UniqueConstraint("user_id", name="uq_user_streak_state_user_id"),
    )
    op.create_index(
        op.f("ix_user_streak_state_user_id"),
        "user_streak_state",
        ["user_id"],
        unique=True,
    )

    # 2. daily_activity table
    op.create_table(
        "daily_activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("counts", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("is_qualifying", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("freeze_applied", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_daily_activity_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_activity")),
        sa.UniqueConstraint("user_id", "local_date", name="uq_daily_activity_user_date"),
    )
    op.create_index(op.f("ix_daily_activity_user_id"), "daily_activity", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_daily_activity_local_date"), "daily_activity", ["local_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_daily_activity_local_date"), table_name="daily_activity")
    op.drop_index(op.f("ix_daily_activity_user_id"), table_name="daily_activity")
    op.drop_table("daily_activity")
    op.drop_index(op.f("ix_user_streak_state_user_id"), table_name="user_streak_state")
    op.drop_table("user_streak_state")
