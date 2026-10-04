"""JobQueue — the PostgreSQL-backed background queue (implementation-plan §16; orchestration
§37). Enqueue from any service; a worker claims one job at a time with `FOR UPDATE SKIP
LOCKED`, so several workers never run the same job. Failures retry with backoff until
`max_attempts`, then stay `failed` with `last_error`. Jobs are optional work: nothing here
is authoritative campaign state and a job's failure must never roll back a turn.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.jobs import BackgroundJob

JOB_TYPES = (
    "memory.embedding",
    "memory.process",
    "journal.update",
    "simulation.advance",
    "world.materialize",
    "campaign.generate",
)
DEFAULT_PRIORITY = {
    "memory.process": 70,
    "journal.update": 60,
    "simulation.advance": 50,
    "memory.embedding": 30,
    "world.materialize": 20,
    "campaign.generate": 40,
}
BACKOFF_SECONDS = (5, 30, 120, 600)


def _now() -> datetime:
    return datetime.now(UTC)


class JobQueue:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        job_type: str,
        *,
        campaign_id: uuid.UUID | None,
        timeline_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        priority: int | None = None,
        not_before: datetime | None = None,
        max_attempts: int = 3,
        dedupe: bool = True,
    ) -> BackgroundJob:
        """Add a job. With `dedupe`, an identical queued job (type, subject, payload) is
        returned instead of a duplicate. The caller's transaction commits it."""
        if job_type not in JOB_TYPES:
            raise ValueError(f"unknown job type {job_type!r}")
        payload = dict(payload or {})
        if dedupe:
            existing = (
                await self.session.execute(
                    select(BackgroundJob).where(
                        BackgroundJob.job_type == job_type,
                        BackgroundJob.campaign_id == campaign_id,
                        BackgroundJob.subject_id == subject_id,
                        BackgroundJob.status == "queued",
                    )
                )
            ).scalars()
            for row in existing:
                if row.payload == payload:
                    return row
        job = BackgroundJob(
            campaign_id=campaign_id,
            timeline_id=timeline_id,
            job_type=job_type,
            subject_id=subject_id,
            priority=priority if priority is not None else DEFAULT_PRIORITY.get(job_type, 50),
            payload=payload,
            status="queued",
            max_attempts=max_attempts,
            not_before=not_before,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def claim(
        self,
        worker_id: str,
        *,
        job_types: tuple[str, ...] | None = None,
        campaign_id: uuid.UUID | None = None,
    ) -> BackgroundJob | None:
        """Claim the most urgent runnable job, or None. Commits the claim so other workers
        see it immediately; the row lock (`SKIP LOCKED`) keeps claims disjoint."""
        if not self.session.in_transaction():
            await self.session.begin()
        q = (
            select(BackgroundJob)
            .where(
                BackgroundJob.status == "queued",
                (BackgroundJob.not_before.is_(None)) | (BackgroundJob.not_before <= _now()),
            )
            .order_by(BackgroundJob.priority.desc(), BackgroundJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job_types:
            q = q.where(BackgroundJob.job_type.in_(job_types))
        if campaign_id is not None:
            q = q.where(BackgroundJob.campaign_id == campaign_id)
        job = (await self.session.execute(q)).scalar_one_or_none()
        if job is None:
            await self.session.rollback()
            return None
        job.status = "running"
        job.claimed_by = worker_id
        job.claimed_at = _now()
        job.attempts += 1
        await self.session.commit()
        return job

    async def complete(self, job: BackgroundJob, result: dict[str, Any] | None = None) -> None:
        job.status = "succeeded"
        job.result = result or {}
        job.finished_at = _now()
        job.last_error = None
        await self.session.commit()

    async def fail(self, job: BackgroundJob, error: str) -> None:
        """Retry with backoff while attempts remain; otherwise the job stays failed."""
        job.last_error = error[:4000]
        if job.attempts < job.max_attempts:
            delay = BACKOFF_SECONDS[min(job.attempts - 1, len(BACKOFF_SECONDS) - 1)]
            job.status = "queued"
            job.not_before = _now() + timedelta(seconds=delay)
        else:
            job.status = "failed"
            job.finished_at = _now()
        await self.session.commit()

    async def cancel(self, job_id: uuid.UUID) -> None:
        job = await self.session.get(BackgroundJob, job_id)
        if job is not None and job.status == "queued":
            job.status = "cancelled"
            job.finished_at = _now()
            await self.session.commit()

    async def pending(self, campaign_id: uuid.UUID | None = None) -> list[BackgroundJob]:
        q = select(BackgroundJob).where(BackgroundJob.status.in_(("queued", "running")))
        if campaign_id is not None:
            q = q.where(BackgroundJob.campaign_id == campaign_id)
        return list((await self.session.execute(q.order_by(BackgroundJob.created_at))).scalars())

    async def recover_stale(self, *, older_than_s: int = 900) -> int:
        """A worker that died mid-job leaves it `running`; re-queue such jobs."""
        cutoff = _now() - timedelta(seconds=older_than_s)
        rows = (
            await self.session.execute(
                select(BackgroundJob).where(
                    BackgroundJob.status == "running", BackgroundJob.claimed_at < cutoff
                )
            )
        ).scalars()
        n = 0
        for job in rows:
            job.status = "queued"
            job.claimed_by = None
            n += 1
        if n:
            await self.session.commit()
        return n


__all__ = ["JobQueue", "JOB_TYPES", "text"]
