"""Entity, Location, LocationEdge (database-schema.md §4; migration 0002)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.models.base import (
    Base,
    created_at_col,
    jsonb_col,
    updated_at_col,
    uuid_pk,
)


class Entity(Base):
    """Stable identity for every meaningful persistent fictional object.

    Names are mutable properties, never identifiers (world-memory §3).
    """

    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_name: Mapped[str | None] = mapped_column(Text)
    lifecycle_state: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="active"
    )
    importance_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="background"
    )
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_entities_created_event")
    )
    established_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_entities_established_event")
    )
    # Column is named `metadata`; the attribute avoids clashing with Base.metadata.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        Index("ix_entities_campaign_type", "campaign_id", "entity_type"),
        Index("ix_entities_campaign_name", "campaign_id", "canonical_name"),
    )


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    location_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    detail_level: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="outline"
    )
    properties: Mapped[dict[str, Any]] = jsonb_col()
    simulation_state: Mapped[dict[str, Any]] = jsonb_col()

    entity: Mapped[Entity] = relationship()
    parent: Mapped[Location | None] = relationship(remote_side=[id])

    __table_args__ = (Index("ix_locations_parent", "parent_location_id"),)


class LocationEdge(Base):
    __tablename__ = "location_edges"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    from_location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    travel_seconds: Mapped[int | None] = mapped_column(BigInteger)
    movement_cost: Mapped[float | None] = mapped_column(Numeric(10, 3))
    requirements: Mapped[dict[str, Any]] = jsonb_col()
    properties: Mapped[dict[str, Any]] = jsonb_col()
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_location_edges_created_event")
    )

    __table_args__ = (
        Index("ix_location_edges_from", "from_location_id"),
        Index("ix_location_edges_to", "to_location_id"),
    )
