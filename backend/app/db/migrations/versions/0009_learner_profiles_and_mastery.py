"""Create learner profiles, learner mastery tracking, and concept subject.

Revision ID: 0009_learner_profiles
Revises: 0008_streak_and_daily_activity
Create Date: 2026-10-17 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_learner_profiles"
down_revision: str | None = "0008_streak_and_daily_activity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Create profiles table if it doesn't already exist
    if "profiles" not in existing_tables:
        op.create_table(
            "profiles",
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("learning_level", sa.String(), nullable=True),
            sa.Column("exam_target", sa.String(), nullable=True),
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
            sa.PrimaryKeyConstraint("user_id", name=op.f("pk_profiles")),
        )

    # 2. Add 'subject' column to 'concepts' table if missing
    if "concepts" in existing_tables:
        concept_cols = {c["name"] for c in inspector.get_columns("concepts")}
        if "subject" not in concept_cols:
            op.add_column("concepts", sa.Column("subject", sa.String(), nullable=True))
            op.create_index(op.f("ix_concepts_subject"), "concepts", ["subject"], unique=False)

    # 3. Create learner_mastery table if it doesn't already exist
    if "learner_mastery" not in existing_tables:
        op.create_table(
            "learner_mastery",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("concept_id", sa.String(), nullable=False),
            sa.Column("mastery_score", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["profiles.user_id"],
                name=op.f("fk_learner_mastery_user_id_profiles"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["concept_id"],
                ["concepts.id"],
                name=op.f("fk_learner_mastery_concept_id_concepts"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_learner_mastery")),
            sa.UniqueConstraint(
                "user_id", "concept_id", name=op.f("uq_learner_mastery_user_concept")
            ),
        )
        op.create_index(
            op.f("ix_learner_mastery_user_id"), "learner_mastery", ["user_id"], unique=False
        )
        op.create_index(
            op.f("ix_learner_mastery_concept_id"), "learner_mastery", ["concept_id"], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "learner_mastery" in existing_tables:
        op.drop_index(op.f("ix_learner_mastery_concept_id"), table_name="learner_mastery")
        op.drop_index(op.f("ix_learner_mastery_user_id"), table_name="learner_mastery")
        op.drop_table("learner_mastery")

    if "concepts" in existing_tables:
        concept_cols = {c["name"] for c in inspector.get_columns("concepts")}
        if "subject" in concept_cols:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("concepts") as batch_op:
                    batch_op.drop_index("ix_concepts_subject")
                    batch_op.drop_column("subject")
            else:
                op.drop_index(op.f("ix_concepts_subject"), table_name="concepts")
                op.drop_column("concepts", "subject")

    if "profiles" in existing_tables:
        op.drop_table("profiles")
