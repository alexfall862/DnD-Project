"""Background jobs (database-schema.md §17; implementation-plan §16): a PostgreSQL-backed queue
claimed with `FOR UPDATE SKIP LOCKED`. Jobs are optional work (embeddings, memory processing,
journals, world simulation); a failed job records its error and never touches authoritative
campaign state.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, updated_at_col, uuid_pk

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    timeline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE")
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column()  # actor / scene / plan, per job type
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    payload: Mapped[dict[str, Any]] = jsonb_col()
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any]] = jsonb_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        Index("ix_background_jobs_claim", "status", "priority", "not_before", "created_at"),
        Index("ix_background_jobs_campaign", "campaign_id", "job_type"),
        {"comment": "worker claims with FOR UPDATE SKIP LOCKED"},
    )


__all__ = ["BackgroundJob", "JOB_STATUSES", "text"]
