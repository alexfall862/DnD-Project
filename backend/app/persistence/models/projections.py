"""Per-actor projections for the human client (database-schema.md §16; human-visibility §7;
migration 0011). Both are derived from one actor's perspective only: the journal from what
the character observed and heard (misconceptions preserved), the encyclopedia rebuilt from
identity knowledge and beliefs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, updated_at_col, uuid_pk


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("timelines.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="session")
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    from_sequence: Mapped[int | None] = mapped_column(BigInteger)
    to_sequence: Mapped[int | None] = mapped_column(BigInteger)
    game_tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_runs.id"))
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_journal_entries_actor", "actor_id", "created_at"),)


class EncyclopediaEntry(Base):
    __tablename__ = "encyclopedia_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("timelines.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # person|place|thing|other
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    knowledge: Mapped[dict[str, Any]] = jsonb_col()  # {"known": [...], "suspected": [...], ...}
    last_updated_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("actor_id", "entity_id", name="uq_encyclopedia_actor_entity"),
    )
