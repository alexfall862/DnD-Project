"""Play session 3 (campaign 7969656a; DECISIONS 10e): a won-over NPC gives real ground and
knows the rules already settled it; an agreed escort ties the groups so the party goes along;
a narrated deed is not spoken as dialogue; rulings cannot invent names; extras get a name."""

from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import TranscriptMessage
from app.services.ai_actors import Happenings
from app.services.consequences import ConsequenceContext
from app.services.orchestrator import PlayRequest, PlayResult, SessionOrchestrator
from app.services.promotion import is_generic_name, proper_name
from tests.fixtures.frostbridge import World
from tests.integration.test_ai_actors import by_actor, npc, pc

pytestmark = pytest.mark.integration


def intent(channel="do", intents=(), utterance=None):
    out = {
        "channel": channel,
        "confidence": 0.9,
        "intents": [
            {"order": i + 1, "action_type": a, "target_ref": t, "params": {}}
            for i, (a, t) in enumerate(intents)
        ],
        "conversation_time_band": "brief",
    }
    if utterance:
        out["utterance"] = utterance
    return out


def responder(table: dict[str, dict]):
    def pick(req):
        m = re.search(r'Player input \(channel: \w+\): "(.*)"', req.user)
        text = m.group(1) if m else req.user
        for phrase, out in table.items():
            if phrase in text:
                return out
        raise AssertionError(f"no fake intent for input: {req.user[-200:]}")

    return pick


def make(session: AsyncSession, fake: FakeModelProvider, reactions: int = 0) -> SessionOrchestrator:
    return SessionOrchestrator(
        session,
        Settings(a9_token="", spotlight_visible_reactions=reactions, narrator_enabled=False),
        engine=RulesEngine.load("core_adventure", master_seed=11),
        provider=fake,
    )


async def test_a_won_over_npc_is_told_so_even_when_nothing_was_said(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    orch = make(session, FakeModelProvider())
    hap = Happenings(w.actors["Alex"])
    hap.social[w.actors["Mira"]] = ("Persuasion", True, 6)
    orch._turn_result = PlayResult(uuid.uuid4())
    orch._turn_result.consequences.append({"ok": True, "text": "Mira agrees: hold a room."})
    text = await orch._reaction_situation(w.actors["Mira"], hap)
    assert "MUST give real ground" in text and "very convincing" in text
    assert "Mira agrees: hold a room." in text and "never contradict" in text


async def test_a_won_over_npc_cannot_answer_with_a_refusal(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    await w.world.create_party(w.h, "party", [w.actors[n] for n in ("Alex", "Elara", "Tomas")])
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder({"room": intent("say", [("persuade", "mira")], utterance="A room, please.")}),
    )
    fake.register("rules_adjudicator", {"requires_check": True, "check": {"difficulty": "routine"}})
    refusal = {
        **npc("No rooms for you."),
        "consequences": [{"kind": "refuse", "person": "self", "request": "a room"}],
    }
    fake.register("npc_actor", by_actor({"Mira": refusal, "Renn": npc(None, act="silence")}))
    fake.register("ai_player", by_actor({"Elara": pc(None), "Tomas": pc(None)}))
    orch = make(session, fake, reactions=1)
    for _ in range(6):
        res = await orch.process_player_input(
            w.h, PlayRequest(w.actors["Alex"], "Mira, a room for the night?")
        )
        if any(
            a["action"] == "social.persuade" and a["status"] == "succeeded" for a in res.actions
        ):
            break
    assert any(a["action"] == "social.persuade" and a["status"] == "succeeded" for a in res.actions)
    # on the turn she was won over, her refusal was dropped and nothing refused was recorded
    assert any("dropped: they were won over" in n for n in res.metrics.get("notes", []))
    assert "refuse" not in [c["kind"] for c in res.consequences]


async def test_an_agreed_escort_takes_the_party_along_when_the_npc_leaves(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    await w.world.create_party(w.h, "party", [w.actors[n] for n in ("Alex", "Elara", "Tomas")])
    orch = make(session, FakeModelProvider())
    scene = await orch.perspective.repo.current_scene(w.actors["Alex"])
    cands = await orch._candidates(w.h, w.actors["Alex"], scene)
    mira = next(c.ref for c in cands if c.id == str(w.actors["Mira"]))
    c = ConsequenceContext(w.h, scene, w.actors["Alex"], None, cands, "ruling", "success", None)
    agreed = await orch.consequences.apply_one(
        c, "agree", {"person": mira, "request": "let the party escort her and protect her goods"}
    )
    assert agreed.ok
    linked = await orch.situations.linked_party(w.actors["Mira"])
    assert set(linked) == {w.actors["Alex"], w.actors["Elara"], w.actors["Tomas"]}
    mira_cands = await orch._candidates(w.h, w.actors["Mira"], scene)
    gh = next(x.ref for x in mira_cands if x.kind == "location" and x.id == str(w.guard_house))
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder({"fter you": intent("say", [("say", "mira")], utterance="After you, Mira.")}),
    )
    fake.register(
        "npc_actor",
        by_actor(
            {
                "Mira": npc(
                    "Come on, then.", intentions=[{"action_type": "travel", "target_ref": gh}]
                ),
                "Renn": npc(None, act="silence"),
            }
        ),
    )
    fake.register("ai_player", by_actor({"Elara": pc(None), "Tomas": pc(None)}))
    orch2 = make(session, fake, reactions=1)
    res = await orch2.process_player_input(w.h, PlayRequest(w.actors["Alex"], "After you, Mira."))
    here = await orch2.perspective.repo.current_scene(w.actors["Alex"])
    assert here.location_id == w.guard_house, res.dev_notes
    assert any("You go along with" in c["text"] for c in res.consequences)


async def test_a_narrated_deed_is_not_spoken_and_introducing_teaches_names(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    orch = make(session, fake)
    scene = await orch.perspective.repo.current_scene(w.actors["Alex"])
    cands = await orch._candidates(w.h, w.actors["Alex"], scene)
    renn = next(c.ref for c in cands if c.id == str(w.actors["Renn"]))
    fake.register("intent_interpreter", responder({"introduce": intent("do", [("say", renn)])}))
    names = await orch.perspective.known_entities(w.actors["Renn"])
    assert w.entities["Alex"] not in names
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "We approach the captain and introduce ourselves.")
    )
    said = (
        (
            await session.execute(
                select(TranscriptMessage).where(
                    TranscriptMessage.speaker_actor_id == w.actors["Alex"],
                    TranscriptMessage.raw_text.like("%introduce ourselves%"),
                )
            )
        )
        .scalars()
        .all()
    )
    assert not said
    assert res.actions[0]["action"] == "gesture"
    names = await orch.perspective.known_entities(w.actors["Renn"])
    assert names.get(w.entities["Alex"]) == "Alex"


async def test_a_ruling_cannot_teach_a_name(session: AsyncSession, frostbridge: World) -> None:
    w = frostbridge
    orch = make(session, FakeModelProvider())
    scene = await orch.perspective.repo.current_scene(w.actors["Alex"])
    cands = await orch._candidates(w.h, w.actors["Alex"], scene)
    c = ConsequenceContext(w.h, scene, w.actors["Alex"], None, cands, "ruling", "success", None)
    bad = await orch.consequences.apply_one(c, "learn", {"text": "The merchant's name is Tomas."})
    assert not bad.ok
    new = await orch.consequences.apply_one(
        c, "learn", {"text": "He fears bandits on the road to Grimwater."}
    )
    assert not new.ok
    ok = await orch.consequences.apply_one(
        c, "learn", {"text": "He is worried about bandits on the road."}
    )
    assert ok.ok


def test_extras_with_only_a_description_get_a_name() -> None:
    assert is_generic_name("Irritated merchant") and is_generic_name("Dock thief 1")
    assert not is_generic_name("Gate guard Hale") and not is_generic_name("Mira")
    assert proper_name("Dorran Pike, the merchant") == "Dorran Pike"
