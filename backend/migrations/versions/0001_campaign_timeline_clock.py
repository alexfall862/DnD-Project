"""campaigns, timelines, world_clocks (database-schema.md §3)

Revision ID: 0001
Revises: 0000
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = "0000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
NOW = sa.text("now()")
GEN_UUID = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("creation_mode", sa.String(32), nullable=False),
        sa.Column("campaign_mode", sa.String(32), nullable=False),
        sa.Column("active_timeline_id", sa.UUID(), nullable=True),
        sa.Column("ruleset_key", sa.Text(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("settings", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("generation_brief", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("world_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.create_table(
        "timelines",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_timeline_id", sa.UUID(), nullable=True),
        sa.Column("branch_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column(
            "next_event_sequence", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_timeline_id"], ["timelines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_timelines_campaign", "timelines", ["campaign_id"])
    op.create_foreign_key(
        "fk_campaigns_active_timeline", "campaigns", "timelines", ["active_timeline_id"], ["id"]
    )

    op.create_table(
        "world_clocks",
        sa.Column("timeline_id", sa.UUID(), nullable=False),
        sa.Column("current_tick", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("calendar_definition", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("time_policy", sa.String(32), server_default="action_driven", nullable=False),
        sa.Column("real_time_anchor", sa.DateTime(timezone=True), nullable=True),
        sa.Column("game_tick_anchor", sa.BigInteger(), nullable=True),
        sa.Column("time_scale", sa.Double(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("timeline_id"),
    )


def downgrade() -> None:
    op.drop_table("world_clocks")
    op.drop_constraint("fk_campaigns_active_timeline", "campaigns", type_="foreignkey")
    op.drop_index("ix_timelines_campaign", table_name="timelines")
    op.drop_table("timelines")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")
