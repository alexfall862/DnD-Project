"""memories, memory_sources (database-schema.md §12). Exact per-actor vector scan; no ANN
index in v0.1 (DECISIONS.md "Embeddings and rerank via A9").

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("subjective_summary", sa.Text(), nullable=False),
        sa.Column("emotional_interpretation", sa.Text(), nullable=True),
        sa.Column("salience", sa.Numeric(4, 3), server_default=sa.text("0.5"), nullable=False),
        sa.Column("emotional_weight", sa.Numeric(4, 3), server_default=sa.text("0.0"), nullable=False),
        sa.Column("specificity", sa.Numeric(4, 3), server_default=sa.text("1.0"), nullable=False),
        sa.Column("accessibility", sa.Numeric(4, 3), server_default=sa.text("1.0"), nullable=False),
        sa.Column("is_core", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(16), server_default="detailed", nullable=False),
        sa.Column("parent_memory_id", sa.UUID(), nullable=True),
        sa.Column("entity_ids", postgresql.ARRAY(sa.UUID()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_tick", sa.BigInteger(), nullable=False),
        sa.Column("last_recalled_tick", sa.BigInteger(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("created_event_id", sa.UUID(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["parent_memory_id"], ["memories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_actor_status", "memories", ["actor_id", "status"])
    op.create_index("ix_memories_entity_ids", "memories", ["entity_ids"], postgresql_using="gin")
    op.create_table(
        "memory_sources",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("memory_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("observation_id", sa.UUID(), nullable=True),
        sa.Column("source_memory_id", sa.UUID(), nullable=True),
        sa.Column("source_role", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"]),
        sa.ForeignKeyConstraint(["source_memory_id"], ["memories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_sources_memory", "memory_sources", ["memory_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_sources_memory", table_name="memory_sources")
    op.drop_table("memory_sources")
    op.drop_index("ix_memories_entity_ids", table_name="memories")
    op.drop_index("ix_memories_actor_status", table_name="memories")
    op.drop_table("memories")
