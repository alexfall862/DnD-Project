"""Play session 2026-10-05: the gate merchant was a scripted extra, so the narrator voiced him
and nobody remembered the deal. Engaged twice, an extra becomes a living character in that
same turn, remembering the earlier exchange; promotion is on the ledger."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.persistence.models import ActorController, Event, Goal, Memory
from tests.integration.test_ai_actors import by_actor, npc, pc
from tests.integration.test_orchestrator import intent, responder

pytestmark = pytest.mark.integration
API = "/api/v1"


@pytest.fixture
def script(app):
    fake = app.state.provider
    asked: list[str] = []
    materializer_inputs: list[str] = []
    fake.register(
        "intent_interpreter",
        responder(
            {
                "what is your issue": intent(
                    "say",
                    intents=[("ask", "an_irritated_merchant", None)],
                    targets=["an_irritated_merchant"],
                    band="brief",
                ),
                "Let us in on it": intent(
                    "say",
                    intents=[("persuade", "an_irritated_merchant", None)],
                    targets=["an_irritated_merchant"],
                    band="brief",
                ),
            }
        ),
    )

    def materialize(req):
        materializer_inputs.append(req.user)
        return {
            "summary": "A cloth trader late for his buyers, hiding a crate he should not have.",
            "occupation": "textile merchant",
            "temperament": "irritable, greedy, frightened of the captain",
            "dimensions": {"greed": 0.9, "honesty": 0.3, "risk_tolerance": 0.4},
            "goals": [
                {"description": "get the wagon through the gate before dark", "priority": 80}
            ],
            "attitude_to_party": {"trust": 15, "fear": 20, "familiarity": 10},
            "memories": [
                {
                    "summary": "Strangers at the gate asked what my issue was with the guards.",
                    "salience": 0.7,
                }
            ],
        }

    def merchant(req):
        asked.append(req.user)
        return npc("Keep your voice down. Maybe we can talk.", act="answer")

    fake.register("npc_materializer", materialize)
    fake.register("npc_actor", by_actor({"Irritated merchant": merchant}))
    fake.register("ai_player", by_actor({"Elara": pc(None), "Tomas": pc(None)}))
    fake.register("narrator", "The rain keeps on.")
    return {"asked": asked, "materializer": materializer_inputs}


async def test_an_extra_engaged_twice_comes_alive_and_remembers(
    app, client, script, session_factory
) -> None:
    r = await client.post(f"{API}/debug/seed-demo", params={"fixture": "frostbridge"})
    w = r.json()
    cid, alex = w["campaign_id"], w["actors"]["Alex"]
    merchant = uuid.UUID(w["actors"]["Irritated merchant"])

    async def controller() -> str:
        async with session_factory() as s:
            return (
                await s.execute(
                    select(ActorController.controller_type).where(
                        ActorController.actor_id == merchant,
                        ActorController.valid_until_event_id.is_(None),
                    )
                )
            ).scalar_one()

    first = await client.post(
        f"{API}/campaigns/{cid}/play",
        json={"actor_id": alex, "text": "Merchant, what is your issue with these guards?"},
    )
    assert first.status_code == 200, first.text
    assert await controller() == "scripted" and not script["asked"]

    second = await client.post(
        f"{API}/campaigns/{cid}/play",
        json={"actor_id": alex, "text": "You know what you have. Let us in on it."},
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert await controller() == "ai"
    assert any("promoted" in n for n in body["dev_notes"])
    # he answers in that same turn, as himself
    assert script["asked"], "the promoted merchant was not asked to react"
    assert any("Keep your voice down" in s["text"] for s in body["speakers"])
    # his memory includes the first exchange (the materializer saw it)
    assert "what is your issue" in script["materializer"][0]
    async with session_factory() as s:
        promoted = (
            (
                await s.execute(
                    select(Event).where(
                        Event.campaign_id == uuid.UUID(cid), Event.event_type == "actor.promoted"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert promoted and promoted[0].payload["goals"] == 1
        goals = (await s.execute(select(Goal).where(Goal.owner_id == merchant))).scalars().all()
        assert any("gate" in g.description for g in goals)
        mems = (await s.execute(select(Memory).where(Memory.actor_id == merchant))).scalars().all()
        assert any("Strangers at the gate" in m.subjective_summary for m in mems)
