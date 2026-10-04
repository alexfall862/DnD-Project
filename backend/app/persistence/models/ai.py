"""AI observability (database-schema.md §15) and turn telemetry (turn-budget §7);
migration 0009.

Non-authoritative: excluded from state hashing. Every model call leaves a ModelRun with the
exact ContextSnapshot it received, each ContextItem's authorization result, the raw and
structured output, validation, latency and tokens.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk


class ContextSnapshot(Base):
    __tablename__ = "context_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    authorization_scope: Mapped[dict[str, Any]] = jsonb_col()
    rendered_context: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    stable_prefix_chars: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_context_snapshots_actor", "actor_id"),)


class ContextItem(Base):
    __tablename__ = "context_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("context_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str | None] = mapped_column(Text)
    owner_actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    retrieval_score: Mapped[float | None] = mapped_column(Numeric(6, 4))
    authorization: Mapped[str] = mapped_column(String(16), nullable=False)  # allowed|denied|public
    section: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (Index("ix_context_items_snapshot", "snapshot_id"),)


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE")
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    profile: Mapped[str] = mapped_column(String(32), nullable=False)
    model_requested: Mapped[str] = mapped_column(Text, nullable=False)
    model_echo: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    prompt_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    context_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("context_snapshots.id")
    )
    parameters: Mapped[dict[str, Any]] = jsonb_col()
    raw_output: Mapped[str | None] = mapped_column(Text)
    structured_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    validation: Mapped[dict[str, Any]] = jsonb_col()
    status: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # ok|repaired|invalid|failed|aborted
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = created_at_col()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_model_runs_turn", "turn_id"),
        Index("ix_model_runs_campaign_role", "campaign_id", "role"),
    )


class DecisionTrace(Base):
    __tablename__ = "decision_traces"

    id: Mapped[uuid.UUID] = uuid_pk()
    model_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    eligible_goals: Mapped[dict[str, Any]] = jsonb_col("[]")
    relevant_beliefs: Mapped[dict[str, Any]] = jsonb_col("[]")
    relevant_memories: Mapped[dict[str, Any]] = jsonb_col("[]")
    relationships: Mapped[dict[str, Any]] = jsonb_col("[]")
    mechanics: Mapped[dict[str, Any]] = jsonb_col()
    selected_intent: Mapped[dict[str, Any]] = jsonb_col()
    decision_summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


class TurnMetrics(Base):
    __tablename__ = "turn_metrics"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE")
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    wall_ms_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ms_to_first_output: Mapped[int | None] = mapped_column(Integer)
    ms_to_first_narration_token: Mapped[int | None] = mapped_column(Integer)
    sync_model_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    background_model_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    calls_by_role: Mapped[dict[str, Any]] = jsonb_col()
    prompt_tokens_total: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    completion_tokens_total: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    max_context_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    degradation_steps: Mapped[dict[str, Any]] = jsonb_col("[]")
    budget_breached: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    claim_extractor_invoked: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    belief_processor_scheduled: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_turn_metrics_campaign", "campaign_id", "created_at"),)
