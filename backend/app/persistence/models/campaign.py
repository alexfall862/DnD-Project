"""Campaign, Timeline, WorldClock (database-schema.md §2–§3; migration 0001)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.models.base import (
    Base,
    created_at_col,
    jsonb_col,
    updated_at_col,
    uuid_pk,
)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    creation_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    campaign_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="sandbox")
    active_timeline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("timelines.id", use_alter=True, name="fk_campaigns_active_timeline")
    )
    ruleset_key: Mapped[str] = mapped_column(Text, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict[str, Any]] = jsonb_col()
    generation_brief: Mapped[dict[str, Any]] = jsonb_col()
    world_version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    timelines: Mapped[list[Timeline]] = relationship(
        back_populates="campaign", foreign_keys="Timeline.campaign_id"
    )

    __table_args__ = (Index("ix_campaigns_status", "status"),)


class Timeline(Base):
    __tablename__ = "timelines"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, default="main")
    parent_timeline_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("timelines.id"))
    # FK to events is added in migration 0004 (events table does not exist yet in 0001).
    branch_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_timelines_branch_event")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    next_event_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = created_at_col()

    campaign: Mapped[Campaign] = relationship(
        back_populates="timelines", foreign_keys=[campaign_id]
    )
    world_clock: Mapped[WorldClock] = relationship(back_populates="timeline", uselist=False)

    __table_args__ = (Index("ix_timelines_campaign", "campaign_id"),)


class WorldClock(Base):
    __tablename__ = "world_clocks"

    timeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), primary_key=True
    )
    current_tick: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    calendar_definition: Mapped[dict[str, Any]] = jsonb_col()
    time_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="action_driven"
    )
    real_time_anchor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    game_tick_anchor: Mapped[int | None] = mapped_column(BigInteger)
    time_scale: Mapped[float | None] = mapped_column()
    updated_at: Mapped[datetime] = updated_at_col()

    timeline: Mapped[Timeline] = relationship(back_populates="world_clock")
