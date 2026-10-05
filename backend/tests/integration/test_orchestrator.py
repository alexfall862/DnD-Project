"""Milestone 06a: a human plays Frostbridge's deterministic actions by natural language with a
fake intent model; every turn is traced, budgeted and streamed.

Tests: compound decomposition; ambiguity → 409 with nothing committed, then resumption by
clarification_id; player assertions per class × policy; conversation time bands and cap;
SSE phase ordering; telemetry; adjudicator rulings (check, no check, invalid primitive); OOC
and private channels commit nothing in-world."""

from __future__ import annotations

import json
import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import (
    Action,
    Belief,
    Campaign,
    Event,
    Fact,
    Item,
    PendingClarification,
    Roll,
    Scene,
    TranscriptMessage,
    TurnMetrics,
)
from app.services.orchestrator import NeedsClarification, PlayRequest, SessionOrchestrator
from tests.fixtures.frostbridge import World

pytestmark = pytest.mark.integration


def intent(
    channel="do", intents=(), conveys=(), asserted=(), clarify=False, band="none", targets=()
):
    return {
        "channel": channel,
        "confidence": 0.9,
        "targets": list(targets),
        "intents": [
            {"order": i + 1, "action_type": a, "target_ref": t, "params": p or {}}
            for i, (a, t, p) in enumerate(intents)
        ],
        "ambiguities": [],
        "requires_clarification": clarify,
        "clarification_question": "Which one?" if clarify else None,
        "conveys": list(conveys),
        "asserted_facts": list(asserted),
        "conversation_time_band": band,
    }


def responder(table: dict[str, dict]):
    """Fake Intent Interpreter: answer by which phrase appears in the player input."""

    def pick(req):
        # the player's own line only: the context also carries the scene so far, which
        # repeats earlier inputs (scene log, play session 2026-10-05)
        m = re.search(r'Player input \(channel: \w+\): "(.*)"', req.user)
        text = m.group(1) if m else req.user
        for phrase, out in table.items():
            if phrase in text:
                return out
        raise AssertionError(f"no fake intent for input: {req.user[-200:]}")

    return pick


def make(session: AsyncSession, fake: FakeModelProvider) -> SessionOrchestrator:
    # 06a tests exercise the human path only: AI reactions (06b) are switched off here
    return SessionOrchestrator(
        session,
        Settings(a9_token="", spotlight_visible_reactions=0, narrator_enabled=False),
        engine=RulesEngine.load("core_adventure", master_seed=11),
        provider=fake,
    )


async def test_compound_input_decomposes_into_ordered_actions_and_speech(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    lantern = await w.world.create_item(
        w.h, "oil lantern", template_key="item.oil_lantern", location_id=w.tavern, zone_key="tables"
    )
    fake = FakeModelProvider().register(
        "intent_interpreter",
        responder(
            {
                "grab the lantern": intent(
                    "do",
                    intents=[
                        ("pick_up", "oil_lantern", None),
                        ("say", "elara", None),
                        ("move", "door", None),
                    ],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {"predicate": "we should leave now"},
                            "stance": "asserts_true",
                        }
                    ],
                    band="brief",
                ),
            }
        ),
    )
    orch = make(session, fake)
    emitted: list[tuple[str, dict]] = []
    before = (
        (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    res = await orch.process_player_input(
        w.h,
        PlayRequest(
            w.actors["Alex"],
            'I grab the lantern, tell Elara "we should leave now", and move to the door.',
        ),
        emit=lambda n, p: emitted.append((n, p)),
    )

    assert [a["action"] for a in res.actions] == ["action.pick_up", "action.move"] and all(
        a["status"] == "succeeded" for a in res.actions
    )
    assert (
        res.speakers
        and res.speakers[0]["text"] == "we should leave now"
        and res.speakers[0]["channel"] == "say"
    )
    assert res.time_advanced_seconds == 15 and res.channel == "do"
    names = [n for n, _ in emitted]
    # per-action mechanics events plus the turn summary mechanics event (api-contracts §9a)
    assert names[0] == "accepted" and names[-1] == "complete" and names.count("mechanics") == 4
    assert res.metrics["sync_model_calls"] == 1 and res.metrics["ms_to_first_output"] is not None
    item = await session.get(Item, lantern.id)
    assert item.possessor_entity_id == w.entities["Alex"]
    types = [
        e.event_type
        for e in (
            await session.execute(
                select(Event)
                .where(Event.campaign_id == w.h.campaign_id)
                .order_by(Event.sequence_number)
            )
        )
        .scalars()
        .all()[len(before) :]
    ]
    assert (
        "item.picked_up" in types
        and "speech.uttered" in types
        and "actor.repositioned" in types
        and types[-1] == "time.advanced"
    )
    msg = (
        await session.execute(
            select(TranscriptMessage).where(TranscriptMessage.turn_id == res.turn_id)
        )
    ).scalar_one()
    assert msg.raw_text == "we should leave now" and msg.source == "human"
    tm = (
        await session.execute(select(TurnMetrics).where(TurnMetrics.turn_id == res.turn_id))
    ).scalar_one()
    assert (
        tm.sync_model_calls == 1
        and tm.calls_by_role == {"intent_interpreter": 1}
        and not tm.budget_breached
    )
    assert any(
        "picks something up" in n or "You say" in n
        for n in [*res.mechanical_notices, *res.dev_notes]
    )


async def two_thieves(session: AsyncSession, w: World, orch: SessionOrchestrator):
    from tests.rules.conftest import FROSTBRIDGE_BUILDS

    t1 = await w.world.create_actor(
        w.h,
        "Dock thief",
        actor_type="npc",
        controller_type="ai",
        location_id=w.tavern,
        mechanical_profile=FROSTBRIDGE_BUILDS["thief"],
        metadata={"descriptor": "a thief"},
    )
    t2 = await w.world.create_actor(
        w.h,
        "Second thief",
        actor_type="npc",
        controller_type="ai",
        location_id=w.tavern,
        mechanical_profile=FROSTBRIDGE_BUILDS["thief"],
        metadata={"descriptor": "a thief"},
    )
    await w.world.create_item(
        w.h, "knife", template_key="item.knife", possessor_actor_id=w.actors["Alex"]
    )
    scene = await session.get(Scene, w.scene)
    # put both thieves in Alex's zone, in the scene, and start an encounter
    from app.persistence.models import SceneParticipant

    space = dict(scene.state["space"])
    for t in (t1, t2):
        session.add(SceneParticipant(scene_id=scene.id, actor_id=t.id))
        space["positions"][str(t.id)] = {
            "zone": "tables",
            "engaged_with": [str(w.actors["Alex"])],
            "cover": "none",
            "elevated": False,
        }
    space["positions"][str(w.actors["Alex"])]["engaged_with"] = [str(t1.id), str(t2.id)]
    scene.state = {**scene.state, "space": space}
    await session.flush()
    sides = {a: "party" for a in (w.actors["Alex"], w.actors["Elara"], w.actors["Tomas"])} | {
        t1.id: "thieves",
        t2.id: "thieves",
    }  # Mira/Renn: bystanders
    enc = await orch.actions.start_encounter(w.h, scene.id, sides)
    # make it Alex's turn
    while enc.current_actor != str(w.actors["Alex"]):
        actor, _ = await orch.actions.next_turn(w.h, scene.id)
        enc = (await orch.actions.load_scene(w.h, scene.id)).ctx.encounter
    return t1, t2


async def test_ambiguous_target_yields_clarification_with_nothing_committed_then_resumes(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider().register(
        "intent_interpreter",
        responder({"Attack him": intent("do", intents=[("attack", "a_thief", None)])}),
    )
    orch = make(session, fake)
    t1, t2 = await two_thieves(session, w, orch)
    n_events = len(
        (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    with pytest.raises(NeedsClarification) as exc:
        await orch.process_player_input(w.h, PlayRequest(w.actors["Alex"], "Attack him."))
    cl = exc.value
    assert {c["ref"] for c in cl.candidates} == {
        "a_thief",
        "a_thief_2",
    } and cl.original_input == "Attack him."
    pending = (
        await session.execute(
            select(PendingClarification).where(PendingClarification.actor_id == w.actors["Alex"])
        )
    ).scalar_one()
    assert pending.status == "open" and pending.clarification_id == cl.clarification_id
    assert (
        len(
            (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
            .scalars()
            .all()
        )
        == n_events
    )  # nothing committed
    assert (
        not (await session.execute(select(Action).where(Action.actor_id == w.actors["Alex"])))
        .scalars()
        .all()
    )
    assert (
        (
            await session.execute(
                select(TurnMetrics).where(TurnMetrics.campaign_id == w.h.campaign_id)
            )
        )
        .scalars()
        .all()
    )  # still measured
    # resume by answering
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "the second one", clarification_id=cl.clarification_id)
    )
    assert (
        res.actions
        and res.actions[0]["action"] == "action.attack"
        and res.actions[0]["target"] == str(t2.id)
    )
    assert res.actions[0]["status"] in ("succeeded", "failed")
    assert (await session.get(PendingClarification, pending.id)).status == "answered"
    assert res.visible_rolls and res.visible_rolls[0]["purpose"].endswith("attack")
    # an unrelated input while a clarification is open cancels it
    fake.register(
        "intent_interpreter", responder({"wait": intent("do", intents=[("wait", None, None)])})
    )
    with pytest.raises(NeedsClarification):
        await orch.process_player_input(w.h, PlayRequest(w.actors["Alex"], "Attack him."))
    await orch.process_player_input(w.h, PlayRequest(w.actors["Alex"], "I wait."))
    opens = (
        (
            await session.execute(
                select(PendingClarification).where(
                    PendingClarification.actor_id == w.actors["Alex"],
                    PendingClarification.status == "open",
                )
            )
        )
        .scalars()
        .all()
    )
    assert opens == []


@pytest.mark.parametrize(
    "class_, policy, expected, adjudicator_called",
    [
        ("self_minor", "personal", "accepted", False),
        ("self_minor", "strict", "adjudicated_accepted", True),
        ("self_major", "strict", "refused", False),
        ("self_major", "collaborative", "adjudicated_accepted", True),
        ("world_minor", "personal", "adjudicated_accepted", True),
        ("world_minor", "collaborative", "accepted", False),
        ("world_major", "personal", "refused", False),
        ("world_major", "collaborative", "adjudicated_accepted", True),
        ("contradiction", "collaborative", "refused", False),
    ],
)
async def test_player_assertions_per_class_and_policy(
    session: AsyncSession, frostbridge: World, class_, policy, expected, adjudicator_called
) -> None:
    w = frostbridge
    campaign = await session.get(Campaign, w.h.campaign_id)
    campaign.settings = {**campaign.settings, "player_canon_policy": policy}
    await session.flush()
    predicate = {
        "self_minor": "has the compass my father gave me",
        "self_major": "always carried an enchanted blade",
        "world_minor": "there is a back door out of the tavern",
        "world_major": "there is a secret passage into the guard house",
        "contradiction": "Renn is the killer",
    }[class_]
    fake = FakeModelProvider().register(
        "intent_interpreter",
        responder(
            {
                "I check": intent(
                    "do",
                    asserted=[
                        {
                            "proposition": {"predicate": predicate},
                            "class": class_,
                            "mechanical_weight": "none",
                        }
                    ],
                )
            }
        ),
    )
    fake.register(
        "rules_adjudicator",
        {
            "requires_check": False,
            "check": None,
            "on_success": [],
            "on_failure": [],
            "time_cost_seconds": 0,
            "precedent_tags": [],
            "scope": "single_use",
            "summary": "plausible; accepted as plain fiction",
        },
    )
    orch = make(session, fake)
    res = await orch.process_player_input(w.h, PlayRequest(w.actors["Alex"], "I check the thing."))
    a = res.assertions[0]
    assert a["class"] == class_ and a["result"] == expected, a
    assert (res.metrics["calls_by_role"].get("rules_adjudicator", 0) == 1) is adjudicator_called
    facts = (
        (
            await session.execute(
                select(Fact).where(Fact.campaign_id == w.h.campaign_id, Fact.predicate == predicate)
            )
        )
        .scalars()
        .all()
    )
    if expected.endswith("accepted"):
        assert (
            len(facts) == 1
            and facts[0].canon_status == "established"
            and facts[0].provenance["source"].startswith("player_assertion")
        )
        if class_ == "self_minor":
            items = (
                (
                    await session.execute(
                        select(Item).where(
                            Item.possessor_entity_id == w.entities["Alex"],
                            Item.item_type == "keepsake",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(items) == 1 and items[0].mechanical_snapshot.get("equipped") is False
    else:
        assert facts == [] and any(n.startswith("assertion") for n in res.dev_notes)
    if class_ == "contradiction":
        stated = (
            (
                await session.execute(
                    select(Belief).where(
                        Belief.actor_id == w.actors["Alex"], Belief.belief_type == "stated"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert stated and stated[-1].proposition["predicate"] == predicate
        from app.persistence.repositories.objective import ObjectiveWorldRepository

        truth = await ObjectiveWorldRepository(session).fact_by_key(
            w.h.campaign_id, "renn_killed_oric"
        )
        assert truth.subject_entity_id == w.entities["Renn"]  # unchanged either way


async def test_conversation_time_bands_and_scene_cap(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider().register(
        "intent_interpreter",
        responder(
            {
                "long story": intent(
                    "say",
                    intents=[("say", "mira", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {"predicate": "told a long story"},
                            "stance": "asserts_true",
                        }
                    ],
                    band="long",
                ),
                "quick word": intent(
                    "say", intents=[("say", "mira", None)], conveys=[], band="normal"
                ),
            }
        ),
    )
    orch = make(session, fake)
    tick0 = (await orch.world.clock(w.h)).current_tick
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I tell Mira a long story: "..."')
    )
    assert (
        res.time_advanced_seconds == 180
        and (await orch.world.clock(w.h)).current_tick == tick0 + 180
    )
    ev = (
        (
            await session.execute(
                select(Event)
                .where(Event.campaign_id == w.h.campaign_id, Event.event_type == "time.advanced")
                .order_by(Event.sequence_number.desc())
            )
        )
        .scalars()
        .first()
    )
    assert ev.payload["reason"] == "conversation:long" and ev.payload["seconds"] == 180
    scene = await session.get(Scene, w.scene)
    scene.state = {**scene.state, "conversation_seconds": 3590}
    await session.flush()
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'A quick word with Mira: "hello"')
    )
    assert res.time_advanced_seconds == 10  # capped at 60 minutes per scene
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'A quick word with Mira: "again"')
    )
    assert (
        res.time_advanced_seconds == 0
        and (await session.get(Scene, w.scene)).state.get("conversation_late") is True
    )


async def test_adjudicator_rulings_check_no_check_and_rejected(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider().register(
        "intent_interpreter", responder({"shove": intent("do", intents=[("shove", None, None)])})
    )
    fake.register(
        "rules_adjudicator",
        {
            "requires_check": True,
            "check": {
                "check": "check.core",
                "attribute": "attr.might",
                "skill": "skill.athletics",
                "difficulty": "moderate",
            },
            "on_success": [
                {"type": "grant_capability", "params": {"capability": "barricade:doorway"}}
            ],
            "on_failure": [],
            "time_cost_seconds": 12,
            "precedent_tags": ["barricade"],
            "scope": "single_use",
            "summary": "Might + Athletics vs moderate",
        },
    )
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I shove the heavy shelf over the doorway.")
    )
    assert res.actions[0]["action"] == "action.improvised" and res.actions[0]["status"] in (
        "succeeded",
        "failed",
    )
    assert res.metrics["calls_by_role"] == {"intent_interpreter": 1, "rules_adjudicator": 1}
    rolls = (
        (
            await session.execute(
                select(Roll).where(Roll.actor_id == w.actors["Alex"], Roll.purpose == "athletics")
            )
        )
        .scalars()
        .all()
    )
    assert len(rolls) == 1 and res.visible_rolls
    act = (
        (await session.execute(select(Action).where(Action.action_key == "action.improvised")))
        .scalars()
        .first()
    )
    assert act is not None and act.resolution_event_id is not None
    if res.actions[0]["status"] == "succeeded":
        assert res.time_advanced_seconds == 0 and (await orch.world.clock(w.h)).current_tick >= 12
    # no check needed
    fake2 = FakeModelProvider().register(
        "intent_interpreter", responder({"nudge": intent("do", intents=[("nudge", None, None)])})
    )
    fake2.register(
        "rules_adjudicator",
        {
            "requires_check": False,
            "check": None,
            "on_success": [{"type": "grant_capability", "params": {"capability": "noted:nudge"}}],
            "on_failure": [],
            "time_cost_seconds": 2,
            "precedent_tags": [],
            "scope": "single_use",
            "summary": "trivial",
        },
    )
    res2 = await make(session, fake2).process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I nudge the cup.")
    )
    assert res2.actions[0]["status"] == "succeeded" and not res2.visible_rolls
    # invalid primitive: rejected by code, nothing applied
    fake3 = FakeModelProvider().register(
        "intent_interpreter", responder({"hack": intent("do", intents=[("hack", None, None)])})
    )
    fake3.register(
        "rules_adjudicator",
        {
            "requires_check": False,
            "check": None,
            "on_success": [{"type": "run_python", "params": {"code": "os.system('x')"}}],
            "on_failure": [],
            "time_cost_seconds": 2,
            "precedent_tags": [],
            "scope": "single_use",
            "summary": "nope",
        },
    )
    n_actions = len((await session.execute(select(Action))).scalars().all())
    res3 = await make(session, fake3).process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I hack the mainframe.")
    )
    assert not res3.actions and any("ruling rejected" in n for n in res3.dev_notes)
    assert len((await session.execute(select(Action))).scalars().all()) == n_actions


async def test_ooc_and_private_commit_nothing_in_world(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider().register(
        "table_assistant", "Sure. Your character can take it slowly; nothing has to happen yet."
    )
    orch = make(session, fake)  # OOC asks the table assistant; nothing else is called
    n = len(
        (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "/ooc can we slow down a bit?")
    )
    assert res.channel == "ooc" and res.ooc.startswith("Sure.")
    assert res.metrics["calls_by_role"] == {"table_assistant": 1}
    # the assistant sees only Alex's perspective: no hidden truth reaches it
    asked = [
        c.request.user
        for c in fake.calls
        if "table_assistant" in c.request.profile + c.request.system
    ]
    assert asked and not any("killed" in u.lower() for u in asked)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "/think I don't trust the captain.")
    )
    assert res.channel == "private" and res.metrics["sync_model_calls"] == 0
    assert (
        len(
            (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
            .scalars()
            .all()
        )
        == n
    )
    private = (
        (
            await session.execute(
                select(TranscriptMessage).where(TranscriptMessage.channel == "private")
            )
        )
        .scalars()
        .all()
    )
    assert private and private[-1].raw_text == "I don't trust the captain."
    assert (
        not (
            await session.execute(
                select(Belief).where(
                    Belief.actor_id == w.actors["Alex"],
                    Belief.proposition_key.like("%trust the captain%"),
                )
            )
        )
        .scalars()
        .all()
    )


async def test_play_endpoint_json_and_sse_ordering(
    session: AsyncSession, frostbridge: World, app, client
) -> None:
    w = frostbridge
    await session.commit()
    app.state.provider.register(
        "intent_interpreter",
        responder({"look around": intent("do", intents=[("search", "tables", None)])}),
    )
    body = {"actor_id": str(w.actors["Alex"]), "text": "I look around the tables carefully."}
    r = await client.post(f"/api/v1/campaigns/{w.h.campaign_id}/play", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (
        out["actions"][0]["action"] == "action.search"
        and out["metrics"]["sync_model_calls"] == 1
        and out["versions"]["scene_version"]
    )
    assert out["narration"] is None  # plain structured result until 06c
    # streaming: accepted → mechanics → complete, and never narration before mechanics
    r = await client.post(
        f"/api/v1/campaigns/{w.h.campaign_id}/play",
        json=body,
        headers={"accept": "text/event-stream"},
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [(line[7:],) for line in r.text.splitlines() if line.startswith("event: ")]
    names = [e[0] for e in events]
    assert (
        names[0] == "accepted"
        and "mechanics" in names
        and names[-2:] == ["complete", "result"]
        or names[-1] == "result"
    )
    assert names.index("mechanics") < names.index("complete") and "narration_delta" not in names
    data = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert any("metrics" in d for d in data)
    # AI actor: refused
    r = await client.post(
        f"/api/v1/campaigns/{w.h.campaign_id}/play",
        json={**body, "actor_id": str(w.actors["Elara"])},
    )
    assert r.status_code == 403
    # stale client state
    r = await client.post(
        f"/api/v1/campaigns/{w.h.campaign_id}/play",
        json={**body, "client_state": {"known_scene_version": 999}},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_STATE"
    tm = (
        (
            await session.execute(
                select(TurnMetrics).where(TurnMetrics.campaign_id == w.h.campaign_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(tm) >= 3
    _ = uuid
