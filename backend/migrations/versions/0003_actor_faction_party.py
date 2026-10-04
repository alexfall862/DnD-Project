"""actors, actor_controllers, factions, parties (database-schema.md §5)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
NOW = sa.text("now()")
TRUE = sa.text("true")
GEN_UUID = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "actors",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("importance_tier", sa.String(32), server_default="background", nullable=False),
        sa.Column("current_location_id", sa.UUID(), nullable=True),
        sa.Column("current_scene_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.Column("mechanical_profile", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("behavior_profile", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("tactical_competence", sa.String(32), server_default="trained", nullable=False),
        sa.Column("alive", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("updated_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.ForeignKeyConstraint(["current_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id"),
    )
    op.create_index("ix_actors_location", "actors", ["current_location_id"])
    op.create_index("ix_actors_scene", "actors", ["current_scene_id"])

    op.create_table(
        "actor_controllers",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("controller_type", sa.String(16), nullable=False),
        sa.Column("user_key", sa.Text(), nullable=True),
        sa.Column("valid_from_event_id", sa.UUID(), nullable=False),  # FK added in 0004
        sa.Column("valid_until_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_actor_controllers_active",
        "actor_controllers",
        ["actor_id"],
        unique=True,
        postgresql_where=sa.text("valid_until_event_id IS NULL"),
    )

    op.create_table(
        "factions",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ideology", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("resources", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("capabilities", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("territory", JSONB, server_default=EMPTY, nullable=False),
        sa.Column(
            "simulation_priority", sa.Numeric(4, 3), server_default=sa.text("0.5"), nullable=False
        ),
        sa.Column("active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("created_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_factions_campaign", "factions", ["campaign_id"])

    op.create_table(
        "faction_memberships",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("faction_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("joined_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.Column("left_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["faction_id"], ["factions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_faction_memberships_actor", "faction_memberships", ["actor_id"])

    op.create_table(
        "parties",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("shared_resources", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("shared_reputation", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("created_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parties_campaign", "parties", ["campaign_id"])

    op.create_table(
        "party_memberships",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("party_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("joined_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.Column("left_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_party_memberships_active",
        "party_memberships",
        ["party_id", "actor_id"],
        unique=True,
        postgresql_where=sa.text("left_event_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_party_memberships_active",
        table_name="party_memberships",
        postgresql_where=sa.text("left_event_id IS NULL"),
    )
    op.drop_table("party_memberships")
    op.drop_index("ix_parties_campaign", table_name="parties")
    op.drop_table("parties")
    op.drop_index("ix_faction_memberships_actor", table_name="faction_memberships")
    op.drop_table("faction_memberships")
    op.drop_index("ix_factions_campaign", table_name="factions")
    op.drop_table("factions")
    op.drop_index(
        "uq_actor_controllers_active",
        table_name="actor_controllers",
        postgresql_where=sa.text("valid_until_event_id IS NULL"),
    )
    op.drop_table("actor_controllers")
    op.drop_index("ix_actors_scene", table_name="actors")
    op.drop_index("ix_actors_location", table_name="actors")
    op.drop_table("actors")
