"""Architectural invariants for the event ledger (testing-strategy.md §7, §10–§11;
database-schema.md §22).

- projection mutation and event creation are atomic (rollback leaves nothing);
- event order is unique and deterministic per timeline, also under concurrency;
- a transaction cannot commit projection changes without an event;
- scenes.local_tick never exceeds the world clock (DB trigger).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.events import TimeAdvanced
from app.persistence.models import Campaign, Event, Scene, Timeline
from app.services.events import EventTransaction, EventTransactionError
from app.services.world import WorldService

pytestmark = [pytest.mark.integration, pytest.mark.invariants]


async def _campaign(session: AsyncSession):
    svc = WorldService(session)
    return svc, await svc.create_campaign(
        "inv", ruleset_key="core_adventure", ruleset_version="0.1", engine_version="test"
    )


async def test_rollback_leaves_no_orphan_event_or_projection(session: AsyncSession) -> None:
    svc, h = await _campaign(session)
    before_version = (await session.get(Campaign, h.campaign_id)).world_version  # type: ignore[union-attr]
    before_count = (
        await session.execute(
            select(func.count()).select_from(Event).where(Event.timeline_id == h.timeline_id)
        )
    ).scalar_one()

    with pytest.raises(RuntimeError, match="boom"):
        async with EventTransaction(session, h.campaign_id, h.timeline_id) as tx:
            await tx.emit(TimeAdvanced(from_tick=0, to_tick=10, seconds=10, reason="test"))
            tx.clock.current_tick = 10  # projection mutation...
            raise RuntimeError("boom")  # ...then failure before commit

    session.expire_all()
    campaign = await session.get(Campaign, h.campaign_id)
    assert campaign is not None and campaign.world_version == before_version
    after_count = (
        await session.execute(
            select(func.count()).select_from(Event).where(Event.timeline_id == h.timeline_id)
        )
    ).scalar_one()
    assert after_count == before_count
    assert (await svc.clock(h)).current_tick == 0
    timeline = await session.get(Timeline, h.timeline_id)
    assert timeline is not None and timeline.next_event_sequence == before_count + 1


async def test_projection_change_without_event_is_rejected(session: AsyncSession) -> None:
    _, h = await _campaign(session)
    with pytest.raises(EventTransactionError):
        async with EventTransaction(session, h.campaign_id, h.timeline_id) as tx:
            tx.clock.current_tick = 999  # mutate without emitting
    session.expire_all()
    clock = await WorldService(session).clock(h)
    assert clock.current_tick == 0


async def test_concurrent_writers_get_unique_contiguous_sequences(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _, h = await _campaign(session)

    async def writer(n: int) -> None:
        async with session_factory() as s:
            svc = WorldService(s)
            for _ in range(n):
                await svc.advance_time(h, 1, reason="concurrent")

    await asyncio.gather(*(writer(5) for _ in range(4)))

    seqs = (
        (
            await session.execute(
                select(Event.sequence_number)
                .where(Event.timeline_id == h.timeline_id)
                .order_by(Event.sequence_number)
            )
        )
        .scalars()
        .all()
    )
    assert seqs == list(range(1, 22))  # campaign.created + 20 advances
    versions = (
        (
            await session.execute(
                select(Event.world_version_after)
                .where(Event.timeline_id == h.timeline_id)
                .order_by(Event.sequence_number)
            )
        )
        .scalars()
        .all()
    )
    assert versions == sorted(versions) and len(set(versions)) == 21
    session.expire_all()
    assert (await WorldService(session).clock(h)).current_tick == 20


async def test_duplicate_sequence_is_rejected_by_database(session: AsyncSession) -> None:
    _, h = await _campaign(session)
    # sequence 1 already exists on this timeline (campaign.created)
    with pytest.raises(DBAPIError):
        await session.execute(
            text(
                "INSERT INTO events (campaign_id, timeline_id, sequence_number, event_type, "
                "game_tick, created_by_type, world_version_after) "
                "VALUES (:c, :t, 1, 'dup', 0, 'test', 1)"
            ),
            {"c": h.campaign_id, "t": h.timeline_id},
        )
    await session.rollback()


async def test_scene_local_tick_cannot_exceed_world_clock(session: AsyncSession) -> None:
    svc, h = await _campaign(session)
    loc = await svc.create_location(h, "Here")
    scene = await svc.start_scene(h, location_id=loc.id)
    scene_id: uuid.UUID = scene.id
    with pytest.raises(DBAPIError, match="may not exceed world clock"):
        await session.execute(
            text("UPDATE scenes SET local_tick = 5 WHERE id = :id"), {"id": scene_id}
        )
    await session.rollback()
    reloaded = await session.get(Scene, scene_id)
    assert reloaded is not None and reloaded.local_tick == 0
