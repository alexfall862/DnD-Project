"""Milestone 08: the PostgreSQL-backed job queue and worker (implementation-plan §16).
Claims are disjoint across sessions, failures retry with backoff and then stay failed, and a
failing optional job never changes authoritative campaign state."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import worker
from app.ai.providers import FakeModelProvider
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import Campaign, Event
from app.persistence.models.jobs import BackgroundJob
from app.seeds.frostbridge_tavern import seed_tavern
from app.services.jobs import JobQueue

pytestmark = pytest.mark.integration


async def test_claims_are_disjoint_and_ordered_by_priority(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    w = await seed_tavern(session, name="jobs-claim", engine_version="test")
    q = JobQueue(session)
    low = await q.enqueue(
        "memory.embedding", campaign_id=w.h.campaign_id, timeline_id=w.h.timeline_id, priority=10
    )
    high = await q.enqueue(
        "memory.embedding",
        campaign_id=w.h.campaign_id,
        timeline_id=w.h.timeline_id,
        priority=90,
        payload={"batch": 8},
    )
    dup = await q.enqueue(
        "memory.embedding",
        campaign_id=w.h.campaign_id,
        timeline_id=w.h.timeline_id,
        priority=90,
        payload={"batch": 8},
    )
    assert dup.id == high.id  # deduplicated while queued
    await session.commit()
    async with session_factory() as a, session_factory() as b:
        cid = w.h.campaign_id
        first = await JobQueue(a).claim("worker-a", campaign_id=cid)
        second = await JobQueue(b).claim("worker-b", campaign_id=cid)
        assert first is not None and second is not None
        assert {first.id, second.id} == {low.id, high.id} and first.id == high.id
        assert first.status == "running" and first.attempts == 1
        assert await JobQueue(a).claim("worker-a", campaign_id=cid) is None
        await JobQueue(a).complete(first, {"embedded": 0})
        await JobQueue(b).fail(second, "boom")
    done = await session.get(BackgroundJob, high.id, populate_existing=True)
    retry = await session.get(BackgroundJob, low.id, populate_existing=True)
    assert done.status == "succeeded" and done.result == {"embedded": 0}
    assert retry.status == "queued" and retry.not_before is not None and "boom" in retry.last_error


async def test_failed_optional_job_leaves_campaign_state_untouched(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    w = await seed_tavern(session, name="jobs-fail", engine_version="test")
    q = JobQueue(session)
    job = await q.enqueue(
        "world.materialize",  # no subject: the handler raises, as any optional job may
        campaign_id=w.h.campaign_id,
        timeline_id=w.h.timeline_id,
        max_attempts=1,
    )
    ok = await q.enqueue(
        "memory.embedding", campaign_id=w.h.campaign_id, timeline_id=w.h.timeline_id
    )
    await session.commit()
    before_version = (await session.get(Campaign, w.h.campaign_id)).world_version
    before_events = len(
        (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    settings = Settings(a9_token="", narrator_enabled=False)
    engine = RulesEngine.load("core_adventure")
    ran = []
    while True:
        j = await worker.run_once(
            session_factory,
            settings,
            engine=engine,
            provider=FakeModelProvider(),
            embedder=None,
            worker_id="test-worker",
            campaign_id=w.h.campaign_id,
        )
        if j is None:
            break
        ran.append(j)
    assert {j.id for j in ran} == {job.id, ok.id}
    failed = await session.get(BackgroundJob, job.id, populate_existing=True)
    assert failed.status == "failed" and "ValueError" in failed.last_error
    embedded = await session.get(BackgroundJob, ok.id, populate_existing=True)
    assert embedded.status == "succeeded" and embedded.result == {"embedded": 0}
    campaign = await session.get(Campaign, w.h.campaign_id, populate_existing=True)
    assert campaign.world_version == before_version
    after_events = len(
        (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    assert after_events == before_events


async def test_unknown_job_type_is_refused_at_enqueue(session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await JobQueue(session).enqueue("nonsense.job", campaign_id=None)
