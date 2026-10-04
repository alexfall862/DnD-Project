"""mysteries, mystery_truth_facts, clues, clue_discoveries (database-schema.md §13);
items.concealed / items.destroyed_event_id (Milestone 07)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
EMPTY_LIST = sa.text("'[]'::jsonb")
NOW = sa.text("now()")
GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "mysteries",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.Text(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="latent", nullable=False),
        sa.Column("solution_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("stakeholders", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("consequences", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("created_event_id", sa.UUID(), nullable=True),
        sa.Column("activated_event_id", sa.UUID(), nullable=True),
        sa.Column("resolved_event_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('latent','active','solved','failed','abandoned')",
            name="ck_mysteries_status",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["activated_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["resolved_event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_mysteries_campaign_key",
        "mysteries",
        ["campaign_id", "key"],
        unique=True,
        postgresql_where=sa.text("key IS NOT NULL"),
    )
    op.create_table(
        "mystery_truth_facts",
        sa.Column("mystery_id", sa.UUID(), nullable=False),
        sa.Column("fact_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(32), server_default="answer", nullable=False),
        sa.ForeignKeyConstraint(["mystery_id"], ["mysteries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fact_id"], ["facts.id"]),
        sa.PrimaryKeyConstraint("mystery_id", "fact_id"),
    )
    op.create_table(
        "clues",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("mystery_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.Text(), nullable=True),
        sa.Column("clue_type", sa.String(16), nullable=False),
        sa.Column("supported_fact_id", sa.UUID(), nullable=True),
        sa.Column("physical_entity_id", sa.UUID(), nullable=True),
        sa.Column("reliability", sa.Numeric(4, 3), server_default=sa.text("1.0"), nullable=False),
        sa.Column("discovery_conditions", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("destructible", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("forgeable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("state", sa.String(16), server_default="intact", nullable=False),
        sa.Column("created_event_id", sa.UUID(), nullable=True),
        sa.Column("destroyed_event_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("clue_type IN ('physical','document','social')", name="ck_clues_type"),
        sa.CheckConstraint("state IN ('intact','destroyed')", name="ck_clues_state"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mystery_id"], ["mysteries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supported_fact_id"], ["facts.id"]),
        sa.ForeignKeyConstraint(["physical_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["created_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["destroyed_event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clues_mystery", "clues", ["mystery_id"])
    op.create_index("ix_clues_supported_fact", "clues", ["supported_fact_id"])
    op.create_index("ix_clues_physical_entity", "clues", ["physical_entity_id"])
    op.create_index(
        "uq_clues_campaign_key",
        "clues",
        ["campaign_id", "key"],
        unique=True,
        postgresql_where=sa.text("key IS NOT NULL"),
    )
    op.create_table(
        "clue_discoveries",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("clue_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("discovery_event_id", sa.UUID(), nullable=False),
        sa.Column("route", sa.String(16), nullable=False),
        sa.Column("claim_id", sa.UUID(), nullable=True),
        sa.Column("fidelity", sa.String(16), server_default="full", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "route IN ('physical','document','testimony','inference','mechanic')",
            name="ck_clue_discoveries_route",
        ),
        sa.ForeignKeyConstraint(["clue_id"], ["clues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["discovery_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clue_id", "actor_id", "route", "fidelity", name="uq_clue_discovery"),
    )
    op.create_index("ix_clue_discoveries_actor", "clue_discoveries", ["actor_id"])
    op.add_column(
        "items",
        sa.Column("concealed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("items", sa.Column("destroyed_event_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_items_destroyed_event", "items", "events", ["destroyed_event_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_items_destroyed_event", "items", type_="foreignkey")
    op.drop_column("items", "destroyed_event_id")
    op.drop_column("items", "concealed")
    op.drop_index("ix_clue_discoveries_actor", table_name="clue_discoveries")
    op.drop_table("clue_discoveries")
    op.drop_index("uq_clues_campaign_key", table_name="clues")
    op.drop_index("ix_clues_physical_entity", table_name="clues")
    op.drop_index("ix_clues_supported_fact", table_name="clues")
    op.drop_index("ix_clues_mystery", table_name="clues")
    op.drop_table("clues")
    op.drop_table("mystery_truth_facts")
    op.drop_index("uq_mysteries_campaign_key", table_name="mysteries")
    op.drop_table("mysteries")
