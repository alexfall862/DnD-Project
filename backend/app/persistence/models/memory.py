"""Durable subjective memory (database-schema.md §12 memories/memory_sources; migration 0008).

A memory belongs to one actor, derives from that actor's observations (lineage in
`memory_sources`), and may be false. `entity_ids` supports structured-first retrieval; the
embedding is a secondary ranking signal only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, uuid_pk

EMBEDDING_DIMENSIONS = 1024


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    subjective_summary: Mapped[str] = mapped_column(Text, nullable=False)
    emotional_interpretation: Mapped[str | None] = mapped_column(Text)
    salience: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("0.5")
    )
    emotional_weight: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("0.0")
    )
    specificity: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("1.0")
    )
    accessibility: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("1.0")
    )
    is_core: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="detailed"
    )  # detailed|compressed|fuzzy|inaccessible|altered
    parent_memory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memories.id")
    )  # set on compressed children
    entity_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'")
    )
    created_tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_recalled_tick: Mapped[int | None] = mapped_column(BigInteger)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_memories_actor_status", "actor_id", "status"),
        Index("ix_memories_entity_ids", "entity_ids", postgresql_using="gin"),
    )


class MemorySource(Base):
    __tablename__ = "memory_sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    observation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("observations.id"))
    source_memory_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memories.id"))
    source_role: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # observation|compressed_from|seed

    __table_args__ = (Index("ix_memory_sources_memory", "memory_id"),)
