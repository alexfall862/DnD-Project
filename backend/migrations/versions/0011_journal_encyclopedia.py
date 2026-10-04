"""journal_entries, encyclopedia_entries (database-schema.md §16)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
NOW = sa.text("now()")
GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("entry_type", sa.String(32), server_default="session", nullable=False),
        sa.Column("title", sa.Text(), server_default="", nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("from_sequence", sa.BigInteger(), nullable=True),
        sa.Column("to_sequence", sa.BigInteger(), nullable=True),
        sa.Column("game_tick", sa.BigInteger(), nullable=False),
        sa.Column("model_run_id", sa.UUID(), nullable=True),
        sa.Column("created_event_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"]),
        sa.ForeignKeyConstraint(["created_event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_entries_actor", "journal_entries", ["actor_id", "created_at"])
    op.create_table(
        "encyclopedia_entries",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("knowledge", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("last_updated_event_id", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["last_updated_event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "entity_id", name="uq_encyclopedia_actor_entity"),
    )


def downgrade() -> None:
    op.drop_table("encyclopedia_entries")
    op.drop_index("ix_journal_entries_actor", table_name="journal_entries")
    op.drop_table("journal_entries")
