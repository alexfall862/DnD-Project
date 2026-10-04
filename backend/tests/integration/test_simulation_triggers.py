"""Milestone 08: what starts a simulation run — a rest/wait that crosses the granularity, the
debug time-advance endpoint with `process_simulation`, and the worker job — and what the
orchestrator hands to the worker (deferred memory processing)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider
from app.persistence.models import Event, Plan
from app.persistence.models.jobs import BackgroundJob
from app.seeds.frostbridge import DAY, seed_frostbridge
from app.services.jobs import JobQueue
from app.services.orchestrator import PlayRequest
from tests.integration.test_frostbridge_slice import Script, make_fake, make_orch
from tests.integration.test_orchestrator import intent

pytestmark = pytest.mark.integration


async def test_a_long_rest_runs_one_bounded_simulation_turn(session: AsyncSession) -> None:
    w = await seed_frostbridge(session, name="trigger-rest", engine_version="test")
    await session.commit()
    fake = make_fake(Script())
    fake.replace(
        "intent_interpreter", lambda req: intent("do", intents=[("long_rest", None, None)])
    )
    fake.register("world_simulator", {"proposals": [], "budget_used": 0})
    orch = make_orch(session, fake)
    tick0 = (await orch.world.clock(w.h)).current_tick
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "We rest for the night by the gate.")
    )
    assert res.actions and res.actions[0]["action"] == "action.long_rest"
    assert (await orch.world.clock(w.h)).current_tick == tick0 + 8 * 3600
    sim = res.metrics.get("simulation")
    assert sim and sim["from_tick"] == tick0 and sim["to_tick"] == tick0 + 8 * 3600
    assert sim["model_calls"] == 0  # nothing was due: an idle night costs no call
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
    assert len(runs) == 1


async def test_debug_time_advance_processes_clocks_and_simulation(app, client) -> None:
    fake: FakeModelProvider = app.state.provider
    fake.register(
        "world_simulator",
        {
            "proposals": [
                {"subject_ref": "s1", "type": "proceed", "justification": "the barge goes"}
            ],
            "budget_used": 1,
        },
    )
    seeded = (
        await client.post("/api/v1/debug/seed-demo", params={"fixture": "frostbridge"})
    ).json()
    cid = seeded["campaign_id"]
    r = await client.post(
        f"/api/v1/debug/campaigns/{cid}/advance-time",
        params={"seconds": 6 * DAY, "process_simulation": "true"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["to_tick"] - body["from_tick"] == 6 * DAY
    sim = body["simulation"]
    assert sim["model_calls"] == 1 and sim["travelled"] == ["day5_renn_to_dock"]
    assert any(p["type"] == "proceed" for p in sim["proposals_applied"])
    facts = (await client.get(f"/api/v1/debug/campaigns/{cid}/facts")).json()
    departed = [f for f in facts if f.get("key") == "shipment_departed"]
    assert departed and departed[0]["canon_status"] == "established"
    jobs = (await client.get(f"/api/v1/debug/campaigns/{cid}/jobs")).json()
    assert isinstance(jobs, list)


async def test_deferred_memory_processing_becomes_a_worker_job(session: AsyncSession) -> None:
    """When the ladder defers the checkpoint, the orchestrator queues it instead of dropping it."""
    w = await seed_frostbridge(session, name="trigger-defer", engine_version="test")
    await session.commit()
    fake = make_fake(Script())
    fake.replace(
        "intent_interpreter", lambda req: intent("do", intents=[("short_rest", None, None)])
    )
    fake.register("world_simulator", {"proposals": [], "budget_used": 0})
    orch = make_orch(session, fake)
    # a budget so tight that the checkpoint must be deferred
    orch.settings = orch.settings.model_copy(update={"max_sync_model_calls_per_turn": 1})
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "We take a short rest by the gate.")
    )
    checkpoints = res.metrics.get("checkpoints") or []
    assert checkpoints and all(c.get("deferred") for c in checkpoints)
    queued = await JobQueue(session).pending(w.h.campaign_id)
    assert {j.job_type for j in queued} == {"memory.process", "journal.update"}
    mem = [j for j in queued if j.job_type == "memory.process"]
    assert {j.subject_id for j in mem} == {w.actors["Elara"], w.actors["Tomas"]}
    assert all(j.payload.get("reason") == "rest" for j in mem)
    plan = await session.get(Plan, w.plan)
    assert plan.current_step == 0  # an hour of rest moves no clocks


async def test_job_rows_belong_to_their_campaign(session: AsyncSession) -> None:
    w = await seed_frostbridge(session, name="trigger-jobs", engine_version="test")
    await session.commit()
    q = JobQueue(session)
    await q.enqueue(
        "simulation.advance",
        campaign_id=w.h.campaign_id,
        timeline_id=w.h.timeline_id,
        payload={"from_tick": 0, "to_tick": DAY},
    )
    await session.commit()
    rows = (
        (
            await session.execute(
                select(BackgroundJob).where(BackgroundJob.campaign_id == w.h.campaign_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].job_type == "simulation.advance"
