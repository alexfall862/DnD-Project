"""Situations: objective, recorded circumstances of a place or a person (DECISIONS 10d).

An obstacle ("the guards hold everyone for inspection"), a status ("inspected", "wanted"),
a promise ("the older guard agreed to let the party through"), a pressure clock, an alarm,
a price, a debt or someone accompanying the party. Situations are objective truth, like
Facts: the engine commits them with `situation.*` events, and each actor perceives only the
public ones where they are, or the ones about them (`SituationService.visible_to`).
Narration never creates or changes one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk

SITUATION_KINDS = (
    "obstacle",
    "status",
    "commitment",
    "clock",
    "alarm",
    "price",
    "debt",
    "follower",
)


class Situation(Base):
    __tablename__ = "situations"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # where it holds (an obstacle, an alarm, a clock); None for one that travels with its
    # subject (a status, a promise, a debt, a follower)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE")
    )
    # whose status / promise / debt / company it is
    subject_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE")
    )
    # who enforces an obstacle (absent, distracted or agreed: it does not block)
    holder_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("actors.id", ondelete="SET NULL")
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = jsonb_col()
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, server_default="public")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    expires_tick: Mapped[int | None] = mapped_column(BigInteger)
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    closed_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_situations_location", "campaign_id", "location_id", "status"),
        Index("ix_situations_subject", "subject_actor_id", "status"),
    )
