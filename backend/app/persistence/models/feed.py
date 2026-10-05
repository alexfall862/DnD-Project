"""The player's feed: each turn as it was shown to the human player (Milestone 10).

Presentation, not world state: one row per completed `/play` turn holding the focus actor's
input and the response the API returned (narration, speaker lines, visible rolls, notices).
Like `turn_metrics` it is written without an Event, because it changes no projection the
world is built from; it is exactly what that player already saw, so serving it back to the
same focus actor reveals nothing new. Branching (Milestone 12) will scope it by timeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk


class PlayerTurn(Base):
    __tablename__ = "player_turns"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE")
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    to_names: Mapped[list[str]] = jsonb_col("[]")  # whisper listeners, as the player knows them
    result: Mapped[dict[str, Any]] = jsonb_col()  # the PlayOut the API returned
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_player_turns_actor", "actor_id", "created_at"),)
