"""Milestone 01 acceptance: a deterministic world can be created, mutated and reloaded with a
complete causal event history."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.events import parse_payload
from app.persistence.models import (
    Actor,
    ActorController,
    Event,
    EventEntity,
    Scene,
    SceneParticipant,
    WorldClock,
)
from app.services.world import CampaignHandle, WorldError, WorldService

pytestmark = pytest.mark.integration


async def _new_campaign(svc: WorldService, name: str = "Test") -> CampaignHandle:
    return await svc.create_campaign(
        name, ruleset_key="core_adventure", ruleset_version="0.1", engine_version="test"
    )


async def test_world_lifecycle_and_reload(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    svc = WorldService(session)
    h = await _new_campaign(svc, "Frostbridge-ish")

    gate = await svc.create_location(h, "Town Gate", location_type="zone")
    square = await svc.create_location(h, "Market Square", location_type="zone")
    await svc.connect_locations(h, gate.id, square.id, travel_seconds=120)

    alex = await svc.create_actor(
        h, "Alex", actor_type="pc", controller_type="human", user_key="alex", location_id=gate.id
    )
    elara = await svc.create_actor(
        h, "Elara", actor_type="pc", controller_type="ai", location_id=gate.id
    )

    scene = await svc.start_scene(h, location_id=gate.id, participant_actor_ids=[alex.id, elara.id])
    assert scene.version == 1  # scene.started touched it
    scene_id = scene.id

    move = await svc.move_actor(h, alex.id, square.id, require_edge=True)  # 120 s travel
    await svc.advance_time(h, 600, reason="wait")

    # --- verify in a brand-new session (reload) ---
    async with session_factory() as s2:
        clock = await s2.get(WorldClock, h.timeline_id)
        assert clock is not None and clock.current_tick == 720

        actor = await s2.get(Actor, alex.id)
        assert actor is not None
        assert actor.current_location_id == square.id
        assert actor.current_scene_id is None  # left the gate scene by moving
        assert actor.updated_event_id == move.id

        other = await s2.get(Actor, elara.id)
        assert other is not None and other.current_scene_id == scene_id

        reloaded_scene = await s2.get(Scene, scene_id)
        assert reloaded_scene is not None
        assert reloaded_scene.version >= 2  # participant left + clock follow-ups
        # the human left: the gate scene is offscreen and lags the clock until a reunion
        # fast-forwards it (time-accounting §3–§5, Milestone 07)
        assert reloaded_scene.local_tick < clock.current_tick

        parts = (
            (
                await s2.execute(
                    select(SceneParticipant).where(SceneParticipant.scene_id == scene_id)
                )
            )
            .scalars()
            .all()
        )
        by_actor = {p.actor_id: p for p in parts}
        assert by_actor[alex.id].left_event_id == move.id
        assert by_actor[elara.id].left_event_id is None

        events = (
            (
                await s2.execute(
                    select(Event)
                    .where(Event.timeline_id == h.timeline_id)
                    .order_by(Event.sequence_number)
                )
            )
            .scalars()
            .all()
        )
        types = [e.event_type for e in events]
        assert types == [
            "campaign.created",
            "location.created",
            "location.created",
            "location.connected",
            "actor.created",
            "actor.created",
            "scene.started",
            "actor.moved",
            "scene.participant_left",
            "time.advanced",
            "time.advanced",
        ]
        assert [e.sequence_number for e in events] == list(range(1, len(events) + 1))
        # every payload round-trips through its registered schema
        for e in events:
            parse_payload(e.event_type, e.payload)
        # causality: the travel time advance was caused by the move
        travel = events[9]
        assert travel.cause_event_id == move.id and travel.payload["seconds"] == 120
        assert travel.game_tick == 120 and events[10].game_tick == 720
        # world version increments once per transaction, stamped on each event
        assert [e.world_version_after for e in events] == [1, 2, 3, 4, 5, 6, 7, 8, 8, 8, 9]
        # entity join rows exist for the actor move
        links = (
            (await s2.execute(select(EventEntity).where(EventEntity.event_id == move.id)))
            .scalars()
            .all()
        )
        assert [(link.entity_id, link.role) for link in links] == [(actor.entity_id, "subject")]


async def test_controller_switch_preserves_actor(session: AsyncSession) -> None:
    svc = WorldService(session)
    h = await _new_campaign(svc)
    loc = await svc.create_location(h, "Room")
    tomas = await svc.create_actor(
        h,
        "Tomas",
        actor_type="pc",
        controller_type="ai",
        location_id=loc.id,
        mechanical_profile={"might": 6},
        behavior_profile={"honesty": 0.82},
    )
    await svc.set_controller(h, tomas.id, "human", user_key="alex")
    await svc.set_controller(h, tomas.id, "ai")

    rows = (
        (
            await session.execute(
                select(ActorController)
                .where(ActorController.actor_id == tomas.id)
                .order_by(ActorController.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert [r.controller_type for r in rows] == ["ai", "human", "ai"]
    assert [r.valid_until_event_id is None for r in rows] == [False, False, True]
    actor = await session.get(Actor, tomas.id)
    assert actor is not None
    assert actor.mechanical_profile == {"might": 6} and actor.behavior_profile == {"honesty": 0.82}
    assert actor.entity_id == tomas.entity_id


async def test_move_requires_edge_when_asked(session: AsyncSession) -> None:
    svc = WorldService(session)
    h = await _new_campaign(svc)
    a = await svc.create_location(h, "A")
    b = await svc.create_location(h, "B")
    npc = await svc.create_actor(h, "Guard", location_id=a.id)
    with pytest.raises(WorldError):
        await svc.move_actor(h, npc.id, b.id, require_edge=True)
    # nothing was committed by the failed move
    events = await svc.events(h)
    assert [e.event_type for e in events][-1] == "actor.created"
    assert (await svc.clock(h)).current_tick == 0


async def test_time_only_moves_forward(session: AsyncSession) -> None:
    svc = WorldService(session)
    h = await _new_campaign(svc)
    with pytest.raises(WorldError):
        await svc.advance_time(h, 0)
    with pytest.raises(WorldError):
        await svc.advance_time(h, -5)
