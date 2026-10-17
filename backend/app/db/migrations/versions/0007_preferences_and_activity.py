"""Create user_preferences and activity_events tables.

Revision ID: 0007_preferences_and_activity
Revises: 0006_turn_leak_suspected
Create Date: 2026-10-17 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_preferences_and_activity"
down_revision: str | None = "0006_turn_leak_suspected"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. user_preferences table
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("daily_goal_minutes", sa.Integer(), server_default="20", nullable=False),
        sa.Column("voice_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("preferred_voice", sa.String(length=64), server_default="alloy", nullable=False),
        sa.Column("locale", sa.String(length=32), server_default="en-US", nullable=False),
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
            name=op.f("fk_user_preferences_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_preferences")),
    )

    # 2. activity_events table
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("ref_type", sa.String(length=64), nullable=True),
        sa.Column("ref_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("meta", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_activity_events_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activity_events")),
        sa.UniqueConstraint("user_id", "kind", "ref_id", name="uq_activity_events_user_kind_ref"),
    )
    op.create_index(
        op.f("ix_activity_events_user_id"), "activity_events", ["user_id"], unique=False
    )
    op.create_index(op.f("ix_activity_events_kind"), "activity_events", ["kind"], unique=False)
    op.create_index(op.f("ix_activity_events_ref_id"), "activity_events", ["ref_id"], unique=False)
    op.create_index(
        op.f("ix_activity_events_occurred_at"), "activity_events", ["occurred_at"], unique=False
    )
    op.create_index(
        op.f("ix_activity_events_local_date"), "activity_events", ["local_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_activity_events_local_date"), table_name="activity_events")
    op.drop_index(op.f("ix_activity_events_occurred_at"), table_name="activity_events")
    op.drop_index(op.f("ix_activity_events_ref_id"), table_name="activity_events")
    op.drop_index(op.f("ix_activity_events_kind"), table_name="activity_events")
    op.drop_index(op.f("ix_activity_events_user_id"), table_name="activity_events")
    op.drop_table("activity_events")
    op.drop_table("user_preferences")
