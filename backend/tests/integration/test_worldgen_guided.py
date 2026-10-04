"""Milestone 09 follow-up: guided creation infers several brief settings from each answer;
the engine applies only valid brief fields; the conversation is bounded."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider
from app.engine.core import RulesEngine
from app.persistence.models import Campaign
from app.worldgen.brief import CampaignBrief
from app.worldgen.guided import MAX_TURNS, OPENING_QUESTION, GuidedCreationService, apply_patch
from tests.integration.test_worldgen import SETTINGS, new_campaign

pytestmark = pytest.mark.integration


def guided(session: AsyncSession, fake: FakeModelProvider) -> GuidedCreationService:
    return GuidedCreationService(
        session, SETTINGS, engine=RulesEngine.load("core_adventure"), provider=fake
    )


async def test_one_answer_sets_several_settings_and_bad_fields_are_refused(
    session: AsyncSession,
) -> None:
    h = await new_campaign(session, "guided-1")
    replies = [
        {
            "brief_patch": {
                "genres": ["dark fantasy"],
                "tone": {"darkness": 0.85},
                "mystery_frequency": "high",
                "player_character": {"name": "Ilse", "concept": "a disgraced healer"},
                "combat_lethality": "apocalyptic",  # invalid value
                "dragons": True,  # not a brief setting
                "seed": 999,  # protected
            },
            "next_question": "Do you want companions travelling with Ilse?",
            "done": False,
        },
        {"brief_patch": {"party_ai_companions": 1}, "done": True},
    ]
    fake = FakeModelProvider().register("brief_interviewer", lambda req: replies.pop(0))
    svc = guided(session, fake)
    brief, state = await svc.state(h.campaign_id)
    assert state.question == OPENING_QUESTION and not state.done
    out = await svc.answer(
        h.campaign_id, "A grim mystery on a frozen frontier. I play Ilse, a disgraced healer."
    )
    b = out["brief"]
    assert b["genres"] == ["dark fantasy"] and b["tone"]["darkness"] == 0.85
    assert b["tone"]["humor"] == 0.3  # untouched keys keep their values
    assert b["mystery_frequency"] == "high" and b["player_character"]["name"] == "Ilse"
    assert b["combat_lethality"] == "medium" and b["seed"] == 0
    assert any(r.startswith("combat_lethality") for r in out["rejected"])
    assert any(r.startswith("dragons") for r in out["rejected"])
    assert any(r.startswith("seed") for r in out["rejected"])
    assert out["question"] == "Do you want companions travelling with Ilse?"
    # the interviewer saw the conversation so far and the current brief
    assert "frozen frontier" in fake.calls[0].request.user
    out = await svc.answer(h.campaign_id, "Just one, someone practical.")
    assert out["done"] and out["question"] is None and out["brief"]["party_ai_companions"] == 1
    c = await session.get(Campaign, h.campaign_id)
    assert c.creation_mode == "guided"
    assert CampaignBrief.model_validate(c.generation_brief).party_ai_companions == 1
    # once done, further answers change nothing and cost nothing
    await svc.answer(h.campaign_id, "Actually, make it three")
    assert len(fake.calls) == 2


async def test_the_conversation_is_bounded_and_can_be_ended_by_the_player(
    session: AsyncSession,
) -> None:
    h = await new_campaign(session, "guided-2")
    fake = FakeModelProvider().register(
        "brief_interviewer",
        {"brief_patch": {"notes": "more detail"}, "next_question": "And?", "done": False},
    )
    svc = guided(session, fake)
    for i in range(MAX_TURNS):
        out = await svc.answer(h.campaign_id, f"answer {i}")
    assert out["done"] and out["turns"] == MAX_TURNS and len(fake.calls) == MAX_TURNS
    h2 = await new_campaign(session, "guided-3")
    fake2 = FakeModelProvider()  # no fixture: a call would fail the test
    out = await guided(session, fake2).answer(h2.campaign_id, "done")
    assert out["done"] and fake2.calls == []


async def test_an_unusable_reply_keeps_the_brief_and_the_question(session: AsyncSession) -> None:
    h = await new_campaign(session, "guided-4")
    fake = FakeModelProvider().register("brief_interviewer", "not json at all")
    out = await guided(session, fake).answer(h.campaign_id, "space pirates please")
    assert not out["done"] and out["question"] == OPENING_QUESTION
    assert out["brief"] == CampaignBrief().model_dump()


def test_apply_patch_merges_nested_settings() -> None:
    b, rejected = apply_patch(CampaignBrief(), {"player_character": {"name": "Kel"}})
    assert b.player_character.name == "Kel" and b.player_character.pronouns == "they/them"
    assert rejected == []


async def test_guided_api(app, client) -> None:
    app.state.provider.register(
        "brief_interviewer",
        {"brief_patch": {"genres": ["cosmic horror"]}, "next_question": None, "done": True},
    )
    cid = (await client.post("/api/v1/campaigns", json={"name": "guided-api"})).json()[
        "campaign_id"
    ]
    r = await client.get(f"/api/v1/campaigns/{cid}/brief/guided")
    assert r.json()["question"] == OPENING_QUESTION
    r = await client.post(f"/api/v1/campaigns/{cid}/brief/guided", json={"message": "dread"})
    assert r.status_code == 200 and r.json()["done"]
    assert r.json()["brief"]["genres"] == ["cosmic horror"]
