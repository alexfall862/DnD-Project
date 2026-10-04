"""Milestone 09 follow-up: custom / imported worlds (campaign-generation §2). Imported content
is established canon; generation extends it and may not contradict it."""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider
from app.engine.core import RulesEngine
from app.persistence.models import Actor, Campaign, Entity, Fact, Location
from app.services.world import WorldError
from app.worldgen.brief import CampaignBrief
from app.worldgen.importer import CHUNK_CHARS, MAX_CHUNKS, ImportService, chunk_text
from tests.fixtures.saltreach import BRIEF, responder
from tests.fixtures.saltreach import STAGES as SCRIPT
from tests.integration.test_worldgen import SETTINGS, new_campaign, service

pytestmark = pytest.mark.integration

IMPORTED = {
    "summary": "The user's notes: an old lighthouse and its keeper.",
    "locations": [
        {
            "ref": "loc_old_light",
            "name": "the Old Light",
            "type": "site",
            "detail": "latent",
            "descriptor": "a dark lighthouse on a spit of shingle",
        }
    ],
    "actors": [
        {
            "ref": "npc_keeper",
            "name": "Ama Velt",
            "importance": "standard",
            "descriptor": "the lighthouse keeper",
            "location_ref": "loc_old_light",
        }
    ],
    "facts": [
        {
            "key": "f_imp_light_dark",
            "predicate": "has not been lit since the god fell silent",
            "subject_ref": "loc_old_light",
            "known_by_refs": ["npc_keeper"],
        }
    ],
}


def importer(session: AsyncSession, fake: FakeModelProvider) -> ImportService:
    return ImportService(
        session, SETTINGS, engine=RulesEngine.load("core_adventure"), provider=fake
    )


async def prepared(session: AsyncSession, name: str):
    h = await new_campaign(session, name)
    c = await session.get(Campaign, h.campaign_id)
    c.generation_brief = CampaignBrief.model_validate(BRIEF).model_dump()
    await session.commit()
    return h


async def test_a_structured_import_is_canon_the_pipeline_extends(session: AsyncSession) -> None:
    h = await prepared(session, "import-structured")
    fake = FakeModelProvider().register("world_author", responder())
    res = await importer(session, fake).import_source(h.campaign_id, IMPORTED, fmt="structured")
    assert res.status == "ready" and res.counts == {"facts": 1, "locations": 1, "actors": 1}
    assert fake.calls == []  # structured data needs no model
    svc = service(session, fake)
    run = await svc.create_run(h.campaign_id, CampaignBrief.model_validate(BRIEF))
    stages = await svc.stages(run.id)
    assert stages[0].stage_key == "import" and stages[0].status == "ready"
    # every stage was shown the imported world as existing canon
    run = await svc.run(run.id)
    assert run.status == "ready", run.error
    premise_call = next(c for c in fake.calls if "STAGE premise" in c.request.user)
    assert (
        "loc_old_light" in premise_call.request.user
        and "f_imp_light_dark" in premise_call.request.user
    )
    await svc.start(h.campaign_id)
    campaign = await session.get(Campaign, h.campaign_id)
    assert campaign.status == "active" and campaign.creation_mode == "imported"
    fact = (
        await session.execute(
            select(Fact).where(Fact.campaign_id == h.campaign_id, Fact.key == "f_imp_light_dark")
        )
    ).scalar_one()
    assert fact.canon_status == "established"
    keeper = (
        await session.execute(
            select(Actor)
            .join(Entity, Entity.id == Actor.entity_id)
            .where(Entity.campaign_id == h.campaign_id, Entity.canonical_name == "Ama Velt")
        )
    ).scalar_one()
    light = await session.get(Location, keeper.current_location_id)
    assert light.detail_level == "latent"


async def test_generation_may_not_contradict_the_import(session: AsyncSession) -> None:
    h = await prepared(session, "import-contradiction")
    imported = copy.deepcopy(IMPORTED)
    imported["facts"].append({"key": "f_imp_return", "predicate": "not the drowned do not return"})
    fake = FakeModelProvider().register("world_author", responder())
    await importer(session, fake).import_source(h.campaign_id, imported, fmt="structured")
    svc = service(session, fake)
    run = await svc.create_run(h.campaign_id, CampaignBrief.model_validate(BRIEF))
    run = await svc.run(run.id)
    assert run.status == "failed" and "metaphysics" in run.error
    row = next(s for s in await svc.stages(run.id) if s.stage_key == "metaphysics")
    assert any("contradicts established canon 'f_imp_return'" in e for e in row.errors)
    with pytest.raises(WorldError):
        await svc.regenerate(run.id, "import")


async def test_an_imported_character_sheet_is_completed_by_the_party_stage(
    session: AsyncSession,
) -> None:
    h = await prepared(session, "import-sheet")
    sheet = {k: v for k, v in SCRIPT["party"]["actors"][0].items() if k != "location_ref"}
    fake = FakeModelProvider().register("world_author", responder())
    res = await importer(session, fake).import_source(
        h.campaign_id, {"actors": [sheet]}, fmt="structured"
    )
    assert res.status == "ready"
    svc = service(session, fake)
    run = await svc.run(
        (await svc.create_run(h.campaign_id, CampaignBrief.model_validate(BRIEF))).id
    )
    assert run.status == "ready", run.error
    started = await svc.start(h.campaign_id)
    rook = await session.get(Actor, started.player_actor_id)
    assert rook.mechanical_profile["skills"]["skill.investigation"] == 2
    assert rook.current_scene_id == started.opening_scene_id


async def test_text_is_read_in_bounded_chunks_that_see_each_other(session: AsyncSession) -> None:
    h = await prepared(session, "import-text")
    para = "The keeper Ama Velt tends the Old Light. " * 60  # ~2.4k characters
    text = "\n\n".join([para, para, para])
    parts = chunk_text(text)
    assert len(parts) == 2 and all(len(p) <= CHUNK_CHARS for p in parts)
    first = {
        "locations": [IMPORTED["locations"][0]],
        "actors": [IMPORTED["actors"][0]],
    }
    second = {"facts": IMPORTED["facts"]}  # refers to refs the first part defined
    answers = [first, second]
    fake = FakeModelProvider().register("world_author", lambda req: answers.pop(0))
    res = await importer(session, fake).import_source(h.campaign_id, text, fmt="text")
    assert res.status == "ready" and res.chunks == 2
    assert res.counts == {"facts": 1, "locations": 1, "actors": 1}
    assert "loc_old_light" in fake.calls[1].request.user  # the second part saw the first
    assert "SOURCE TEXT" in fake.calls[0].request.user
    with pytest.raises(WorldError, match="source too long"):
        await importer(session, FakeModelProvider()).import_source(
            h.campaign_id, "\n\n".join(["x" * (CHUNK_CHARS - 10)] * (MAX_CHUNKS + 1)), fmt="text"
        )


async def test_import_api(app, client) -> None:
    r = await client.post("/api/v1/campaigns", json={"name": "api-import"})
    cid = r.json()["campaign_id"]
    await client.put(f"/api/v1/campaigns/{cid}/brief", json={"brief": BRIEF})
    r = await client.post(
        f"/api/v1/campaigns/{cid}/imports", json={"format": "structured", "content": IMPORTED}
    )
    assert r.status_code == 200 and r.json()["status"] == "ready"
    bad = {"actors": [{"ref": "npc_x", "name": "X", "location_ref": "loc_nowhere"}]}
    r = await client.post(
        f"/api/v1/campaigns/{cid}/imports", json={"format": "structured", "content": bad}
    )
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert any("loc_nowhere" in e for e in r.json()["errors"])
