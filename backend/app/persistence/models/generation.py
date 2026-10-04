"""Generation runs and stages (database-schema.md §17; campaign-generation §5, §26).

A run belongs to one draft campaign; each stage stores its validated World Author envelope.
Stage outputs are *proposals*, not world state: the world is built from them only when the
campaign starts, so pre-play rerolls replace outputs instead of retracting events.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, updated_at_col, uuid_pk


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )  # pending|running|ready|failed|applied
    scope: Mapped[str] = mapped_column(String(32), nullable=False, server_default="full")
    model_profile: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="deep_world_author"
    )
    brief: Mapped[dict[str, Any]] = jsonb_col()
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (Index("ix_generation_runs_campaign", "campaign_id"),)


class GenerationStage(Base):
    __tablename__ = "generation_stages"

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_runs.id", ondelete="CASCADE"), nullable=False
    )
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )  # pending|running|ready|failed|invalidated
    depends_on: Mapped[dict[str, Any]] = jsonb_col("[]")
    guidance: Mapped[str | None] = mapped_column(Text)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # the accepted envelope
    errors: Mapped[dict[str, Any]] = jsonb_col("[]")
    # itemized stages: {"outline": envelope, "filled": {ref: envelope}, "failed": [ref], ...}
    progress: Mapped[dict[str, Any]] = jsonb_col()
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_runs.id"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("run_id", "stage_key", name="uq_generation_stage"),
        Index("ix_generation_stages_run", "run_id", "order_index"),
    )
