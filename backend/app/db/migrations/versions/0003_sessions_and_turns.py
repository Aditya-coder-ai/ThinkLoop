"""Create dialogue sessions and turns tables.

Revision ID: 0003_sessions_and_turns
Revises: 0002_content_tables
Create Date: 2026-10-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_sessions_and_turns"
down_revision: str | None = "0002_content_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("concept_id", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name="fk_sessions_concept_id_concepts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
    )
    op.create_index("ix_sessions_concept_id", "sessions", ["concept_id"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # 2. turns table
    op.create_table(
        "turns",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("diagnosis", sa.JSON(), nullable=True),
        sa.Column("strategy", sa.String(), nullable=True),
        sa.Column("prompt_versions", sa.JSON(), nullable=True),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name="fk_turns_session_id_sessions", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_turns"),
    )
    op.create_index("ix_turns_session_id", "turns", ["session_id"])
    op.create_index("ix_turns_created_at", "turns", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_turns_created_at", table_name="turns")
    op.drop_index("ix_turns_session_id", table_name="turns")
    op.drop_table("turns")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_concept_id", table_name="sessions")
    op.drop_table("sessions")
