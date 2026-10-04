"""Milestone 08: bounded world simulation over the Frostbridge clocks (testing-strategy §18;
frostbridge §19, §36–§38). Deterministic systems run first; the World Simulator is asked only
about due decisions; prerequisites are revalidated against current state; every run is one
`simulation.run` event with interval, candidates and budget."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.providers import FakeModelProvider
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import (
    Actor,
    ConditionInstanceRow,
    Event,
    Fact,
    Plan,
    Scene,
)
from app.seeds.frostbridge import DAY, HOUR, OPENING_TICK, seed_frostbridge
from app.services.memory import MemoryService
from app.services.schedule import ScheduleService
from app.services.simulation import SimulationService
from app.services.turns import Turn, budget_from_settings

pytestmark = pytest.mark.integration

PROCEED = {
    "proposals": [
        {"subject_ref": "s1", "type": "proceed", "justification": "the barge is loaded; go"}
    ],
    "budget_used": 1,
}


def make_sim(session: AsyncSession, fake: FakeModelProvider) -> SimulationService:
    settings = Settings(a9_token="", narrator_enabled=False)
    engine = RulesEngine.load("core_adventure", master_seed=3)
    memory = MemoryService(session)
    compiler = ContextCompiler(session, memory=memory, engine=engine)
    runner = ModelRunner(session, ModelRouter(settings, fake))
    return SimulationService(session, settings, engine=engine, compiler=compiler, runner=runner)


async def advance(w, seconds: int):
    await w.world.advance_time(w.h, seconds, reason="the party is away")


async def fired(session: AsyncSession, w) -> dict[str, str]:
    rows = (
        await session.execute(
            select(Event).where(
                Event.campaign_id == w.h.campaign_id, Event.event_type == "scheduled_event.fired"
            )
        )
    ).scalars()
    return {e.payload["scheduled_type"]: e.payload["outcome"] for e in rows}


async def test_six_days_away_the_shipment_departs_with_one_simulator_call(
    session: AsyncSession,
) -> None:
    w = await seed_frostbridge(session, name="sim-depart", engine_version="test")
    await session.commit()
    fake = FakeModelProvider().register("world_simulator", PROCEED)
    sim = make_sim(session, fake)
    turn = Turn(w.h, budget=budget_from_settings(sim.settings, None))

    # the clock moves (scheduled Day +2 / +3 deterministic events fire with it) ...
    start = (await w.world.clock(w.h)).current_tick
    await advance(w, 6 * DAY)
    now = (await w.world.clock(w.h)).current_tick
    assert now == OPENING_TICK + 6 * DAY
    # ... then one bounded simulation run covers the interval
    run = await sim.tick(w.h, from_tick=start, to_tick=now, turn=turn)
    await session.commit()

    assert run.event_budget == 3 and run.model_calls == 1
    # deterministic first: cargo assembled (plan clock), barge loaded (plan clock + Renn free),
    # Renn walked to the dock (scheduled travel through the scene service)
    # (cargo and documentation were completed by the Day +3 scheduled event as the clock ran)
    assert any("load barge" in s for s in run.plan_steps_advanced)
    assert "day5_renn_to_dock" in run.travelled
    renn = await session.get(Actor, w.actors["Renn"])
    assert renn.current_location_id == w.locations["restricted_dock"]
    dock_scene = (
        await session.execute(
            select(Scene).where(
                Scene.location_id == w.locations["restricted_dock"], Scene.status == "active"
            )
        )
    ).scalar_one()
    assert renn.current_scene_id == dock_scene.id
    # the decision went to the simulator once; its proposal was applied
    assert run.candidates and any(c.startswith("s1:day5_shipment") for c in run.candidates)
    assert [p["type"] for p in run.proposals_applied] == ["proceed"]
    departed = await session.get(Fact, w.facts["shipment_departed"])
    assert departed.canon_status == "established"
    plan = await session.get(Plan, w.plan)
    assert plan.current_step == 4  # depart at night done; pay the buyer is next (Day +6 noon)
    outcomes = await fired(session, w)
    assert outcomes["faction.shipment_departure"] == "processed"
    assert outcomes["actor.travel"] == "processed"
    assert outcomes["clue.destroy"] == "processed" and outcomes["fact.establish"] == "processed"
    # the run is on the ledger with its interval, candidates and budget (Invariant 14)
    runs = (
        (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == w.h.campaign_id, Event.event_type == "simulation.run"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(runs) == 1 and runs[0].payload["event_budget"] == 3
    assert runs[0].payload["model_calls"] == 1 and runs[0].payload["candidates"]
    # the quarry clock has not come yet; a later advance fires it without any model call
    assert (await session.get(Fact, w.facts["quarry_disturbance"])).canon_status == "latent"
    await advance(w, 3 * DAY)
    run2 = await sim.tick(w.h, from_tick=now, to_tick=now + 3 * DAY)
    await session.commit()
    assert (await session.get(Fact, w.facts["quarry_disturbance"])).canon_status == "established"
    assert run2.model_calls == 0 and (await session.get(Plan, w.plan)).status == "completed"
    assert await ScheduleService(session).pending(w.h) == []


async def test_player_disruption_changes_the_planned_result_without_a_model_call(
    session: AsyncSession,
) -> None:
    """Renn detained before Day +5: the barge cannot be loaded, he does not walk to the dock,
    the shipment is cancelled by prerequisite revalidation — the simulator is never asked."""
    w = await seed_frostbridge(session, name="sim-disrupt", engine_version="test")
    await session.commit()
    session.add(
        ConditionInstanceRow(
            target_entity_id=w.entities["Renn"],
            condition_key="condition.detained",
            instance_key="arrest1",
            intensity=1,
            status="active",
        )
    )
    await session.flush()
    fake = FakeModelProvider().register("world_simulator", PROCEED)
    sim = make_sim(session, fake)
    start = (await w.world.clock(w.h)).current_tick
    await advance(w, 6 * DAY)
    run = await sim.tick(w.h, from_tick=start, to_tick=start + 6 * DAY)
    await session.commit()
    assert run.model_calls == 0 and fake.calls == []
    plan = await session.get(Plan, w.plan)
    # cargo assembled by its clock; the documentation step was cancelled with Renn detained,
    # so the barge is never loaded and nothing after it happens
    assert plan.current_step == 1
    assert not any("load barge" in s for s in run.plan_steps_advanced)
    outcomes = await fired(session, w)
    assert outcomes["faction.shipment_departure"] == "cancelled"
    assert outcomes["actor.travel"] == "cancelled"
    assert outcomes["clue.destroy"] == "cancelled" and outcomes["plan.advance"] == "cancelled"
    assert (await session.get(Fact, w.facts["shipment_departed"])).canon_status == "latent"
    renn = await session.get(Actor, w.actors["Renn"])
    assert renn.current_location_id == w.locations["red_lantern"]


async def test_simulator_proposals_are_validated_and_budgeted(session: AsyncSession) -> None:
    w = await seed_frostbridge(session, name="sim-validate", engine_version="test")
    await session.commit()
    bad = {
        "proposals": [
            {"subject_ref": "zz9", "type": "proceed", "justification": "made up"},
            {"subject_ref": "s1", "type": "actor_travel", "justification": "wrong type"},
            {
                "subject_ref": "s1",
                "type": "plan_hold",
                "delay_seconds": 3600,
                "justification": "wait",
            },
            {"subject_ref": "p1", "type": "plan_hold", "justification": "wait too"},
        ],
        "budget_used": 4,
    }
    fake = FakeModelProvider().register("world_simulator", bad)
    sim = make_sim(session, fake)
    start = (await w.world.clock(w.h)).current_tick
    await advance(w, 6 * DAY)
    run = await sim.tick(w.h, from_tick=start, to_tick=start + 6 * DAY)
    await session.commit()
    reasons = {(r["subject_ref"], r["reason"]) for r in run.proposals_rejected}
    assert ("zz9", "unknown subject or type") in reasons
    assert any(r[0] == "s1" and "does not apply" in r[1] for r in reasons)
    held = [p for p in run.proposals_applied if p["type"] == "plan_hold"]
    assert held  # the shipment waits an hour; nothing departed
    assert (await session.get(Fact, w.facts["shipment_departed"])).canon_status == "latent"
    pending = {p.payload.get("key"): p for p in await ScheduleService(session).pending(w.h)}
    assert pending["day5_shipment"].scheduled_tick == 5 * DAY + 23 * HOUR + 3600


async def test_an_idle_world_costs_no_calls(session: AsyncSession) -> None:
    w = await seed_frostbridge(session, name="sim-idle", engine_version="test")
    await session.commit()
    fake = FakeModelProvider()  # no simulator fixture: a call would raise
    sim = make_sim(session, fake)
    start = (await w.world.clock(w.h)).current_tick
    await advance(w, 12 * HOUR)
    run = await sim.tick(w.h, from_tick=start, to_tick=start + 12 * HOUR)
    await session.commit()
    assert run.model_calls == 0 and run.candidates == [] and run.event_budget == 1
    assert fake.calls == []
