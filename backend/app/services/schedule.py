"""ScheduleService — engine-created future events with prerequisite revalidation
(database-schema.md §8 `scheduled_events`; frostbridge §19, §36–§37; GLOSSARY "Scheduled
event"). Milestone 07 ships the deterministic part: scheduling, firing when the world clock
passes `scheduled_tick`, revalidating prerequisites against *current* state, and a small table
of deterministic handlers. Anything that needs the World Simulator (shipment departure, faction
reasoning) stays `pending` for Milestone 08's worker; it is never guessed here.

Every firing commits inside the clock-advancing transaction and is recorded by a
`scheduled_event.fired` Event with the outcome (`processed | cancelled | skipped`).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.persistence.models import (
    Actor,
    Clue,
    ConditionInstanceRow,
    Fact,
    Item,
    Plan,
    ScheduledEvent,
)
from app.services.events import EventTransaction
from app.services.world import CampaignHandle, WorldError

DETERMINISTIC_TYPES = {"fact.establish", "clue.destroy", "plan.advance", "location.state"}
BLOCKING_CONDITIONS = {"condition.incapacitated", "condition.detained", "condition.dead"}


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _tx(self, h: CampaignHandle, **kw: Any) -> EventTransaction:
        return EventTransaction(self.session, h.campaign_id, h.timeline_id, **kw)

    # -- scheduling ------------------------------------------------------------------------------

    async def schedule(
        self,
        h: CampaignHandle,
        *,
        tick: int,
        event_type: str,
        payload: dict[str, Any] | None = None,
        prerequisites: list[dict[str, Any]] | None = None,
        key: str | None = None,
        tx: EventTransaction | None = None,
    ) -> ScheduledEvent:
        if tx is None:
            async with self._tx(h) as tx2:
                return await self.schedule(
                    h,
                    tick=tick,
                    event_type=event_type,
                    payload=payload,
                    prerequisites=prerequisites,
                    key=key,
                    tx=tx2,
                )
        if tick < tx.clock.current_tick:
            raise WorldError("cannot schedule in the past")
        row = ScheduledEvent(
            campaign_id=h.campaign_id,
            timeline_id=h.timeline_id,
            scheduled_tick=tick,
            event_type=event_type,
            payload={
                **(payload or {}),
                "prerequisites": list(prerequisites or []),
                **({"key": key} if key else {}),
            },
            status="pending",
        )
        self.session.add(row)
        await self.session.flush()
        created = await tx.emit(
            ev.ScheduledEventCreated(
                scheduled_event_id=row.id, scheduled_tick=tick, scheduled_type=event_type
            )
        )
        row.created_event_id = created.id
        return row

    async def pending(self, h: CampaignHandle) -> list[ScheduledEvent]:
        return list(
            (
                await self.session.execute(
                    select(ScheduledEvent)
                    .where(
                        ScheduledEvent.timeline_id == h.timeline_id,
                        ScheduledEvent.status == "pending",
                    )
                    .order_by(ScheduledEvent.scheduled_tick, ScheduledEvent.created_at)
                )
            )
            .scalars()
            .all()
        )

    async def by_key(self, h: CampaignHandle, key: str) -> ScheduledEvent | None:
        for row in (
            (
                await self.session.execute(
                    select(ScheduledEvent).where(ScheduledEvent.timeline_id == h.timeline_id)
                )
            )
            .scalars()
            .all()
        ):
            if row.payload.get("key") == key:
                return row
        return None

    # -- firing ----------------------------------------------------------------------------------

    async def fire_due(self, tx: EventTransaction, up_to_tick: int) -> list[ScheduledEvent]:
        """Called by the clock advance: every pending deterministic event whose tick has come
        is revalidated and either processed or cancelled. Non-deterministic types are left
        pending (Milestone 08). Returns the rows touched."""
        due = list(
            (
                await self.session.execute(
                    select(ScheduledEvent)
                    .where(
                        ScheduledEvent.timeline_id == tx.timeline_id,
                        ScheduledEvent.status == "pending",
                        ScheduledEvent.scheduled_tick <= up_to_tick,
                    )
                    .order_by(ScheduledEvent.scheduled_tick, ScheduledEvent.created_at)
                )
            )
            .scalars()
            .all()
        )
        touched: list[ScheduledEvent] = []
        for row in due:
            if row.event_type not in DETERMINISTIC_TYPES:
                continue  # needs the simulator; stays pending
            row.status = "processing"
            failed = await self._failed_prerequisite(row.payload.get("prerequisites", []))
            if failed is not None:
                fired = await tx.emit(
                    ev.ScheduledEventFired(
                        scheduled_event_id=row.id,
                        scheduled_tick=row.scheduled_tick,
                        scheduled_type=row.event_type,
                        outcome="cancelled",
                        detail={"failed_prerequisite": failed},
                    ),
                    game_tick=row.scheduled_tick,
                )
                row.status, row.processed_event_id = "cancelled", fired.id
                touched.append(row)
                continue
            fired = await tx.emit(
                ev.ScheduledEventFired(
                    scheduled_event_id=row.id,
                    scheduled_tick=row.scheduled_tick,
                    scheduled_type=row.event_type,
                    outcome="processed",
                    detail={k: v for k, v in row.payload.items() if k != "prerequisites"},
                ),
                game_tick=row.scheduled_tick,
            )
            await self._handle(tx, row, fired)
            row.status, row.processed_event_id = "processed", fired.id
            touched.append(row)
        return touched

    async def _failed_prerequisite(self, prereqs: list[dict[str, Any]]) -> dict[str, Any] | None:
        for p in prereqs:
            kind = p.get("kind")
            if kind == "actor_free":
                actor = await self.session.get(Actor, uuid.UUID(str(p["actor_id"])))
                if actor is None or not actor.alive or not actor.active:
                    return p
                conds = {
                    c
                    for c in (
                        await self.session.execute(
                            select(ConditionInstanceRow.condition_key).where(
                                ConditionInstanceRow.target_entity_id == actor.entity_id,
                                ConditionInstanceRow.status == "active",
                            )
                        )
                    ).scalars()
                }
                if conds & BLOCKING_CONDITIONS:
                    return p
            elif kind == "item_exists":
                item = await self.session.get(Item, uuid.UUID(str(p["item_id"])))
                if item is None or item.destroyed_event_id is not None:
                    return p
            elif kind == "clue_intact":
                clue = await self.session.get(Clue, uuid.UUID(str(p["clue_id"])))
                if clue is None or clue.state != "intact":
                    return p
            elif kind == "fact_true":
                fact = await self.session.get(Fact, uuid.UUID(str(p["fact_id"])))
                if fact is None or fact.truth_status != "true":
                    return p
            else:
                return {**p, "reason": "unknown prerequisite kind"}
        return None

    async def _handle(self, tx: EventTransaction, row: ScheduledEvent, fired) -> None:
        p = row.payload
        if row.event_type == "fact.establish":
            fact = await self.session.get(Fact, uuid.UUID(str(p["fact_id"])))
            if fact is not None and fact.canon_status != "established":
                est = await tx.emit(
                    ev.FactEstablished(
                        fact_id=fact.id, key=fact.key, reason=p.get("reason", "scheduled")
                    ),
                    cause=fired,
                    game_tick=row.scheduled_tick,
                )
                fact.canon_status, fact.established_event_id = "established", est.id
        elif row.event_type == "clue.destroy":
            from app.services.mystery import MysteryService

            await MysteryService(self.session).destroy_clue(
                CampaignHandle(tx.campaign_id, tx.timeline_id),
                uuid.UUID(str(p["clue_id"])),
                reason=p.get("reason", "scheduled"),
                tx=tx,
                cause=fired,
            )
        elif row.event_type == "plan.advance":
            plan = await self.session.get(Plan, uuid.UUID(str(p["plan_id"])))
            if plan is not None and plan.status == "active":
                steps = list(plan.steps or [])
                before = plan.current_step
                after = min(before + 1, len(steps))
                adv = await tx.emit(
                    ev.PlanAdvanced(
                        plan_id=plan.id,
                        from_step=before,
                        to_step=after,
                        reason=p.get("reason", "scheduled"),
                    ),
                    cause=fired,
                    game_tick=row.scheduled_tick,
                )
                plan.current_step, plan.updated_event_id = after, adv.id
                if after >= len(steps):
                    plan.status = "completed"
        elif row.event_type == "location.state":
            from app.persistence.models import Location

            loc = await self.session.get(Location, uuid.UUID(str(p["location_id"])))
            if loc is not None:
                loc.simulation_state = {**(loc.simulation_state or {}), **p.get("patch", {})}
