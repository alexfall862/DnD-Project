"""Milestone 09: generate a non-Frostbridge campaign with FakeModel stages, reroll a stage,
reject contradictions, refuse a broken world, start it, and play its opening scene."""

from __future__ import annotations

import copy
from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import (
    Actor,
    Belief,
    Campaign,
    Clue,
    Entity,
    Event,
    Fact,
    Location,
    Mystery,
    Scene,
)
from app.services.orchestrator import PlayRequest, SessionOrchestrator
from app.services.perspective import PerspectiveService
from app.services.scenes import SceneService
from app.services.schedule import ScheduleService
from app.services.world import WorldError, WorldService
from app.worldgen.brief import CampaignBrief
from app.worldgen.materialize import MaterializeService
from app.worldgen.service import GenerationService
from app.worldgen.stages import STAGES
from tests.fixtures.saltreach import BRIEF, expected_calls, responder
from tests.fixtures.saltreach import STAGES as SCRIPT
from tests.integration.test_orchestrator import intent

pytestmark = pytest.mark.integration

SETTINGS = Settings(a9_token="", narrator_enabled=False, spotlight_visible_reactions=0)


async def new_campaign(session: AsyncSession, name: str):
    h = await WorldService(session).create_campaign(
        name, ruleset_key="core_adventure", ruleset_version="0.1.0", engine_version="test"
    )
    await session.commit()
    return h


def service(session: AsyncSession, fake: FakeModelProvider) -> GenerationService:
    return GenerationService(
        session, SETTINGS, engine=RulesEngine.load("core_adventure"), provider=fake
    )


async def generated(session: AsyncSession, name: str, fake: FakeModelProvider | None = None):
    calls: list[str] = []
    fake = fake or FakeModelProvider().register("world_author", responder(calls=calls))
    h = await new_campaign(session, name)
    svc = service(session, fake)
    run = await svc.create_run(h.campaign_id, CampaignBrief.model_validate(BRIEF))
    run = await svc.run(run.id)
    return h, svc, run, calls


async def test_generate_start_and_play_a_new_campaign(session: AsyncSession) -> None:
    h, svc, run, calls = await generated(session, "gen-full")
    assert run.status == "ready", run.error
    # one bounded call per plain stage; outline + one per item for the heavy stages, in order
    assert calls == expected_calls()
    stages = await svc.stages(run.id)
    assert all(s.status == "ready" for s in stages)
    per_stage = Counter(c.split(":")[0] for c in calls)
    assert all(s.attempts == per_stage[s.stage_key] for s in stages if s.stage_key != "import")
    assert all(s.progress == {} for s in stages)  # item progress is cleared once accepted
    started = await svc.start(h.campaign_id)

    campaign = await session.get(Campaign, h.campaign_id)
    assert campaign.status == "active" and campaign.name == "The Silent Tide"
    names = {
        e.canonical_name: e
        for e in (
            await session.execute(select(Entity).where(Entity.campaign_id == h.campaign_id))
        ).scalars()
    }
    # deep where play starts, shallow far away
    inn = (
        await session.execute(
            select(Location).where(Location.entity_id == names["the Gull and Anchor"].id)
        )
    ).scalar_one()
    march = (
        await session.execute(
            select(Location).where(Location.entity_id == names["the Ironmarch"].id)
        )
    ).scalar_one()
    assert inn.detail_level == "materialized" and inn.properties["space"]["zones"]
    assert march.detail_level == "outline" and "space" not in march.properties
    # the opening scene: the player, two AI companions, the innkeeper, at the inn
    scene = await session.get(Scene, started.opening_scene_id)
    assert scene.location_id == inn.id and scene.state["weather"].startswith("a salt wind")
    rook = await session.get(Actor, started.player_actor_id)
    assert rook.current_scene_id == scene.id
    psv = PerspectiveService(session)
    view = await psv.scene_view(rook.id)
    present = {p.known_as for p in view.participants if not p.is_self}
    assert {"Tess Morrow", "Bran Hollis", "the innkeeper"} <= present  # Wenna is a stranger
    # locked truth, redundant clues, knowledge only where it belongs
    mystery = (
        await session.execute(select(Mystery).where(Mystery.campaign_id == h.campaign_id))
    ).scalar_one()
    assert mystery.solution_locked and mystery.status == "active"
    clues = (
        (await session.execute(select(Clue).where(Clue.mystery_id == mystery.id))).scalars().all()
    )
    assert {c.clue_type for c in clues} == {"social", "document", "physical"}
    poisoned = (
        await session.execute(
            select(Fact).where(Fact.campaign_id == h.campaign_id, Fact.key == "f_harl_poisoned")
        )
    ).scalar_one()
    holders = {
        b.actor_id
        for b in (
            await session.execute(select(Belief).where(Belief.fact_id == poisoned.id))
        ).scalars()
    }
    harl = (
        await session.execute(select(Actor).where(Actor.entity_id == names["Harl Brask"].id))
    ).scalar_one()
    assert holders == {harl.id}
    assert "fouled" not in str(await psv.context_candidates(rook.id))
    metaphysics = (
        await session.execute(
            select(Fact).where(Fact.campaign_id == h.campaign_id, Fact.key == "f_no_return")
        )
    ).scalar_one()
    assert metaphysics.canon_status == "established"
    pending = {p.payload.get("key") for p in await ScheduleService(session).pending(h)}
    assert "day2_price_spike" in pending
    started_events = (
        (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == h.campaign_id, Event.event_type == "campaign.started"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(started_events) == 1

    # ... and it plays: a turn in the opening scene through the ordinary orchestrator
    fake = FakeModelProvider().register(
        "intent_interpreter", lambda req: intent("do", intents=[("search", "bar", None)])
    )
    orch = SessionOrchestrator(
        session, SETTINGS, engine=RulesEngine.load("core_adventure", master_seed=5), provider=fake
    )
    res = await orch.process_player_input(h, PlayRequest(rook.id, "I look behind the bar."))
    assert res.actions and res.actions[0]["action"] == "action.search"
    assert res.metrics["sync_model_calls"] == 1
    # the party can walk to the well; the warden who lives there is part of the new scene
    well = (
        await session.execute(
            select(Location).where(Location.entity_id == names["the East Well"].id)
        )
    ).scalar_one()
    actors = [rook.id] + [
        a.id
        for a in (
            await session.execute(select(Actor).where(Actor.current_scene_id == scene.id))
        ).scalars()
        if a.actor_type == "pc" and a.id != rook.id
    ]
    tr = await SceneService(session).travel(h, actors, well.id)
    osk = (
        await session.execute(select(Actor).where(Actor.entity_id == names["Osk Tamber"].id))
    ).scalar_one()
    assert osk.current_scene_id == tr.scene.id


async def test_rerolling_a_stage_invalidates_only_its_dependents(session: AsyncSession) -> None:
    calls: list[str] = []
    renamed = copy.deepcopy(SCRIPT["starting_settlement"])
    renamed["locations"][1]["name"] = "the Drowned Lamb"
    fake = FakeModelProvider().register(
        "world_author",
        responder({"starting_settlement": [SCRIPT["starting_settlement"], renamed]}, calls=calls),
    )
    h, svc, run, _ = await generated(session, "gen-reroll", fake)
    assert run.status == "ready"
    calls.clear()
    invalidated = await svc.regenerate(run.id, "starting_settlement", guidance="a rougher inn")
    assert invalidated == ["local_factions", "npcs", "opportunities", "party", "opening"]
    status = {s.stage_key: s.status for s in await svc.stages(run.id)}
    assert status["starting_settlement"] == "ready" and status["geography"] == "ready"
    assert all(status[k] == "invalidated" for k in invalidated)
    run = await svc.run(run.id)
    assert run.status == "ready"
    # nothing upstream was regenerated
    assert calls == expected_calls(["starting_settlement", *invalidated])
    settlement = next(s for s in await svc.stages(run.id) if s.stage_key == "starting_settlement")
    assert settlement.output["locations"][1]["name"] == "the Drowned Lamb"
    assert settlement.guidance == "a rougher inn"
    # once the campaign has started, rerolling is refused (established canon is immutable)
    await svc.start(h.campaign_id)
    with pytest.raises(WorldError):
        await svc.regenerate(run.id, "cultures")


async def test_a_contradiction_is_rejected_then_corrected_within_the_bound(
    session: AsyncSession,
) -> None:
    bad = copy.deepcopy(SCRIPT["history"])
    bad["facts"].append(
        {"key": "f_bad", "predicate": "the sea-god has been silent for years", "value": 3}
    )
    seen: list[str] = []

    def author(req):
        if "STAGE history" in req.user:
            seen.append(req.user)
            return bad if len(seen) == 1 else copy.deepcopy(SCRIPT["history"])
        return responder()(req)

    fake = FakeModelProvider().register("world_author", author)
    _h, svc, run, _ = await generated(session, "gen-contradiction", fake)
    assert run.status == "ready"
    hist = next(s for s in await svc.stages(run.id) if s.stage_key == "history")
    assert hist.attempts == 2
    assert "contradicts established canon 'f_god_silent'" in seen[1]  # the retry was told why


async def test_a_stage_that_stays_invalid_fails_the_run(session: AsyncSession) -> None:
    bad = copy.deepcopy(SCRIPT["opportunities"])
    bad["clues"] = bad["clues"][:1] + [
        {
            "ref": "clu_x",
            "mystery_ref": "mys_nope",
            "clue_type": "social",
            "supports_fact_key": "f_wenna_saw",
        }
    ]
    fake = FakeModelProvider().register("world_author", responder({"opportunities": bad}))
    h, svc, run, _ = await generated(session, "gen-fail", fake)
    assert run.status == "failed" and "opportunities" in run.error
    row = next(s for s in await svc.stages(run.id) if s.stage_key == "opportunities")
    assert row.status == "failed"
    # the bad clue is dropped (soft reference), leaving the stage one clue short; the items
    # without clues were sent back once with that error, the rest are kept for a rerun
    assert any("needs at least 2 clues" in e for e in row.errors), row.errors
    assert row.progress["outline"] and row.progress["filled"]
    sent_back = row.progress["item_errors"]
    assert sent_back and all(
        any("add clues for this item" in e for e in errs) for errs in sent_back.values()
    )
    assert not set(sent_back) & set(row.progress["filled"])  # a rerun refills exactly these
    with pytest.raises(WorldError):
        await svc.start(h.campaign_id)


async def test_a_failed_item_is_retried_alone_and_a_rerun_resumes(session: AsyncSession) -> None:
    """One bad NPC sheet costs one item, not the stage: its retry is told why, the good
    sheets are kept, and a rerun after a failure asks only for what is unfinished."""
    bad = {"actors": [{**SCRIPT["npcs"]["actors"][1], "location_ref": "loc_nowhere"}]}
    calls: list[str] = []
    fake = FakeModelProvider().register(
        "world_author", responder({"npcs:npc_wenna": bad}, calls=calls)
    )
    h, svc, run, _ = await generated(session, "gen-item-fail", fake)
    assert run.status == "failed" and "npcs" in run.error
    row = next(s for s in await svc.stages(run.id) if s.stage_key == "npcs")
    assert calls.count("npcs:npc_wenna") == 2 and calls.count("npcs:npc_harl") == 1
    assert row.progress["failed"] == ["npc_wenna"]
    assert set(row.progress["filled"]) == {"npc_harl", "npc_osk"}
    assert any("loc_nowhere" in e for e in row.errors)
    retry = next(
        c
        for c in fake.calls
        if "ITEM npc_wenna" in c.request.user
        and "loc_nowhere" in c.request.user
        and "rejected" in c.request.user
    )
    assert retry  # the corrective retry carried the item's own error

    # the model behaves now: the rerun resumes at the failed item only
    calls.clear()
    svc2 = service(session, FakeModelProvider().register("world_author", responder(calls=calls)))
    run = await svc2.run(run.id)
    assert run.status == "ready", run.error
    assert calls[0] == "npcs:npc_wenna"  # no new outline, no rewrite of the kept sheets
    assert "npcs:outline" not in calls and "npcs:npc_harl" not in calls
    row = next(s for s in await svc2.stages(run.id) if s.stage_key == "npcs")
    assert {a["ref"] for a in row.output["actors"]} >= {"npc_harl", "npc_wenna", "npc_osk"}
    await svc2.start(h.campaign_id)


async def test_a_world_that_fails_quality_checks_is_not_built(session: AsyncSession) -> None:
    # a second mystery that never receives a clue route: no single stage can see that, only
    # the whole-world quality check after building
    secrets = copy.deepcopy(SCRIPT["secrets"])
    secrets["mysteries"].append(
        {
            "ref": "mys_unreachable",
            "question": "Who rang the drowned bell?",
            "truth_fact_keys": ["f_fen_traders"],
        }
    )
    fake = FakeModelProvider().register("world_author", responder({"secrets": secrets}))
    h, svc, run, _ = await generated(session, "gen-quality", fake)
    assert run.status == "ready"
    with pytest.raises(WorldError):
        await svc.start(h.campaign_id)
    campaign = await session.get(Campaign, h.campaign_id, populate_existing=True)
    assert campaign.status == "generating"
    built = (
        (
            await session.execute(
                select(Actor)
                .join(Entity, Entity.id == Actor.entity_id)
                .where(Entity.campaign_id == h.campaign_id)
            )
        )
        .scalars()
        .all()
    )
    assert built == []  # the unit of work rolled every row back


async def test_materializing_a_shallow_place_on_demand(session: AsyncSession) -> None:
    h, svc, _run, _ = await generated(session, "gen-materialize")
    await svc.start(h.campaign_id)
    chapel_ent = (
        await session.execute(
            select(Entity).where(
                Entity.campaign_id == h.campaign_id, Entity.canonical_name == "the Drowned Chapel"
            )
        )
    ).scalar_one()
    chapel = (
        await session.execute(select(Location).where(Location.entity_id == chapel_ent.id))
    ).scalar_one()
    assert chapel.detail_level == "outline"
    envelope = {
        "summary": "The chapel's nave is half flooded.",
        "locations": [
            {
                "ref": "loc_drowned_chapel",
                "name": "the Drowned Chapel",
                "type": "site",
                "detail": "materialized",
                "zones": [{"key": "steps", "exit": True}, {"key": "nave", "cover": "light"}],
                "adjacency": [["steps", "nave"]],
                "features": ["a bell rope hanging into black water"],
            }
        ],
        "actors": [
            {
                "ref": "npc_hermit",
                "name": "Old Sefa",
                "importance": "standard",
                "descriptor": "a hermit in oilskins",
                "location_ref": "loc_drowned_chapel",
                "goals": [{"description": "keep the bell from being rung"}],
            }
        ],
        "facts": [
            {
                "key": "f_bell_below",
                "predicate": "a bronze bell lies under the nave water",
                "subject_ref": "loc_drowned_chapel",
            }
        ],
    }
    fake = FakeModelProvider().register("world_author", envelope)
    mat = MaterializeService(
        session, SETTINGS, engine=RulesEngine.load("core_adventure"), provider=fake
    )
    out = await mat.materialize_location(h, chapel.id, need="the party asked a scholar about it")
    assert out["status"] == "materialized" and out["zones"] == 2 and out["actors"] == 1
    await session.refresh(chapel)
    assert chapel.detail_level == "materialized" and len(chapel.properties["space"]["zones"]) == 2
    events = (
        (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == h.campaign_id, Event.event_type == "location.materialized"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    sefa = (
        await session.execute(
            select(Actor)
            .join(Entity, Entity.id == Actor.entity_id)
            .where(Entity.campaign_id == h.campaign_id, Entity.canonical_name == "Old Sefa")
        )
    ).scalar_one()
    assert sefa.current_location_id == chapel.id
    # contradicting established canon is refused
    bad = copy.deepcopy(envelope)
    bad["locations"][0]["ref"] = "loc_salt_flats"
    bad["facts"] = [{"key": "f_x", "predicate": "not the drowned do not return"}]
    flats_ent = (
        await session.execute(
            select(Entity).where(
                Entity.campaign_id == h.campaign_id, Entity.canonical_name == "the Salt Flats"
            )
        )
    ).scalar_one()
    flats = (
        await session.execute(select(Location).where(Location.entity_id == flats_ent.id))
    ).scalar_one()
    fake2 = FakeModelProvider().register("world_author", bad)
    mat2 = MaterializeService(
        session, SETTINGS, engine=RulesEngine.load("core_adventure"), provider=fake2
    )
    with pytest.raises(WorldError):
        await mat2.materialize_location(h, flats.id)
    await session.refresh(flats)
    assert flats.detail_level == "latent"


async def test_generation_api_flow(app, client) -> None:
    app.state.provider.register("world_author", responder())
    r = await client.post("/api/v1/campaigns", json={"name": "api-gen"})
    assert r.status_code == 201
    cid = r.json()["campaign_id"]
    r = await client.put(f"/api/v1/campaigns/{cid}/brief", json={"brief": BRIEF})
    assert r.status_code == 200 and r.json()["brief"]["title"] == "The Silent Tide"
    r = await client.post(f"/api/v1/campaigns/{cid}/generation-runs", params={"inline": "true"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    r = await client.get(f"/api/v1/generation-runs/{run_id}")
    assert r.json()["status"] == "ready" and len(r.json()["stages"]) == len(STAGES)
    preview = (await client.get(f"/api/v1/campaigns/{cid}/generation-preview")).json()
    secrets_stage = next(s for s in preview["stages"] if s["stage"] == "secrets")
    assert "secrets" not in secrets_stage  # hidden without debug opt-in
    preview2 = (
        await client.get(
            f"/api/v1/campaigns/{cid}/generation-preview", params={"include_secrets": "true"}
        )
    ).json()
    assert any(
        "fouled" in x
        for x in next(s for s in preview2["stages"] if s["stage"] == "secrets")["secrets"]
    )
    r = await client.post(
        f"/api/v1/generation-runs/{run_id}/stages/party/regenerate", json={"guidance": "older"}
    )
    assert r.status_code == 200 and r.json()["invalidated"] == ["opening"]
    r = await client.post(f"/api/v1/campaigns/{cid}/start")
    assert r.status_code == 409  # the opening stage was invalidated by the reroll
    await client.post(f"/api/v1/campaigns/{cid}/generation-runs", params={"inline": "true"})
    r = await client.post(f"/api/v1/campaigns/{cid}/start")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["opening_scene_id"] and body["player_actor_id"]
    r = await client.get(
        f"/api/v1/campaigns/{cid}/scene", params={"actor_id": body["player_actor_id"]}
    )
    assert r.status_code == 200, r.text
    scene = r.json()
    assert scene["scene_id"] == body["opening_scene_id"]
    assert scene["location_known_as"] == "the Gull and Anchor"
    assert scene["your_zone"] == "common_room"
    assert {"Tess Morrow", "Bran Hollis"} <= {p["known_as"] for p in scene["participants"]}


async def test_a_horror_campaign_plays_with_its_genre_module(session: AsyncSession) -> None:
    brief = {**BRIEF, "genres": ["cosmic horror"]}
    npcs = copy.deepcopy(SCRIPT["npcs"])
    npcs["actors"][1]["skills"]["occult"] = 2  # the innkeeper knows the old rites
    fake = FakeModelProvider().register("world_author", responder({"npcs": npcs}))
    h = await new_campaign(session, "gen-horror")
    svc = service(session, fake)
    run = await svc.create_run(h.campaign_id, CampaignBrief.model_validate(brief))
    campaign = await session.get(Campaign, h.campaign_id)
    assert campaign.settings["genre_modules"] == ["horror"]
    run = await svc.run(run.id)
    assert run.status == "ready", run.error
    author_calls = [c for c in fake.calls if "Genre modules in play: Horror" in c.request.user]
    # every call (each stage, outline and item) was told the module's constraints
    assert len(author_calls) == len(expected_calls())
    await svc.start(h.campaign_id)
    wenna = (
        await session.execute(
            select(Actor)
            .join(Entity, Entity.id == Actor.entity_id)
            .where(Entity.campaign_id == h.campaign_id, Entity.canonical_name == "Wenna Ludd")
        )
    ).scalar_one()
    assert wenna.mechanical_profile["skills"]["skill.occult"] == 2
    engine = RulesEngine.for_campaign("core_adventure", campaign.settings)
    st = engine.actor(str(wenna.id), wenna.mechanical_profile)
    assert "resource.stability" in st.resources  # the module's resource applies in play


async def test_a_cut_off_stage_is_continued_not_restarted(session: AsyncSession) -> None:
    """A9 generation runs: a stage overran its output budget. The complete part is kept and
    the bounded second call is asked only for what is missing. (The heavy stages are itemized
    now; plain stages still continue.)"""
    import json as _json

    pressures = copy.deepcopy(SCRIPT["pressures"])
    full = _json.dumps({"pressures": pressures["pressures"]})
    cut_at = full.index('"ref": "prs_prices"') + 25  # inside the second pressure
    seen: list[str] = []

    def author(req):
        if "STAGE pressures" in req.user:
            seen.append(req.user)
            if len(seen) == 1:
                return full[:cut_at]  # cut off mid-entry
            return {**pressures, "pressures": [pressures["pressures"][1]]}  # what was missing
        return responder()(req)

    fake = FakeModelProvider().register("world_author", author)
    h, svc, run, _ = await generated(session, "gen-continue", fake)
    assert run.status == "ready", run.error
    row = next(s for s in await svc.stages(run.id) if s.stage_key == "pressures")
    assert row.attempts == 2
    assert {p["ref"] for p in row.output["pressures"]} == {"prs_sickness", "prs_prices"}
    assert "CONTINUE" in seen[1]
    assert any("continued after a cut-off answer" in n for n in row.errors)
    started = await svc.start(h.campaign_id)
    assert started.player_actor_id


async def test_a_day_zero_schedule_and_a_distant_settlement_still_start(
    session: AsyncSession,
) -> None:
    """09c A9 run: a day-0 schedule was "in the past" once the clock reached the opening hour,
    and a regional capital two hops away (inside-the-town, town-to-capital) counted as
    unreachable."""
    from app.persistence.models import ScheduledEvent

    geography = copy.deepcopy(SCRIPT["geography"])
    geography["locations"].append(
        {"ref": "loc_capital", "name": "Saltholm", "type": "city", "settlement": True}
    )
    settlement = copy.deepcopy(SCRIPT["starting_settlement"])
    town = next(x["ref"] for x in settlement["locations"] if x.get("settlement"))
    settlement["routes"].append({"from_ref": town, "to_ref": "loc_capital", "travel_minutes": 600})
    pressures = copy.deepcopy(SCRIPT["pressures"])
    pressures["schedules"][0]["at_day"] = 0
    fake = FakeModelProvider().register(
        "world_author",
        responder(
            {"geography": geography, "starting_settlement": settlement, "pressures": pressures}
        ),
    )
    h, svc, run, _ = await generated(session, "gen-day0", fake)
    assert run.status == "ready", run.error
    await svc.start(h.campaign_id)
    sched = (
        (
            await session.execute(
                select(ScheduledEvent).where(ScheduledEvent.campaign_id == h.campaign_id)
            )
        )
        .scalars()
        .all()
    )
    assert sched and min(s.scheduled_tick for s in sched) > 0  # day 0 = as play begins
