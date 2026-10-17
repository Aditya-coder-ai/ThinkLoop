"""Create curriculum content tables with vector embeddings.

Revision ID: 0002_content_tables
Revises: 0001_initial
Create Date: 2026-10-16 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0002_content_tables"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. concepts table
    if "concepts" not in existing_tables:
        op.create_table(
            "concepts",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("domain", sa.String(), nullable=False),
            sa.Column("topic", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("difficulty", sa.Integer(), nullable=False),
            sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("content_hash", sa.String(), nullable=False),
            sa.Column("embedding", Vector(1024), nullable=True),
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
            sa.PrimaryKeyConstraint("id", name=op.f("pk_concepts")),
        )
        op.create_index(op.f("ix_concepts_domain"), "concepts", ["domain"], unique=False)
        op.create_index(op.f("ix_concepts_topic"), "concepts", ["topic"], unique=False)
        op.create_index(op.f("ix_concepts_is_active"), "concepts", ["is_active"], unique=False)

        if is_postgres:
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_concepts_embedding_hnsw "
                "ON concepts USING hnsw (embedding vector_cosine_ops)"
            )

    # 2. concept_edges table
    if "concept_edges" not in existing_tables:
        op.create_table(
            "concept_edges",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_id", sa.String(), nullable=False),
            sa.Column("target_id", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(
                ["source_id"],
                ["concepts.id"],
                name=op.f("fk_concept_edges_source_id_concepts"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["target_id"],
                ["concepts.id"],
                name=op.f("fk_concept_edges_target_id_concepts"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_edges")),
            sa.UniqueConstraint(
                "source_id", "target_id", name=op.f("uq_concept_edges_source_id_target_id")
            ),
        )
        op.create_index(
            op.f("ix_concept_edges_source_id"), "concept_edges", ["source_id"], unique=False
        )
        op.create_index(
            op.f("ix_concept_edges_target_id"), "concept_edges", ["target_id"], unique=False
        )

    # 3. misconceptions table
    if "misconceptions" not in existing_tables:
        op.create_table(
            "misconceptions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("concept_id", sa.String(), nullable=False),
            sa.Column("statement", sa.String(), nullable=False),
            sa.Column("correct_idea", sa.String(), nullable=False),
            sa.Column("conflict_prompt", sa.String(), nullable=False),
            sa.Column("example_utterances", sa.JSON(), nullable=False),
            sa.Column("evidence", sa.String(), nullable=True),
            sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("content_hash", sa.String(), nullable=False),
            sa.Column("embedding", Vector(1024), nullable=True),
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
                ["concept_id"],
                ["concepts.id"],
                name=op.f("fk_misconceptions_concept_id_concepts"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_misconceptions")),
        )
        op.create_index(
            op.f("ix_misconceptions_concept_id"), "misconceptions", ["concept_id"], unique=False
        )
        op.create_index(
            op.f("ix_misconceptions_is_active"), "misconceptions", ["is_active"], unique=False
        )

        if is_postgres:
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_misconceptions_embedding_hnsw "
                "ON misconceptions USING hnsw (embedding vector_cosine_ops)"
            )

    # 4. problems table
    if "problems" not in existing_tables:
        op.create_table(
            "problems",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("concept_id", sa.String(), nullable=False),
            sa.Column("statement", sa.String(), nullable=False),
            sa.Column("difficulty", sa.Integer(), nullable=False),
            sa.Column("answer_spec", sa.JSON(), nullable=False),
            sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("content_hash", sa.String(), nullable=False),
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
                ["concept_id"],
                ["concepts.id"],
                name=op.f("fk_problems_concept_id_concepts"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_problems")),
        )
        op.create_index(op.f("ix_problems_concept_id"), "problems", ["concept_id"], unique=False)
        op.create_index(op.f("ix_problems_is_active"), "problems", ["is_active"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_misconceptions_embedding_hnsw")
        op.execute("DROP INDEX IF EXISTS ix_concepts_embedding_hnsw")

    op.drop_table("problems")
    op.drop_table("misconceptions")
    op.drop_table("concept_edges")
    op.drop_table("concepts")
