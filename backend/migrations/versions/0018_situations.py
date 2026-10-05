"""situations: recorded obstacles, statuses, promises, clocks, alarms, prices, debts and
followers (DECISIONS 10d)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_t = postgresql.UUID(as_uuid=True)
    op.create_table(
        "situations",
        sa.Column("id", uuid_t, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "campaign_id",
            uuid_t,
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("location_id", uuid_t, sa.ForeignKey("locations.id", ondelete="CASCADE")),
        sa.Column("subject_actor_id", uuid_t, sa.ForeignKey("actors.id", ondelete="CASCADE")),
        sa.Column("holder_actor_id", uuid_t, sa.ForeignKey("actors.id", ondelete="SET NULL")),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("expires_tick", sa.BigInteger()),
        sa.Column("created_event_id", uuid_t, sa.ForeignKey("events.id")),
        sa.Column("closed_event_id", uuid_t, sa.ForeignKey("events.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('obstacle','status','commitment','clock','alarm','price','debt','follower')",
            name="ck_situations_kind",
        ),
        sa.CheckConstraint("status IN ('active','closed','expired')", name="ck_situations_status"),
    )
    op.create_index(
        "ix_situations_location", "situations", ["campaign_id", "location_id", "status"]
    )
    op.create_index("ix_situations_subject", "situations", ["subject_actor_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_situations_subject", table_name="situations")
    op.drop_index("ix_situations_location", table_name="situations")
    op.drop_table("situations")
