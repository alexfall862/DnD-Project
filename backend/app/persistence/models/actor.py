"""Actors, controllers, factions, parties (database-schema.md §5; migration 0003).

`Actor` is one mechanical representation for human PCs, AI PCs, NPCs and creatures
(Invariant 11). Who drives the actor is runtime state in `ActorController`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk
from app.persistence.models.entity import Entity


class Actor(Base):
    __tablename__ = "actors"

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)  # pc|npc|creature|...
    importance_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="background"
    )
    current_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    current_scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scenes.id", use_alter=True, name="fk_actors_current_scene")
    )
    mechanical_profile: Mapped[dict[str, Any]] = jsonb_col()
    behavior_profile: Mapped[dict[str, Any]] = jsonb_col()
    tactical_competence: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="trained"
    )
    alive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_actors_updated_event")
    )

    entity: Mapped[Entity] = relationship()
    controllers: Mapped[list[ActorController]] = relationship(back_populates="actor")

    __table_args__ = (
        Index("ix_actors_location", "current_location_id"),
        Index("ix_actors_scene", "current_scene_id"),
    )


class ActorController(Base):
    """Control history. Exactly one row per actor has `valid_until_event_id IS NULL`."""

    __tablename__ = "actor_controllers"

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), nullable=False
    )
    # human | ai | scripted | dormant
    controller_type: Mapped[str] = mapped_column(String(16), nullable=False)
    user_key: Mapped[str | None] = mapped_column(Text)
    valid_from_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_actor_controllers_from_event"),
        nullable=False,
    )
    valid_until_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_actor_controllers_until_event")
    )
    created_at: Mapped[datetime] = created_at_col()

    actor: Mapped[Actor] = relationship(back_populates="controllers")

    __table_args__ = (
        Index(
            "uq_actor_controllers_active",
            "actor_id",
            unique=True,
            postgresql_where=text("valid_until_event_id IS NULL"),
        ),
    )


class Faction(Base):
    __tablename__ = "factions"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ideology: Mapped[dict[str, Any]] = jsonb_col()
    resources: Mapped[dict[str, Any]] = jsonb_col()
    capabilities: Mapped[dict[str, Any]] = jsonb_col()
    territory: Mapped[dict[str, Any]] = jsonb_col()
    simulation_priority: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("0.5")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_factions_created_event")
    )

    __table_args__ = (Index("ix_factions_campaign", "campaign_id"),)


class FactionMembership(Base):
    __tablename__ = "faction_memberships"

    id: Mapped[uuid.UUID] = uuid_pk()
    faction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("factions.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    joined_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_faction_memberships_joined_event")
    )
    left_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_faction_memberships_left_event")
    )

    __table_args__ = (Index("ix_faction_memberships_actor", "actor_id"),)


class Party(Base):
    __tablename__ = "parties"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    shared_resources: Mapped[dict[str, Any]] = jsonb_col()
    shared_reputation: Mapped[dict[str, Any]] = jsonb_col()
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_parties_created_event")
    )

    __table_args__ = (Index("ix_parties_campaign", "campaign_id"),)


class PartyMembership(Base):
    __tablename__ = "party_memberships"

    id: Mapped[uuid.UUID] = uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parties.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str | None] = mapped_column(Text)
    joined_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_party_memberships_joined_event")
    )
    left_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_party_memberships_left_event")
    )

    __table_args__ = (
        Index(
            "uq_party_memberships_active",
            "party_id",
            "actor_id",
            unique=True,
            postgresql_where=text("left_event_id IS NULL"),
        ),
    )
