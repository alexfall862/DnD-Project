"""Dice (play session 2026-10-05, decision 1): in manual mode a check the game calls for
pauses the turn before anything happens; the player sees the skill, the number to reach,
their bonus and the stakes; rolling resumes the stored turn (no second interpretation) and
the engine rolls at that moment; reconsidering changes nothing; auto mode rolls at once.
Every roll carries its natural die, DC and outcome, and dev view can replay it from its
seed through the engine's dice function."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.persistence.models import Claim, PendingRoll
from app.persistence.models.rules import Roll
from tests.integration.test_ai_actors import by_actor, npc, pc
from tests.integration.test_orchestrator import intent, responder

pytestmark = pytest.mark.integration
API = "/api/v1"


@pytest.fixture
def script(app):
    fake = app.state.provider
    fake.register(
        "intent_interpreter",
        responder(
            {
                "let me in on it": intent(
                    "say",
                    intents=[("persuade", "mira", None)],
                    targets=["mira"],
                    band="brief",
                )
            }
        ),
    )
    fake.register(
        "npc_actor",
        by_actor({"Mira": npc("Fine. Talk.", act="answer"), "Renn": npc(None, act="silence")}),
    )
    fake.register("ai_player", by_actor({"Elara": pc(None), "Tomas": pc(None)}))
    fake.register("narrator", "Mira weighs you up.")
    return fake


async def setup(client, mode: str):
    w = (await client.post(f"{API}/debug/seed-demo", params={"fixture": "tavern"})).json()
    r = await client.patch(
        f"{API}/campaigns/{w['campaign_id']}/settings", json={"changes": {"dice_mode": mode}}
    )
    assert r.status_code == 200, r.text
    return w


async def play(client, w, **body):
    r = await client.post(
        f"{API}/campaigns/{w['campaign_id']}/play", json={"actor_id": w["actors"]["Alex"], **body}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_a_called_for_check_waits_for_the_player_to_roll(
    client, script, session_factory
) -> None:
    w = await setup(client, "manual")
    asked = await play(client, w, text="Innkeeper, you know what you have. Mira, let me in on it.")
    req = asked["roll_request"]
    assert req and asked["needs_player_input"] and not asked["visible_rolls"]
    (check,) = req["checks"]
    assert check["label"] == "Persuasion" and check["dc"] == 14 and check["die"] == "1d20"
    assert isinstance(check["bonus"], int) and check["stakes"]["failure"]
    assert "Persuasion check" in req["prompt"] and "against 14" in req["prompt"]
    async with session_factory() as s:
        # nothing happened yet: no dice, no words reached anyone
        assert (
            not (
                await s.execute(select(Roll).where(Roll.actor_id == uuid.UUID(w["actors"]["Alex"])))
            )
            .scalars()
            .all()
        )
        assert (
            not (
                await s.execute(
                    select(Claim).where(Claim.speaker_actor_id == uuid.UUID(w["actors"]["Alex"]))
                )
            )
            .scalars()
            .all()
        )

    calls_before = len(script.calls)
    rolled = await play(client, w, text="Roll", roll_request_id=req["id"], roll_decision="roll")
    roll = rolled["visible_rolls"][0]
    assert roll["purpose"] == "Persuasion" and roll["dc"] == 14 and roll["source"] == "engine"
    assert 1 <= roll["natural"] <= 20 and roll["success"] in (True, False)
    assert any(a["action"] == "social.persuade" for a in rolled["actions"])
    # the stored interpretation was reused: no second interpreter call
    roles = [type(c).__name__ and c.request.profile for c in script.calls[calls_before:]]
    assert "intent_interpreter" not in rolled["metrics"]["calls_by_role"], roles
    async with session_factory() as s:
        assert (await s.get(PendingRoll, uuid.UUID(req["id"]))).status == "rolled"
    # dev certificate: the stored seed replays to the same dice through the engine
    cert = (await client.get(f"{API}/debug/rolls/{roll['id']}")).json()
    assert cert["replay"]["ok"] and cert["roll"]["seed"] is not None
    assert cert["source"].startswith("engine dice service")


async def test_reconsidering_changes_nothing(client, script, session_factory) -> None:
    w = await setup(client, "manual")
    asked = await play(client, w, text="Mira, let me in on it.")
    out = await play(
        client,
        w,
        text="Reconsider",
        roll_request_id=asked["roll_request"]["id"],
        roll_decision="reconsider",
    )
    assert out["ooc"] and not out["actions"] and not out["visible_rolls"]
    async with session_factory() as s:
        pr = await s.get(PendingRoll, uuid.UUID(asked["roll_request"]["id"]))
        assert pr.status == "reconsidered"
    # the request is spent
    r = await client.post(
        f"{API}/campaigns/{w['campaign_id']}/play",
        json={
            "actor_id": w["actors"]["Alex"],
            "text": "Roll",
            "roll_request_id": asked["roll_request"]["id"],
            "roll_decision": "roll",
        },
    )
    assert r.status_code == 400


async def test_auto_roll_rolls_at_once(client, script) -> None:
    w = await setup(client, "auto")
    out = await play(client, w, text="Mira, let me in on it.")
    assert out["roll_request"] is None
    assert out["visible_rolls"] and out["visible_rolls"][0]["purpose"] == "Persuasion"
