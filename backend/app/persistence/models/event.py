"""Append-only event ledger, transcript archive, scheduled events
(database-schema.md §7–§8; migration 0004).

Events are never rewritten in ordinary play. `payload_version` is recorded but no upcasters
exist before v0.1 (DECISIONS.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    game_tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    cause_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = jsonb_col()
    world_version_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("timeline_id", "sequence_number", name="uq_events_timeline_sequence"),
        Index("ix_events_campaign_type", "campaign_id", "event_type"),
        Index("ix_events_timeline_tick", "timeline_id", "game_tick"),
        Index("ix_events_scene", "scene_id"),
    )


class EventEntity(Base):
    """Join table so common history queries do not scan JSON payloads."""

    __tablename__ = "event_entities"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # actor|target|item|observer|...

    __table_args__ = (
        Index("ix_event_entities_entity", "entity_id"),
        Index("ix_event_entities_event", "event_id"),
    )


class TranscriptMessage(Base):
    """Raw verbatim archive, separate from canonical events."""

    __tablename__ = "transcript_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id"))
    speaker_actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    game_tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # human|ai|engine
    turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_transcript_scene", "scene_id"),
        Index("ix_transcript_turn", "turn_id"),
    )


class TranscriptRecipient(Base):
    """Intended recipients only; overhearing is represented through observations."""

    __tablename__ = "transcript_recipients"

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcript_messages.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (Index("ix_transcript_recipients_message", "message_id"),)


class ScheduledEvent(Base):
    __tablename__ = "scheduled_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = jsonb_col()
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    processed_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_scheduled_events_due", "timeline_id", "status", "scheduled_tick"),
    )
