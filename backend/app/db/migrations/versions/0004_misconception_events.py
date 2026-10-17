"""Create misconception_events table.

Revision ID: 0004_misconception_events
Revises: 0003_sessions_and_turns
Create Date: 2026-10-17 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_misconception_events"
down_revision: str | None = "0003_sessions_and_turns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "misconception_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("misconception_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("turn_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["misconception_id"],
            ["misconceptions.id"],
            name="fk_misconception_events_misconception_id_misconceptions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_misconception_events_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["turns.id"],
            name="fk_misconception_events_turn_id_turns",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_misconception_events_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_misconception_events"),
    )
    op.create_index("ix_misconception_events_session_id", "misconception_events", ["session_id"])
    op.create_index("ix_misconception_events_user_id", "misconception_events", ["user_id"])
    op.create_index(
        "ix_misconception_events_misconception_id", "misconception_events", ["misconception_id"]
    )
    op.create_index("ix_misconception_events_created_at", "misconception_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_misconception_events_created_at", table_name="misconception_events")
    op.drop_index("ix_misconception_events_misconception_id", table_name="misconception_events")
    op.drop_index("ix_misconception_events_user_id", table_name="misconception_events")
    op.drop_index("ix_misconception_events_session_id", table_name="misconception_events")
    op.drop_table("misconception_events")
