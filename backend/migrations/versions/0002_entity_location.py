"""entities, locations, location_edges (database-schema.md §4)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
NOW = sa.text("now()")
GEN_UUID = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=True),
        sa.Column("lifecycle_state", sa.String(32), server_default="active", nullable=False),
        sa.Column("importance_tier", sa.String(32), server_default="background", nullable=False),
        sa.Column("created_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.Column("established_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.Column("metadata", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entities_campaign_name", "entities", ["campaign_id", "canonical_name"])
    op.create_index("ix_entities_campaign_type", "entities", ["campaign_id", "entity_type"])

    op.create_table(
        "locations",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("parent_location_id", sa.UUID(), nullable=True),
        sa.Column("location_type", sa.String(32), nullable=False),
        sa.Column("detail_level", sa.String(32), server_default="outline", nullable=False),
        sa.Column("properties", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("simulation_state", JSONB, server_default=EMPTY, nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id"),
    )
    op.create_index("ix_locations_parent", "locations", ["parent_location_id"])

    op.create_table(
        "location_edges",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("from_location_id", sa.UUID(), nullable=False),
        sa.Column("to_location_id", sa.UUID(), nullable=False),
        sa.Column("relationship_type", sa.String(32), nullable=False),
        sa.Column("travel_seconds", sa.BigInteger(), nullable=True),
        sa.Column("movement_cost", sa.Numeric(10, 3), nullable=True),
        sa.Column("requirements", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("properties", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("created_event_id", sa.UUID(), nullable=True),  # FK added in 0004
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_location_edges_from", "location_edges", ["from_location_id"])
    op.create_index("ix_location_edges_to", "location_edges", ["to_location_id"])


def downgrade() -> None:
    op.drop_index("ix_location_edges_to", table_name="location_edges")
    op.drop_index("ix_location_edges_from", table_name="location_edges")
    op.drop_table("location_edges")
    op.drop_index("ix_locations_parent", table_name="locations")
    op.drop_table("locations")
    op.drop_index("ix_entities_campaign_type", table_name="entities")
    op.drop_index("ix_entities_campaign_name", table_name="entities")
    op.drop_table("entities")
