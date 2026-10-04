"""generation_runs, generation_stages (database-schema.md §17; Milestone 09)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
EMPTY_LIST = sa.text("'[]'::jsonb")
NOW = sa.text("now()")
GEN = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "generation_runs",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("scope", sa.String(32), server_default="full", nullable=False),
        sa.Column(
            "model_profile", sa.String(64), server_default="deep_world_author", nullable=False
        ),
        sa.Column("brief", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','ready','failed','applied')",
            name="ck_generation_runs_status",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_runs_campaign", "generation_runs", ["campaign_id"])
    op.create_table(
        "generation_stages",
        sa.Column("id", sa.UUID(), server_default=GEN, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("depends_on", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("guidance", sa.Text(), nullable=True),
        sa.Column("output", JSONB, nullable=True),
        sa.Column("errors", JSONB, server_default=EMPTY_LIST, nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("model_run_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','ready','failed','invalidated')",
            name="ck_generation_stages_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["generation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "stage_key", name="uq_generation_stage"),
    )
    op.create_index("ix_generation_stages_run", "generation_stages", ["run_id", "order_index"])


def downgrade() -> None:
    op.drop_index("ix_generation_stages_run", table_name="generation_stages")
    op.drop_table("generation_stages")
    op.drop_index("ix_generation_runs_campaign", table_name="generation_runs")
    op.drop_table("generation_runs")
