"""Scenes and participants (database-schema.md §6; migration 0004).

`local_tick` may never exceed the timeline's world clock (time-accounting.md §3); migration
0004 installs a trigger that enforces it at the database level.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.models.base import Base, jsonb_col, uuid_pk


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    scene_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    start_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_scenes_start_event")
    )
    end_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_scenes_end_event")
    )
    start_tick: Mapped[int | None] = mapped_column(BigInteger)
    end_tick: Mapped[int | None] = mapped_column(BigInteger)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    local_tick: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    merged_from: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    state: Mapped[dict[str, Any]] = jsonb_col()

    participants: Mapped[list[SceneParticipant]] = relationship(back_populates="scene")

    __table_args__ = (
        Index("ix_scenes_timeline_status", "timeline_id", "status"),
        Index("ix_scenes_location", "location_id"),
    )


class SceneParticipant(Base):
    __tablename__ = "scene_participants"

    id: Mapped[uuid.UUID] = uuid_pk()
    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), nullable=False
    )
    zone_key: Mapped[str | None] = mapped_column(String(64))
    position_state: Mapped[dict[str, Any]] = jsonb_col()
    joined_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_scene_participants_joined_event")
    )
    left_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", use_alter=True, name="fk_scene_participants_left_event")
    )

    scene: Mapped[Scene] = relationship(back_populates="participants")

    __table_args__ = (
        Index(
            "uq_scene_participants_active",
            "scene_id",
            "actor_id",
            unique=True,
            postgresql_where=text("left_event_id IS NULL"),
        ),
        Index("ix_scene_participants_actor", "actor_id"),
    )
