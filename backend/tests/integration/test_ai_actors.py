"""Milestone 06b: AI players and NPCs act through proposals, speak with structured information
content, and keep deception private.

Tests (task card): independent choice vs. the player's wish; NPC lie → Claim not Fact;
`conveys[]` authorization rejection; Claim Extractor only on the fallback path; the Frostbridge
whisper belief table; autonomy pause; two actors targeting one dagger with revalidation;
fallback policy reuse when the situation is unchanged; the tavern-scene acceptance table."""

from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider, ModelRequest
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import (
    Belief,
    Claim,
    Event,
    Fact,
    Item,
    ModelRun,
    RelationshipDelta,
    Scene,
)
from app.services.ai_actors import Decision
from app.services.orchestrator import PlayRequest, SessionOrchestrator
from app.services.perspective import PerspectiveService
from app.services.turns import Turn, budget_from_settings
from tests.fixtures.frostbridge import World
from tests.integration.test_orchestrator import intent, responder, two_thieves

pytestmark = pytest.mark.integration

REF_LINE = re.compile(r"(b_[0-9a-f]{8}): .*?{}.*?\[fact (f_[0-9a-f]{8})\]")


def make(session: AsyncSession, fake: FakeModelProvider, **settings) -> SessionOrchestrator:
    return SessionOrchestrator(
        session,
        Settings(a9_token="", **{"narrator_enabled": False, **settings}),
        engine=RulesEngine.load("core_adventure", master_seed=11),
        provider=fake,
    )


def is_actor(req: ModelRequest, name: str) -> bool:
    return f"You are {name}" in req.user


def fact_ref(req: ModelRequest, predicate_fragment: str) -> str:
    """The f_ ref of a belief line in this request's context that mentions the fragment."""
    m = re.search(
        r"(b_[0-9a-f]{8}): [^\n]*"
        + re.escape(predicate_fragment)
        + r"[^\n]*\[fact (f_[0-9a-f]{8})\]",
        req.user,
    )
    assert m, f"no fact line for {predicate_fragment!r} in context:\n{req.user[-1500:]}"
    return m.group(2)


def npc(
    text: str | None,
    conveys=(),
    *,
    act="answer",
    knowingly_false=False,
    intentions=(),
    emotions=(),
    relationships=(),
    fallback=None,
    summary="in character",
):
    return {
        "decision_summary": summary,
        "speech_act": {"type": act, "knowingly_false": knowingly_false},
        "spoken_text": text,
        "conveys": list(conveys),
        "intentions": list(intentions),
        "belief_proposals": [],
        "emotion_proposals": list(emotions),
        "relationship_proposals": list(relationships),
        "fallback_policy": fallback,
    }


def pc(
    text: str | None,
    conveys=(),
    *,
    channel="say",
    target=None,
    intentions=(),
    beliefs=(),
    emotions=(),
    relationships=(),
    fallback=None,
    summary="in character",
):
    return {
        "decision_summary": summary,
        "spoken_text": text,
        "speech_channel": channel,
        "speech_target_ref": target,
        "conveys": list(conveys),
        "intentions": list(intentions),
        "belief_proposals": list(beliefs),
        "emotion_proposals": list(emotions),
        "goal_updates": [],
        "relationship_proposals": list(relationships),
        "fallback_policy": fallback,
    }


def by_actor(table: dict[str, dict | callable]):
    def pick(req: ModelRequest):
        for name, out in table.items():
            if is_actor(req, name):
                return out(req) if callable(out) else out
        raise AssertionError(f"no fixture for actor in request: {req.user[:200]}")

    return pick


async def beliefs_of(session: AsyncSession, actor_id: uuid.UUID) -> dict[tuple[str, str], float]:
    """(predicate, type) -> confidence, excluding seeded beliefs and 'asserted' meta-beliefs."""
    psv = PerspectiveService(session)
    return {
        (b.proposition["predicate"], b.belief_type): b.confidence
        for b in await psv.beliefs(actor_id)
        if b.source_type != "seeded" and b.proposition["predicate"] != "asserted"
    }


# --- independent choice -----------------------------------------------------------------------


async def test_ai_player_chooses_for_herself_not_for_the_player(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder(
            {
                "search the back room": intent(
                    "say",
                    intents=[("tell", "elara", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {"predicate": "asks Elara to search the back room"},
                            "stance": "question",
                        }
                    ],
                    band="brief",
                )
            }
        ),
    )
    fake.register(
        "ai_player",
        by_actor(
            {
                "Elara": pc(
                    "No. I am not leaving the room while that captain is at the door.",
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "self",
                                "predicate": "refuses to leave the room",
                            },
                            "stance": "asserts_true",
                            "about_speaker_self": True,
                        }
                    ],
                    intentions=[],  # she declines; nothing is proposed
                    emotions=[{"emotion": "wary", "intensity": 0.6}],
                ),
            }
        ),
    )
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I tell Elara "search the back room".')
    )
    assert res.metrics["reactions"]["visible"] == 1 and res.metrics["reactions"]["spoke"] == 1
    assert res.metrics["calls_by_role"] == {"intent_interpreter": 1, "ai_player": 1}
    elara_lines = [s for s in res.speakers if s["actor_id"] == str(w.actors["Elara"])]
    assert elara_lines and elara_lines[0]["text"].startswith("No.")
    # her refusal reached Alex as a Claim; she moved nowhere; her emotion is state with an event
    alex = await beliefs_of(session, w.actors["Alex"])
    assert ("refuses to leave the room", "believed") in alex or (
        "refuses to leave the room",
        "suspected",
    ) in alex
    scene = await session.get(Scene, w.scene)
    assert scene.state["space"]["positions"][str(w.actors["Elara"])]["zone"] == "tables"
    emos = await orch.ai.psychology.emotions(w.actors["Elara"])
    assert [e.emotion_key for e in emos] == ["wary"] and emos[0].source_event_id is not None
    # Tomas (not addressed, no new information) did not get a call
    assert not any(
        FakeModelProvider.role_of(c.request) == "ai_player" and is_actor(c.request, "Tomas")
        for c in fake.calls
    )


# --- NPC lie: Claim, not Fact -----------------------------------------------------------------


async def test_npc_lie_creates_claim_and_recipient_belief_but_no_fact(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder(
            {
                "last speak": intent(
                    "say",
                    intents=[("ask", "a_man_you_have_not_met", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "a_man_you_have_not_met",
                                "predicate": "last spoke to Oric when",
                            },
                            "stance": "question",
                        }
                    ],
                    band="brief",
                )
            }
        ),
    )
    fake.register(
        "npc_actor",
        by_actor(
            {
                "Renn": lambda req: npc(
                    "Weeks ago.",
                    conveys=[
                        {
                            "kind": "fact_ref",
                            "ref_id": fact_ref(req, "met privately"),
                            "stance": "asserts_false",
                            "contradicts_ref": fact_ref(req, "met privately"),
                        }
                    ],
                    act="lie",
                    knowingly_false=True,
                ),
                "Mira": npc(None, act="silence"),
            }
        ),
    )
    orch = make(session, fake)
    await w.knowledge.learn_identity(w.h, w.actors["Renn"], w.entities["Oric"], "Oric Dane")
    facts_before = len((await session.execute(select(Fact))).scalars().all())
    res = await orch.process_player_input(
        w.h,
        PlayRequest(
            w.actors["Alex"], 'I ask the stranger at the door "when did you last speak to Oric?"'
        ),
    )
    assert res.metrics["calls_by_role"].get("npc_actor", 0) >= 1
    renn_claims = (
        (await session.execute(select(Claim).where(Claim.speaker_actor_id == w.actors["Renn"])))
        .scalars()
        .all()
    )
    assert len(renn_claims) == 1
    c = renn_claims[0]
    assert c.deliberate_false is True and c.speaker_stance == "asserts_false"
    assert c.source_fact_id == w.facts["renn_met_oric"] and c.conveyance_source == "structured"
    assert len((await session.execute(select(Fact))).scalars().all()) == facts_before
    psv = PerspectiveService(session)
    # Tomas (stranger to Renn) lands at suspected ≈ 0.35–0.45; the lie flag never reaches him
    tomas = await beliefs_of(session, w.actors["Tomas"])
    key = ("not met privately the night before the disappearance", "suspected")
    assert key in tomas and 0.3 <= tomas[key] <= 0.5
    heard = [h for h in await psv.heard_claims(w.actors["Tomas"]) if h.claim_id == c.id]
    assert heard and not hasattr(heard[0], "deliberate_false")
    # Renn keeps exactly one belief about the meeting: the known fact
    renn = [
        b
        for b in await psv.beliefs(w.actors["Renn"])
        if "met privately" in b.proposition["predicate"]
    ]
    assert len(renn) == 1 and renn[0].belief_type == "known"
    # the human heard Renn: the reply is in the response
    assert any(
        s["actor_id"] == str(w.actors["Renn"]) and s["text"] == "Weeks ago." for s in res.speakers
    )


# --- conveys[] authorization ------------------------------------------------------------------


async def test_ai_output_referencing_knowledge_outside_its_context_is_rejected(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder({"think": intent("say", intents=[("ask", "elara", None)], band="brief")}),
    )
    secret = str(w.facts["renn_killed_oric"])
    table = {
        "Elara": pc(
            "Renn killed Oric, I am sure of it.",
            conveys=[{"kind": "fact_ref", "ref_id": secret, "stance": "asserts_true"}],
        ),
        "Tomas": pc(None),
    }
    fake.register("ai_player", by_actor(table))
    orch = make(session, fake)
    claims_before = len((await session.execute(select(Claim))).scalars().all())
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I ask Elara "what do you think?"')
    )
    assert res.metrics["reactions"]["rejected"] == 1 and res.metrics["reactions"]["spoke"] == 0
    assert len((await session.execute(select(Claim))).scalars().all()) == claims_before
    assert not any(s["actor_id"] == str(w.actors["Elara"]) for s in res.speakers)
    leaks = (
        (
            await session.execute(
                select(Event).where(
                    Event.event_type == "proposal.rejected_leakage",
                    Event.campaign_id == w.h.campaign_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert leaks and leaks[-1].payload["actor_id"] == str(w.actors["Elara"])
    # a short ref that was never supplied is treated the same way
    table["Elara"] = pc("Trust me.", conveys=[{"kind": "fact_ref", "ref_id": "f_deadbeef"}])
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I ask Elara "what do you think?"')
    )
    assert res.metrics["reactions"]["rejected"] == 1
    assert len((await session.execute(select(Claim))).scalars().all()) == claims_before


# --- Claim Extractor only on the fallback path -------------------------------------------------


async def test_claim_extractor_runs_once_and_only_when_conveys_is_incomplete(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder({"Oric": intent("say", intents=[("ask", "mira", None)], band="brief")}),
    )
    # Mira answers at length, names Oric, and supplies no conveys at all → fallback
    table = {
        "Mira": npc(
            "Oric drank here most nights. Paid his tab late, but he paid.",
            conveys=[],
            act="answer",
        ),
        "Renn": npc(None, act="silence"),
    }
    fake.register("npc_actor", by_actor(table))
    fake.register(
        "claim_extractor",
        {
            "conveys": [
                {
                    "kind": "proposition",
                    "proposition": {
                        "subject_entity_id": "oric",
                        "predicate": "drank here most nights",
                    },
                    "stance": "asserts_true",
                },
                {
                    "kind": "proposition",
                    "proposition": {"subject_entity_id": "oric", "predicate": "paid his tab late"},
                    "stance": "asserts_true",
                },
            ]
        },
    )
    orch = make(session, fake)
    # Mira knows Oric by name (so his name in her text counts as a mention)
    await w.knowledge.learn_identity(w.h, w.actors["Mira"], w.entities["Oric"], "Oric")
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I ask Mira "did you know Oric?"')
    )
    assert res.metrics["calls_by_role"].get("claim_extractor") == 1
    mira_claims = (
        (await session.execute(select(Claim).where(Claim.speaker_actor_id == w.actors["Mira"])))
        .scalars()
        .all()
    )
    assert {c.predicate for c in mira_claims} == {"drank here most nights", "paid his tab late"}
    assert all(c.conveyance_source == "structured" for c in mira_claims)
    # Alex now holds what she said, as told-beliefs
    alex = await beliefs_of(session, w.actors["Alex"])
    assert ("drank here most nights", "suspected") in alex
    # a complete, phatic or structured answer never triggers it
    table["Mira"] = npc("Fine.", conveys=[])
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I ask Mira "did you know Oric well?"')
    )
    assert "claim_extractor" not in res.metrics["calls_by_role"]


# --- the Frostbridge whisper -------------------------------------------------------------------


async def test_whisper_belief_table_with_ai_reaction(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder(
            {
                "Mira had something": intent(
                    "whisper",
                    intents=[("whisper", "elara", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "mira",
                                "predicate": "involved in the disappearance of",
                                "object_entity_id": "oric",
                            },
                            "stance": "uncertain",
                        }
                    ],
                    band="brief",
                )
            }
        ),
    )
    fake.register(
        "ai_player",
        by_actor(
            {
                "Elara": pc(
                    "Keep your voice down. I will watch her.",
                    channel="whisper",
                    target="alex",
                    conveys=[],
                    relationships=[
                        {
                            "target_ref": "alex",
                            "dimension": "trust",
                            "delta": 3,
                            "reason": "confided in me",
                        }
                    ],
                )
            }
        ),
    )
    orch = make(session, fake)
    # Alex refers to Oric by name in the proposition: give him the name
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Oric"], "Oric")
    res = await orch.process_player_input(
        w.h,
        PlayRequest(
            w.actors["Alex"],
            'I whisper to Elara "I think Mira had something to do with Oric\'s disappearance."',
        ),
    )
    alex, elara, tomas, mira = (w.actors[n] for n in ("Alex", "Elara", "Tomas", "Mira"))
    assert await beliefs_of(session, alex) == {("involved in the disappearance of", "stated"): 0.55}
    assert await beliefs_of(session, elara) == {
        ("involved in the disappearance of", "suspected"): 0.585
    }
    assert await beliefs_of(session, tomas) == {}
    assert await beliefs_of(session, mira) == {}
    psv = PerspectiveService(session)
    eb = {(b.proposition["predicate"], b.belief_type): b for b in await psv.beliefs(elara)}
    assert eb[("asserted", "known")].confidence == 1.0  # Elara knows Alex said it
    assert await psv.heard_claims(tomas) == [] and await psv.heard_claims(mira) == []
    # Elara whispered back: Alex heard it, Tomas did not; her trust delta is event-linked
    assert [s for s in res.speakers if s["actor_id"] == str(elara)][0]["recipients"] == [str(alex)]
    rel = await psv.repo.relationship(elara, w.entities["Alex"])
    deltas = (
        (
            await session.execute(
                select(RelationshipDelta).where(
                    RelationshipDelta.relationship_id == rel.id,
                    RelationshipDelta.reason == "confided in me",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(deltas) == 1 and deltas[0].delta == 3 and deltas[0].event_id is not None
    await session.refresh(rel)
    assert rel.trust == 63 and rel.last_changed_event_id == deltas[0].event_id


# --- autonomy pause ----------------------------------------------------------------------------


async def test_autonomy_gate_pauses_item_transfer_even_when_the_model_wants_it(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    # the dagger lies on the floor at the tables, so picking it up is a legal intention
    item = await session.get(Item, w.dagger)
    item.possessor_entity_id, item.location_id, item.zone_key = None, w.tavern, "tables"
    await session.flush()
    fake = FakeModelProvider()
    intents = {"dagger": intent("say", intents=[("tell", "elara", None)], band="brief")}
    fake.register("intent_interpreter", responder(intents))
    table = {
        "Elara": pc(
            "Give it here, then.",
            intentions=[{"action_type": "pick_up", "target_ref": "veyra_s_chipped_dagger"}],
        ),
    }
    fake.register("ai_player", by_actor(table))
    orch = make(session, fake)
    scene = await session.get(Scene, w.scene)
    cands = await orch._candidates(w.h, w.actors["Elara"], scene)
    assert "veyra_s_chipped_dagger" in {c.ref for c in cands}
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I tell Elara "take the dagger".')
    )
    assert res.metrics["reactions"]["paused"] == 1
    item = await session.get(Item, w.dagger)
    assert item.possessor_entity_id is None  # paused: nothing moved
    paused = (
        (await session.execute(select(Event).where(Event.event_type == "autonomy.paused")))
        .scalars()
        .all()
    )
    assert (
        paused
        and paused[-1].payload["domain"] == "item_transfer"
        and paused[-1].payload["level"] == "ask"
    )
    scene = await session.get(Scene, w.scene)
    assert scene.state["autonomy_pending"][0]["actor_id"] == str(w.actors["Elara"])
    # Tomas's autonomy allows it: the same intention executes
    table["Tomas"] = pc(
        "I will hold on to it.",
        intentions=[{"action_type": "pick_up", "target_ref": "veyra_s_chipped_dagger"}],
    )
    table["Elara"] = pc(None)
    intents["keep it"] = intent("say", intents=[("tell", "tomas", None)], band="brief")
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I tell Tomas "you keep it, then".')
    )
    item = await session.get(Item, w.dagger)
    assert item.possessor_entity_id == w.entities["Tomas"]


# --- concurrent snapshots, revalidation -------------------------------------------------------


async def test_two_actors_target_one_dagger_second_proposal_is_invalidated(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    item = await session.get(Item, w.dagger)
    item.possessor_entity_id, item.location_id, item.zone_key = None, w.tavern, "tables"
    await session.flush()
    fake = FakeModelProvider()
    both = {
        "Elara": pc(
            "Mine.", intentions=[{"action_type": "pick_up", "target_ref": "veyra_s_chipped_dagger"}]
        ),
        "Tomas": pc(
            "I have it.",
            intentions=[{"action_type": "pick_up", "target_ref": "veyra_s_chipped_dagger"}],
        ),
    }
    fake.register("ai_player", by_actor(both))
    orch = make(session, fake)
    await orch.ai.psychology.set_ai_profile(
        w.actors["Elara"], autonomy={"item_transfer": "autonomous"}
    )
    scene = await session.get(Scene, w.scene)
    turn = Turn(w.h, budget=budget_from_settings(orch.settings))
    elara = await orch.perspective.repo.actor(w.actors["Elara"])
    tomas = await orch.perspective.repo.actor(w.actors["Tomas"])
    decisions = await orch.ai.decide_many(
        w.h,
        scene,
        [elara, tomas],
        {elara.id: "Loot on the floor.", tomas.id: "Loot on the floor."},
        turn,
    )
    assert len(decisions) == 2 and all(isinstance(d, Decision) and d.output for d in decisions)
    assert {d.based_on_scene_version for d in decisions} == {scene.version}  # same snapshot
    first = await orch.ai.apply(w.h, scene.id, decisions[0], turn)
    second = await orch.ai.apply(w.h, scene.id, decisions[1], turn)
    assert first.actions[0]["status"] == "succeeded"
    assert second.actions[0]["status"] == "invalidated"
    item = await session.get(Item, w.dagger)
    assert item.possessor_entity_id == w.entities["Elara"]
    inv = (
        (
            await session.execute(
                select(Event).where(
                    Event.event_type == "proposal.invalidated",
                    Event.campaign_id == w.h.campaign_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(inv) == 1 and inv[0].payload["actor_id"] == str(w.actors["Tomas"])


# --- fallback policy in combat -----------------------------------------------------------------


async def test_fallback_policy_replaces_model_calls_while_the_situation_is_unchanged(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder({"wait": intent("do", intents=[("wait", None, None)])}),
    )

    def thief(req: ModelRequest):
        return npc(
            None,
            intentions=[{"action_type": "attack", "target_ref": "alex"}],
            fallback={"target_ref": "alex", "intent": "attack", "flee_below": 0.3},
        )

    fake.register(
        "npc_actor",
        by_actor(
            {
                "Dock thief": thief,
                "Second thief": thief,
                "Mira": npc(None, act="silence"),
                "Renn": npc(None, act="silence"),
            }
        ),
    )
    fake.register(
        "ai_player",
        by_actor(
            {
                "Elara": pc(
                    None,
                    intentions=[{"action_type": "attack", "target_ref": "a_thief"}],
                    fallback={"target_ref": "a_thief", "intent": "attack"},
                ),
                "Tomas": pc(
                    None,
                    intentions=[{"action_type": "attack", "target_ref": "a_thief"}],
                    fallback={"target_ref": "a_thief", "intent": "attack"},
                ),
            }
        ),
    )
    orch = make(session, fake)
    for a in (w.actors["Elara"], w.actors["Tomas"]):
        await orch.ai.psychology.set_ai_profile(a, autonomy={"combat": "autonomous"})
    t1, t2 = await two_thieves(session, w, orch)
    # the thieves need to know Alex by some name to target "alex"; a descriptor works too
    # round 1: Alex waits → every AI combatant gets one model call and records a policy
    res1 = await orch.process_player_input(w.h, PlayRequest(w.actors["Alex"], "I wait."))
    log1 = res1.metrics["ai_combat_turns"]
    assert log1 and all(e["source"] in ("model", "policy", "default_policy") for e in log1)
    calls1 = sum(res1.metrics["calls_by_role"].get(r, 0) for r in ("ai_player", "npc_actor"))
    assert calls1 >= 1
    scene = await session.get(Scene, w.scene)
    assert str(t1.id) in scene.state.get("fallback_policies", {}) or str(t2.id) in scene.state.get(
        "fallback_policies", {}
    )
    # round 2: nothing changed for a combatant whose target still stands → policy, no call
    res2 = await orch.process_player_input(w.h, PlayRequest(w.actors["Alex"], "I wait."))
    log2 = res2.metrics["ai_combat_turns"]
    policy_turns = [e for e in log2 if e["source"] == "policy"]
    assert policy_turns, log2
    calls2 = sum(res2.metrics["calls_by_role"].get(r, 0) for r in ("ai_player", "npc_actor"))
    assert calls2 < max(calls1, 1) + len(log2) - len(policy_turns)
    runs = (
        (
            await session.execute(
                select(ModelRun).where(ModelRun.turn_id == uuid.UUID(res2.metrics["turn_id"]))
            )
        )
        .scalars()
        .all()
    )
    assert all(
        r.role != "npc_actor" or r.actor_id not in {e["actor"] for e in policy_turns} for r in runs
    )


# --- acceptance: the tavern scene ---------------------------------------------------------------


async def test_tavern_scene_belief_stores_match_the_expected_table(
    session: AsyncSession, frostbridge: World
) -> None:
    """Alex asks Mira about Renn (partial truth), whispers his suspicion to Elara, hears Tomas
    defend the guard, and asks Renn directly (a lie). Each store afterwards is exact."""
    w = frostbridge
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Oric"], "Oric")
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Renn"], "Captain Renn")
    await w.knowledge.learn_identity(w.h, w.actors["Elara"], w.entities["Renn"], "Captain Renn")
    await w.knowledge.learn_identity(w.h, w.actors["Tomas"], w.entities["Renn"], "Captain Renn")
    await w.knowledge.learn_identity(w.h, w.actors["Mira"], w.entities["Oric"], "Oric")
    await w.knowledge.learn_identity(w.h, w.actors["Renn"], w.entities["Oric"], "Oric Dane")
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder(
            {
                "was Renn here": intent(
                    "say",
                    intents=[("ask", "mira", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "captain_renn",
                                "predicate": "was here the night Oric vanished",
                            },
                            "stance": "question",
                        }
                    ],
                    band="brief",
                ),
                "Mira had something": intent(
                    "whisper",
                    intents=[("whisper", "elara", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "mira",
                                "predicate": "involved in the disappearance of",
                                "object_entity_id": "oric",
                            },
                            "stance": "uncertain",
                        }
                    ],
                    band="brief",
                ),
                "what do you make of": intent(
                    "say",
                    intents=[("ask", "tomas", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "captain_renn",
                                "predicate": "is trustworthy",
                            },
                            "stance": "question",
                        }
                    ],
                    band="brief",
                ),
                "last speak": intent(
                    "say",
                    intents=[("ask", "captain_renn", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "captain_renn",
                                "predicate": "last spoke to Oric when",
                            },
                            "stance": "question",
                        }
                    ],
                    band="brief",
                ),
            }
        ),
    )
    fake.register(
        "npc_actor",
        by_actor(
            {
                "Mira": lambda req: npc(
                    "He was here that night. They argued. I did not hear about what.",
                    conveys=[
                        {
                            "kind": "fact_ref",
                            "ref_id": fact_ref(req, "met privately"),
                            "stance": "asserts_true",
                            "fidelity": "partial",
                        }
                    ],
                    act="answer",
                    emotions=[{"emotion": "fear", "intensity": 0.5}],
                ),
                "Renn": lambda req: npc(
                    "Weeks ago.",
                    conveys=[
                        {
                            "kind": "fact_ref",
                            "ref_id": fact_ref(req, "met privately"),
                            "stance": "asserts_false",
                            "contradicts_ref": fact_ref(req, "met privately"),
                        }
                    ],
                    act="lie",
                    knowingly_false=True,
                ),
            }
        ),
    )
    fake.register(
        "ai_player",
        by_actor(
            {
                "Elara": pc("Keep your voice down.", channel="whisper", target="alex"),
                "Tomas": pc(
                    "Captain Renn runs a tidy watch. Accusations need evidence.",
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "captain_renn",
                                "predicate": "runs a tidy watch",
                            },
                            "stance": "asserts_true",
                        }
                    ],
                ),
            }
        ),
    )
    orch = make(session, fake)
    alex = w.actors["Alex"]
    await orch.process_player_input(
        w.h, PlayRequest(alex, 'I ask Mira "was Renn here the night Oric vanished?"')
    )
    await orch.process_player_input(
        w.h,
        PlayRequest(
            alex,
            'I whisper to Elara "I think Mira had something to do with Oric\'s disappearance."',
        ),
    )
    await orch.process_player_input(
        w.h, PlayRequest(alex, 'I ask Tomas "what do you make of Captain Renn?"')
    )
    await orch.process_player_input(
        w.h, PlayRequest(alex, 'I ask Captain Renn "when did you last speak to Oric?"')
    )

    met = "met privately the night before the disappearance"
    not_met = "not " + met
    stores = {
        n: await beliefs_of(session, w.actors[n])
        for n in ("Alex", "Elara", "Tomas", "Mira", "Renn")
    }
    # Mira's partial truth reached everyone at the tables and the door
    for n in ("Alex", "Elara", "Tomas"):
        assert (met, "suspected") in stores[n], (n, stores[n])
    # Renn's lie: a weaker contradicting alternative for those who heard Mira first
    for n in ("Alex", "Elara", "Tomas"):
        lie = [k for k in stores[n] if k[0] == not_met]
        assert lie and stores[n][lie[0]] <= 0.35, (n, stores[n])
    # the whisper: Alex stated it, Elara suspects it, nobody else holds it
    assert stores["Alex"][("involved in the disappearance of", "stated")] == 0.55
    assert stores["Elara"][("involved in the disappearance of", "suspected")] == 0.585
    assert all(k[0] != "involved in the disappearance of" for k in stores["Tomas"])
    assert all(k[0] != "involved in the disappearance of" for k in stores["Mira"])
    # Tomas's defence reached Alex and Elara; Elara's whisper reply reached only Alex
    assert ("runs a tidy watch", "suspected") in stores["Alex"] or (
        "runs a tidy watch",
        "believed",
    ) in stores["Alex"]
    assert any(k[0] == "runs a tidy watch" for k in stores["Elara"])
    # Mira knows the truth: Renn's lie lands as a weaker alternative (rumor), her own partial
    # account adds nothing she did not hold; Renn likewise keeps his facts and only gains what
    # Tomas said. Neither learned the whisper.
    assert all(k[0] != met for k in stores["Mira"]) and stores["Mira"][(not_met, "rumor")] <= 0.1
    assert stores["Renn"] == {("runs a tidy watch", "suspected"): 0.35}, stores["Renn"]
    # objective truth untouched, deception private, provenance complete
    assert all(
        f.canon_status == "established"
        for f in (await session.execute(select(Fact))).scalars().all()
    )
    renn_claims = (
        (await session.execute(select(Claim).where(Claim.speaker_actor_id == w.actors["Renn"])))
        .scalars()
        .all()
    )
    assert len(renn_claims) == 1 and renn_claims[0].deliberate_false
    told = (
        (await session.execute(select(Belief).where(Belief.source_type == "told"))).scalars().all()
    )
    assert told and all(b.claim_id is not None and b.acquired_event_id is not None for b in told)


# --- regressions from the first live A9 sessions (06d design-iteration loop) ---------------------


async def test_model_written_ids_in_propositions_never_reach_the_claims_table(
    session: AsyncSession, frostbridge: World
) -> None:
    """GLM put the whisper target's *actor* id in subject_entity_id, and made-up uuids appear
    too. Actor ids map to the entity; unknown ids become free text; nothing crashes."""
    w = frostbridge
    elara_actor = str(w.actors["Elara"])
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder(
            {
                "knows more": intent(
                    "whisper",
                    intents=[("whisper", "elara", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": elara_actor,  # an actor id, not an entity id
                                "predicate": "should_watch_the_innkeeper",
                            },
                            "stance": "asserts_true",
                        },
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "11111111-2222-3333-4444-555555555555",
                                "predicate": "is hiding something",
                            },
                            "stance": "uncertain",
                        },
                    ],
                    band="brief",
                )
            }
        ),
    )
    fake.register("ai_player", by_actor({"Elara": pc(None)}))
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h,
        PlayRequest(
            w.actors["Alex"],
            "I whisper to Elara that she knows more than she says.",
            target_actor_ids=[w.actors["Elara"]],
        ),
    )
    assert res.speakers and res.speakers[0]["channel"] == "whisper"
    claims = (
        (await session.execute(select(Claim).where(Claim.speaker_actor_id == w.actors["Alex"])))
        .scalars()
        .all()
    )
    by_pred = {c.predicate: c for c in claims}
    assert by_pred["should watch the innkeeper"].subject_entity_id == w.entities["Elara"]
    assert by_pred["is hiding something"].subject_entity_id is None


async def test_explicit_speech_is_always_an_utterance_not_canon_or_action(
    session: AsyncSession, frostbridge: World
) -> None:
    """A /whisper that the interpreter read as a world assertion plus a 'conceal' action still
    produces exactly one whisper and no adjudication (player-authored canon is for deeds)."""
    w = frostbridge
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder(
            {
                "innkeeper": intent(
                    "whisper",
                    intents=[("conceal", None, None)],
                    asserted=[
                        {
                            "proposition": {"predicate": "the innkeeper is hiding something"},
                            "class": "world_minor",
                            "mechanical_weight": "none",
                        }
                    ],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "mira",
                                "predicate": "knows more than she is saying",
                            },
                            "stance": "uncertain",
                        }
                    ],
                    band="brief",
                )
            }
        ),
    )
    fake.register("ai_player", by_actor({"Elara": pc(None)}))
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h,
        PlayRequest(
            w.actors["Alex"],
            "/whisper I think the innkeeper knows more than she is saying.",
            target_actor_ids=[w.actors["Elara"]],
        ),
    )
    assert len([s for s in res.speakers if s["actor_id"] == str(w.actors["Alex"])]) == 1
    assert res.assertions == [] and "rules_adjudicator" not in res.metrics["calls_by_role"]
    assert any("ignored in explicit speech" in n for n in res.metrics["notes"])
    elara = await beliefs_of(session, w.actors["Elara"])
    assert ("knows more than she is saying", "suspected") in elara


async def test_assertion_refs_need_the_predicate_denials_need_only_the_names(
    session: AsyncSession, frostbridge: World
) -> None:
    """Mira referencing 'Renn met Oric privately' under 'Captain Renn's been in' is dropped
    (names alone are not corroboration); Renn's 'Weeks ago.' denial still lands."""
    w = frostbridge
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Oric"], "Oric")
    await w.knowledge.learn_identity(w.h, w.actors["Mira"], w.entities["Oric"], "Oric")
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder({"been in lately": intent("say", intents=[("ask", "mira", None)], band="brief")}),
    )
    fake.register(
        "npc_actor",
        by_actor(
            {
                "Mira": lambda req: npc(
                    "Oric? Not that I have seen. Captain Renn has been in, though.",
                    conveys=[
                        {
                            "kind": "fact_ref",
                            "ref_id": fact_ref(req, "met privately"),
                            "stance": "asserts_true",
                        }
                    ],
                ),
                "Renn": npc(None, act="silence"),
            }
        ),
    )
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I ask Mira "has Oric been in lately?"')
    )
    assert any("not corroborated" in n for n in res.metrics["notes"]), res.metrics["notes"]
    mira_claims = (
        (await session.execute(select(Claim).where(Claim.speaker_actor_id == w.actors["Mira"])))
        .scalars()
        .all()
    )
    assert all(c.source_fact_id != w.facts["renn_met_oric"] for c in mira_claims)
