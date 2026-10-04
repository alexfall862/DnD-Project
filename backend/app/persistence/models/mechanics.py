"""Mechanical state projections: resources, conditions, items, documents
(database-schema.md §9; migration 0006)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk


class ResourceStateRow(Base):
    __tablename__ = "resource_states"

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    resource_key: Mapped[str] = mapped_column(Text, nullable=False)
    current: Mapped[int] = mapped_column(Integer, nullable=False)
    max_value: Mapped[int | None] = mapped_column(Integer)  # cached computed maximum
    state: Mapped[dict[str, Any]] = jsonb_col()
    last_changed_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))

    __table_args__ = (
        UniqueConstraint("entity_id", "resource_key", name="uq_resource_states_entity_key"),
    )


class ConditionInstanceRow(Base):
    __tablename__ = "condition_instances"

    id: Mapped[uuid.UUID] = uuid_pk()
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    condition_key: Mapped[str] = mapped_column(Text, nullable=False)
    instance_key: Mapped[str] = mapped_column(String(32), nullable=False)
    intensity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    source_ref: Mapped[str | None] = mapped_column(Text)  # e.g. condition key / effect source
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    start_tick: Mapped[int | None] = mapped_column(BigInteger)
    expiry_tick: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    ended_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    parameters: Mapped[dict[str, Any]] = jsonb_col()

    __table_args__ = (
        Index("ix_condition_instances_target", "target_entity_id", "status"),
        UniqueConstraint(
            "target_entity_id", "instance_key", name="uq_condition_instances_instance"
        ),
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    template_key: Mapped[str | None] = mapped_column(Text)  # ruleset equipment key
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="gear")
    description: Mapped[str | None] = mapped_column(Text)
    mechanical_snapshot: Mapped[dict[str, Any]] = jsonb_col()
    condition_state: Mapped[dict[str, Any]] = jsonb_col()
    owner_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    possessor_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    container_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    zone_key: Mapped[str | None] = mapped_column(String(64))
    hidden_properties: Mapped[dict[str, Any]] = jsonb_col()
    public_properties: Mapped[dict[str, Any]] = jsonb_col()
    provenance: Mapped[dict[str, Any]] = jsonb_col()
    # A concealed item lies in a location/zone but is not visible until a successful search
    # reveals it (Milestone 07); it is excluded from scene loads, candidates and observations.
    concealed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    destroyed_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))

    __table_args__ = (
        Index("ix_items_possessor", "possessor_entity_id"),
        Index("ix_items_location", "location_id"),
    )


class ItemHistory(Base):
    __tablename__ = "item_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = jsonb_col()
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_item_history_item", "item_id"),)


class Document(Base):
    """Immutable original text (world-memory §15)."""

    __tablename__ = "documents"

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    author_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    creation_tick: Mapped[int | None] = mapped_column(BigInteger)
    language: Mapped[str] = mapped_column(String(32), nullable=False, server_default="common")
    cipher: Mapped[str | None] = mapped_column(String(32))
    conveys: Mapped[dict[str, Any]] = jsonb_col("[]")  # communication-and-knowledge §3
