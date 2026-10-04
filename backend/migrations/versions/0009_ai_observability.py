"""context_snapshots, context_items, model_runs, decision_traces, turn_metrics
(database-schema.md §15; turn-budget-and-latency.md §7)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
EMPTY_LIST = sa.text("'[]'::jsonb")
NOW = sa.text("now()")
GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "context_snapshots",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(48), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("purpose", sa.Text(), server_default="", nullable=False),
        sa.Column("authorization_scope", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("rendered_context", sa.Text(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("stable_prefix_chars", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_context_snapshots_actor", "context_snapshots", ["actor_id"])
    op.create_table(
        "context_items",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("owner_actor_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("retrieval_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("authorization", sa.String(16), nullable=False),
        sa.Column("section", sa.String(32), server_default="", nullable=False),
        sa.Column("metadata", JSONB, server_default=EMPTY, nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["context_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_context_items_snapshot", "context_items", ["snapshot_id"])
    op.create_table(
        "model_runs",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=True),
        sa.Column("turn_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("profile", sa.String(32), nullable=False),
        sa.Column("model_requested", sa.Text(), nullable=False),
        sa.Column("model_echo", sa.Text(), nullable=True),
        sa.Column("role", sa.String(48), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("prompt_id", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("context_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("parameters", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("structured_output", JSONB, nullable=True),
        sa.Column("validation", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["context_snapshot_id"], ["context_snapshots.id"]),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_runs_turn", "model_runs", ["turn_id"])
    op.create_index("ix_model_runs_campaign_role", "model_runs", ["campaign_id", "role"])
    op.create_table(
        "decision_traces",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("model_run_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("eligible_goals", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("relevant_beliefs", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("relevant_memories", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("relationships", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("mechanics", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("selected_intent", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("decision_summary", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_run_id"),
    )
    op.create_table(
        "turn_metrics",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=True),
        sa.Column("turn_id", sa.UUID(), nullable=False),
        sa.Column("wall_ms_total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("ms_to_first_output", sa.Integer(), nullable=True),
        sa.Column("ms_to_first_narration_token", sa.Integer(), nullable=True),
        sa.Column("sync_model_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("background_model_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("calls_by_role", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("prompt_tokens_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("completion_tokens_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_context_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("degradation_steps", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("budget_breached", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("claim_extractor_invoked", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("belief_processor_scheduled", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id"),
    )
    op.create_index("ix_turn_metrics_campaign", "turn_metrics", ["campaign_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_turn_metrics_campaign", table_name="turn_metrics")
    op.drop_table("turn_metrics")
    op.drop_table("decision_traces")
    op.drop_index("ix_model_runs_campaign_role", table_name="model_runs")
    op.drop_index("ix_model_runs_turn", table_name="model_runs")
    op.drop_table("model_runs")
    op.drop_index("ix_context_items_snapshot", table_name="context_items")
    op.drop_table("context_items")
    op.drop_index("ix_context_snapshots_actor", table_name="context_snapshots")
    op.drop_table("context_snapshots")
