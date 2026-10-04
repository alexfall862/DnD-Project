"""actor_ai_profiles, emotion_states, goals, goal_targets, plans
(database-schema.md §10 actor_ai_profiles, §12 emotion_states/goals/goal_targets/plans)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
EMPTY_LIST = sa.text("'[]'::jsonb")
NOW = sa.text("now()")
GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "actor_ai_profiles",
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("autonomy_profile", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("decision_preferences", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("tactical_preferences", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("preferred_model_profile", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("actor_id"),
    )
    op.create_table(
        "emotion_states",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("emotion_key", sa.String(32), nullable=False),
        sa.Column("intensity", sa.Numeric(4, 3), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=True),
        sa.Column("start_tick", sa.BigInteger(), nullable=False),
        sa.Column("expiry_tick", sa.BigInteger(), nullable=True),
        sa.Column("decay_rule", sa.String(32), server_default="linear", nullable=False),
        sa.Column("resolution_event_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["resolution_event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_emotion_states_actor_status", "emotion_states", ["actor_id", "status"])
    op.create_table(
        "goals",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("owner_type", sa.String(16), nullable=False),  # actor|faction|party
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("parent_goal_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("goal_type", sa.String(32), server_default="personal", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="50", nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("visibility", sa.String(16), server_default="private", nullable=False),
        sa.Column("progress", sa.Numeric(4, 3), server_default="0", nullable=False),
        sa.Column("deadline_tick", sa.BigInteger(), nullable=True),
        sa.Column("created_event_id", sa.UUID(), nullable=True),
        sa.Column("resolved_event_id", sa.UUID(), nullable=True),
        sa.Column("metadata", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_goal_id"], ["goals.id"]),
        sa.ForeignKeyConstraint(["created_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["resolved_event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goals_owner", "goals", ["owner_type", "owner_id", "status"])
    op.create_table(
        "goal_targets",
        sa.Column("goal_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("target_role", sa.String(32), server_default="subject", nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("goal_id", "entity_id", "target_role"),
    )
    op.create_index("ix_goal_targets_entity", "goal_targets", ["entity_id"])
    op.create_table(
        "plans",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("goal_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("current_step", sa.Integer(), server_default="0", nullable=False),
        sa.Column("steps", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("created_event_id", sa.UUID(), nullable=True),
        sa.Column("updated_event_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["updated_event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("plans")
    op.drop_index("ix_goal_targets_entity", table_name="goal_targets")
    op.drop_table("goal_targets")
    op.drop_index("ix_goals_owner", table_name="goals")
    op.drop_table("goals")
    op.drop_index("ix_emotion_states_actor_status", table_name="emotion_states")
    op.drop_table("emotion_states")
    op.drop_table("actor_ai_profiles")
