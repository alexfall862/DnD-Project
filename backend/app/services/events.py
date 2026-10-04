"""EventTransaction — the only legal way to change authoritative state.

Implements database-schema.md §18–§19 (version allocation, sequence allocation):

1. lock the campaign row, read `world_version`;
2. lock the timeline row (serialises writers per timeline) and its world clock;
3. every `emit()` reserves the next sequence number and inserts an Event stamped with
   `world_version_after = base + 1`;
4. callers mutate projections inside the same `async with` block;
5. on exit: campaign `world_version` += 1, touched scenes `version` += 1, commit.
   Any exception rolls everything back — no orphan events, no unexplained projections.

A transaction that mutates nothing and emits nothing is a no-op; one that would commit
projection changes without an event raises `EventTransactionError`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from types import TracebackType
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events import EventPayload
from app.persistence.models import (
    Campaign,
    Event,
    EventEntity,
    Scene,
    Timeline,
    WorldClock,
)

UNIT_OF_WORK = "unit_of_work"  # session.info flag: EventTransactions flush instead of commit


class unit_of_work:  # noqa: N801 - used as a context manager
    """Group many EventTransactions into one database transaction (seeding, fixtures): each
    still allocates its events and bumps versions, but the commit happens once at the end and
    any failure rolls back everything. Never used on the play path."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> unit_of_work:
        self.session.info[UNIT_OF_WORK] = True
        if not self.session.in_transaction():
            await self.session.begin()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self.session.info.pop(UNIT_OF_WORK, None)
        if exc_type is not None:
            await self.session.rollback()
            return False
        await self.session.commit()
        return False


class EventTransactionError(RuntimeError):
    pass


class EventTransaction:
    def __init__(
        self,
        session: AsyncSession,
        campaign_id: uuid.UUID,
        timeline_id: uuid.UUID,
        *,
        created_by_type: str = "engine",
        created_by_id: uuid.UUID | None = None,
    ) -> None:
        self.session = session
        self.campaign_id = campaign_id
        self.timeline_id = timeline_id
        self.created_by_type = created_by_type
        self.created_by_id = created_by_id
        self.events: list[Event] = []
        self._touched_scenes: dict[uuid.UUID, Scene] = {}
        self.campaign: Campaign
        self.timeline: Timeline
        self.clock: WorldClock
        self.base_world_version: int
        self.world_version_after: int

    # -- lifecycle -------------------------------------------------------------------------

    async def __aenter__(self) -> EventTransaction:
        s = self.session
        if not s.in_transaction():
            await s.begin()
        # populate_existing: re-read even if cached, so we see the row as locked/committed.
        self.campaign = (
            await s.execute(
                select(Campaign)
                .where(Campaign.id == self.campaign_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        self.timeline = (
            await s.execute(
                select(Timeline)
                .where(Timeline.id == self.timeline_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        if self.timeline.campaign_id != self.campaign_id:
            raise EventTransactionError("timeline does not belong to campaign")
        self.clock = (
            await s.execute(
                select(WorldClock)
                .where(WorldClock.timeline_id == self.timeline_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        self.base_world_version = self.campaign.world_version
        self.world_version_after = self.base_world_version + 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        s = self.session
        deferred = bool(s.info.get(UNIT_OF_WORK))
        if exc_type is not None:
            await s.rollback()
            return False
        if not self.events:
            if s.dirty or s.new or s.deleted:
                await s.rollback()
                raise EventTransactionError("projection changes without an Event are forbidden")
            if not deferred:
                await s.rollback()
            return False
        self.campaign.world_version = self.world_version_after
        for scene in self._touched_scenes.values():
            scene.version += 1
        if deferred:
            await s.flush()  # the enclosing unit of work commits or rolls back as a whole
        else:
            await s.commit()
        return False

    # -- emitting ----------------------------------------------------------------------------

    async def emit(
        self,
        payload: EventPayload,
        *,
        game_tick: int | None = None,
        scene: Scene | None = None,
        location_id: uuid.UUID | None = None,
        cause: Event | None = None,
        entities: Iterable[tuple[uuid.UUID, str]] = (),
        extra: dict[str, Any] | None = None,
    ) -> Event:
        """Append one event. `entities` are (entity_id, role) pairs for `event_entities`."""
        sequence = self.timeline.next_event_sequence
        self.timeline.next_event_sequence = sequence + 1
        if scene is not None:
            self._touched_scenes[scene.id] = scene
        data = payload.model_dump(mode="json")
        if extra:
            data.update(extra)
        event = Event(
            campaign_id=self.campaign_id,
            timeline_id=self.timeline_id,
            sequence_number=sequence,
            event_type=type(payload).event_type,
            payload_version=type(payload).payload_version,
            game_tick=self.clock.current_tick if game_tick is None else game_tick,
            scene_id=scene.id if scene is not None else None,
            location_id=location_id,
            cause_event_id=cause.id if cause is not None else None,
            created_by_type=self.created_by_type,
            created_by_id=self.created_by_id,
            payload=data,
            world_version_after=self.world_version_after,
        )
        self.session.add(event)
        await self.session.flush()
        for entity_id, role in entities:
            self.session.add(EventEntity(event_id=event.id, entity_id=entity_id, role=role))
        self.events.append(event)
        return event

    def touch_scene(self, scene: Scene) -> None:
        """Mark a scene's projection as changed so its version is bumped on commit."""
        self._touched_scenes[scene.id] = scene
