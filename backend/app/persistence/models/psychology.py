"""Actor psychology: AI profiles (autonomy), emotion states, goals, goal targets, plans
(database-schema.md §10, §12; world-memory §4, §12; migration 0010).

Goals and emotions are projections changed only through events (goal.created/updated,
emotion.changed). Autonomy is configuration; the engine enforces it after generation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, updated_at_col, uuid_pk


class ActorAIProfile(Base):
    __tablename__ = "actor_ai_profiles"

    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id", ondelete="CASCADE"), primary_key=True
    )
    autonomy_profile: Mapped[dict[str, Any]] = jsonb_col()  # domain -> level
    decision_preferences: Mapped[dict[str, Any]] = jsonb_col()
    tactical_preferences: Mapped[dict[str, Any]] = jsonb_col()
    preferred_model_profile: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = updated_at_col()


class EmotionState(Base):
    __tablename__ = "emotion_states"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    emotion_key: Mapped[str] = mapped_column(String(32), nullable=False)
    intensity: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    start_tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expiry_tick: Mapped[int | None] = mapped_column(BigInteger)
    decay_rule: Mapped[str] = mapped_column(String(32), nullable=False, server_default="linear")
    resolution_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_emotion_states_actor_status", "actor_id", "status"),)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    owner_type: Mapped[str] = mapped_column(String(16), nullable=False)  # actor|faction|party
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parent_goal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("goals.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    goal_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="personal")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )  # active|succeeded|failed|abandoned|superseded
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, server_default="private")
    progress: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, server_default="0")
    deadline_tick: Mapped[int | None] = mapped_column(BigInteger)
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    resolved_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_goals_owner", "owner_type", "owner_id", "status"),)


class GoalTarget(Base):
    __tablename__ = "goal_targets"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), primary_key=True)
    target_role: Mapped[str] = mapped_column(String(32), primary_key=True, server_default="subject")

    __table_args__ = (Index("ix_goal_targets_entity", "entity_id"),)


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = uuid_pk()
    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    steps: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    updated_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = created_at_col()
