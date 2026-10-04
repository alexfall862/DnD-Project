"""Milestone 07 — the Frostbridge deterministic vertical slice (frostbridge-demo.md §43,
testing/vertical-slice.md) with FakeModelProvider and a fixed RNG.

One scripted session walks: gate notice → tavern → Mira's evasion and partial reveal → the
private whisper → companion disagreement → split party (live warehouse / offscreen guard house)
→ ledger, dagger and mud discoveries → thief combat with an environmental improvisation →
reunion with knowledge still asymmetric → exchange → Renn's lie → four days of world clocks →
restart/reload → one more turn. Every step asserts the architecture property it exists for.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.providers import FakeModelProvider, ModelRequest
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.db import make_engine
from app.persistence.models import (
    Belief,
    Claim,
    Clue,
    ClueDiscovery,
    ContextSnapshot,
    Event,
    Fact,
    Item,
    Memory,
    ModelRun,
    Observation,
    Plan,
    RelationshipDelta,
    Roll,
    Scene,
    TurnMetrics,
    WorldClock,
)
from app.seeds.frostbridge import DAY, FrostbridgeWorld, seed_frostbridge
from app.services.documents import DocumentService
from app.services.mystery import MysteryService
from app.services.orchestrator import NeedsClarification, PlayRequest, SessionOrchestrator
from app.services.perspective import PerspectiveService
from app.services.scenes import SceneService
from app.services.schedule import ScheduleService
from tests.integration.test_ai_actors import fact_ref, is_actor, npc, pc
from tests.integration.test_orchestrator import intent

pytestmark = [pytest.mark.integration, pytest.mark.leakage, pytest.mark.replay]

MASTER_SEED = 7


# ---------------------------------------------------------------------------------------------
# fixtures: the fake models, scripted per actor and per situation
# ---------------------------------------------------------------------------------------------


def belief_ref(req: ModelRequest, fragment: str) -> str:
    m = re.search(r"(b_[0-9a-f]{8}): [^\n]*" + re.escape(fragment), req.user)
    assert m, f"no belief line for {fragment!r} in context:\n{req.user[-1500:]}"
    return m.group(1)


INTENTS = {
    "read the notice": intent("do", intents=[("read", "notice_nailed_to_the_gatepost", None)]),
    "head to the Red Lantern": intent(
        "do", intents=[("travel", "red_lantern_tavern", {"with": ["elara", "tomas"]})]
    ),
    "has Oric Dane been in": intent(
        "say",
        intents=[("ask", "the_innkeeper", None)],
        conveys=[
            {
                "kind": "proposition",
                "proposition": {"subject_entity_id": "oric_dane", "predicate": "was here lately"},
                "stance": "question",
            }
        ],
        band="brief",
    ),
    "between us": intent(
        "whisper",
        intents=[("whisper", "the_innkeeper", None)],
        conveys=[
            {
                "kind": "proposition",
                "proposition": {
                    "subject_entity_id": "oric_dane",
                    "predicate": "met someone here before he vanished",
                },
                "stance": "question",
            }
        ],
        band="brief",
    ),
    "had something to do with": intent(
        "whisper",
        intents=[("whisper", "elara", None)],
        conveys=[
            {
                "kind": "proposition",
                "proposition": {
                    "subject_entity_id": "the_innkeeper",
                    "predicate": "involved in the disappearance of",
                    "object_entity_id": "oric_dane",
                },
                "stance": "uncertain",
            }
        ],
        band="brief",
    ),
    "make of the captain": intent(
        "say",
        intents=[("ask", "tomas", None)],
        conveys=[
            {
                "kind": "proposition",
                "proposition": {"subject_entity_id": "captain_renn", "predicate": "is trustworthy"},
                "stance": "question",
            }
        ],
        band="brief",
    ),
    "guard house records": intent(
        "say",
        intents=[("ask", "tomas", None)],
        conveys=[
            {
                "kind": "proposition",
                "proposition": {
                    "subject_entity_id": "tomas",
                    "predicate": "should look at the guard house records",
                },
                "stance": "asserts_true",
            }
        ],
        band="brief",
    ),
    "shuttered warehouse": intent(
        "do",
        intents=[
            ("travel", "a_shuttered_warehouse_with_a_faded_merchant_sign", {"with": ["elara"]})
        ],
    ),
    "search the office": intent("do", intents=[("search", "office", None)]),
    "read the ledger": intent("do", intents=[("read", "oric_s_private_ledger", None)]),
    "search the main floor": intent("do", intents=[("search", "floor", None)]),
    "pick up the dagger": intent(
        "do", intents=[("move", "floor", None), ("pick_up", "veyra_s_chipped_dagger", None)]
    ),
    "Attack him": intent("do", intents=[("attack", "a_thief_in_dark_clothing", None)]),
    "shove the heavy shelf": intent("do", intents=[("shove", None, None)]),
    "wait": intent("do", intents=[("wait", None, None)]),
    "strike at the first thief": intent(
        "do", intents=[("attack", "a_thief_in_dark_clothing", None)]
    ),
    "over to the guard house": intent(
        "do", intents=[("travel", "guard_house", {"with": ["elara"]})]
    ),
    "found Oric's ledger": intent(
        "say",
        intents=[("say", "tomas", None)],
        conveys=[
            {
                "kind": "proposition",
                "proposition": {
                    "subject_entity_id": "oric_dane",
                    "predicate": "kept a ledger of dock shortfalls",
                },
                "stance": "asserts_true",
            }
        ],
        band="normal",
    ),
    "back to the tavern": intent(
        "do", intents=[("travel", "red_lantern_tavern", {"with": ["elara", "tomas"]})]
    ),
    "last speak to Oric": intent(
        "say",
        intents=[("ask", "captain_renn", None)],
        conveys=[
            {
                "kind": "proposition",
                "proposition": {
                    "subject_entity_id": "captain_renn",
                    "predicate": "last spoke to",
                    "object_entity_id": "oric_dane",
                },
                "stance": "question",
            }
        ],
        band="brief",
    ),
    "quiet word": intent("say", intents=[("say", "elara", None)], conveys=[], band="brief"),
}

RULING_SHOVE = {
    "requires_check": True,
    "check": {
        "check": "check.core",
        "attribute": "attr.might",
        "skill": "skill.athletics",
        "difficulty": "routine",
    },
    "on_success": [
        {
            "type": "alter_feature",
            "params": {
                "zone": "floor",
                "feature": "a heavy shelf",
                "replacement": "a heavy shelf toppled across the floor",
            },
        }
    ],
    "on_failure": [],
    "time_cost_seconds": 6,
    "precedent_tags": ["barricade", "shelf"],
    "scope": "single_use",
    "summary": "Might + Athletics vs routine to topple the shelf",
}


class Script:
    """Per-actor scripted decisions: content-sensitive where it matters, sequential otherwise."""

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()

    def mira(self, req: ModelRequest):
        self.calls["Mira"] += 1
        if "meet someone" in req.user or self.calls["Mira"] >= 2:
            return npc(
                "He met the captain here that night. They argued, and he looked frightened "
                "after. I did not hear about what.",
                conveys=[
                    {
                        "kind": "fact_ref",
                        "ref_id": fact_ref(req, "met privately"),
                        "stance": "asserts_true",
                        "fidelity": "partial",
                    },
                    {
                        "kind": "fact_ref",
                        "ref_id": fact_ref(req, "argued"),
                        "stance": "asserts_true",
                        "fidelity": "partial",
                    },
                ],
                act="answer",
                summary="a quiet question; the captain is across the room, but she risks it",
            )
        return npc(
            "Not for a while. I pour drinks; I do not keep track of who comes and goes.",
            conveys=[
                {
                    "kind": "proposition",
                    "proposition": {"predicate": "does not keep track of who comes and goes"},
                    "stance": "asserts_true",
                    "about_speaker_self": True,
                }
            ],
            act="evade",
            summary="guards present; evade",
        )

    def renn(self, req: ModelRequest):
        self.calls["Renn"] += 1
        if "last spoke to" in req.user:
            return npc(
                "Weeks ago.",
                conveys=[
                    {
                        "kind": "fact_ref",
                        "ref_id": fact_ref(req, "met privately"),
                        "stance": "asserts_false",
                        "deliberate_false": True,
                    }
                ],
                act="lie",
                knowingly_false=True,
                summary="deny the meeting",
            )
        return npc(None, act="silence")

    def elara(self, req: ModelRequest):
        self.calls["Elara"] += 1
        if "your turn in combat" in req.user:
            return pc(
                None,
                intentions=[{"action_type": "attack", "target_ref": "a_thief_in_dark_clothing"}],
                fallback={"intent": "attack", "flee_below": 0.2},
            )
        if "minutes have passed" in req.user:
            return pc(None)
        if "had something to do with" in req.user or "involved in the disappearance" in req.user:
            if self.calls["Elara_whisper"] == 0:
                self.calls["Elara_whisper"] += 1
                return pc("Understood.", channel="whisper", target="alex")
        if "benefit of the doubt" in req.user and self.calls["Elara_disagree"] == 0:
            self.calls["Elara_disagree"] += 1
            return pc(
                "Authority deserves scrutiny, Tomas. Captains have nerves like anyone.",
                conveys=[
                    {
                        "kind": "belief_ref",
                        "ref_id": belief_ref(req, "authority deserves scrutiny"),
                        "stance": "asserts_true",
                    }
                ],
                emotions=[{"emotion": "frustration", "intensity": 0.3}],
                relationships=[
                    {
                        "target_ref": "tomas",
                        "dimension": "respect",
                        "delta": -2,
                        "reason": "he defends the badge before the facts",
                    }
                ],
            )
        return pc(None)

    def tomas(self, req: ModelRequest):
        self.calls["Tomas"] += 1
        if "minutes have passed" in req.user:
            return pc(
                None,
                intentions=[
                    {"action_type": "move", "target_ref": "records"},
                    {"action_type": "search", "target_ref": "records"},
                ],
                summary="use the time: look at the patrol records",
            )
        if "is trustworthy" in req.user and self.calls["Tomas_opinion"] == 0:
            self.calls["Tomas_opinion"] += 1
            return pc(
                "Captains do not rise by being careless. I would not condemn the man on an "
                "innkeeper's nerves; he deserves the benefit of the doubt.",
                conveys=[
                    {
                        "kind": "proposition",
                        "proposition": {
                            "subject_entity_id": "captain_renn",
                            "predicate": "deserves the benefit of the doubt",
                        },
                        "stance": "asserts_true",
                    }
                ],
            )
        if "guard house records" in req.user and self.calls["Tomas_go"] == 0:
            self.calls["Tomas_go"] += 1
            return pc(
                "I will go and look.",
                intentions=[{"action_type": "travel", "target_ref": "guard_house"}],
            )
        if "ledger" in req.user and self.calls["Tomas_exchange"] == 0:
            self.calls["Tomas_exchange"] += 1
            return pc(
                "Then hear this: the patrol log has a numbering gap on that night, the "
                "restricted-dock round. Someone took a page.",
                conveys=[
                    {
                        "kind": "fact_ref",
                        "ref_id": fact_ref(req, "numbering gap"),
                        "stance": "asserts_true",
                    }
                ],
            )
        return pc(None)

    def thief(self, req: ModelRequest):
        name = "Dock thief 1" if is_actor(req, "Dock thief 1") else "Dock thief 2"
        self.calls[name] += 1
        if self.calls[name] == 1:
            return npc(
                None,
                intentions=[{"action_type": "attack", "target_ref": "a_travel_worn_newcomer"}],
                fallback={"intent": "attack", "flee_below": 0.5},
                summary="grab what we can; hit the nearest",
            )
        return npc(
            "Enough! Enough, we yield!",
            conveys=[],
            intentions=[{"action_type": "surrender", "target_ref": None}],
            act="other",
            summary="not worth dying for",
        )

    def memory(self, req: ModelRequest):
        # only the actor whose window holds the whispered suspicion can remember it
        if "involved in the disappearance" in req.user:
            return {
                "memories": [
                    {
                        "summary": (
                            "Alex privately trusted me with his suspicion about the innkeeper."
                        ),
                        "emotional_interpretation": "trusted",
                        "salience": 0.8,
                        "emotional_weight": 0.4,
                        "is_core": False,
                        "source_observation_ids": [],
                    }
                ],
                "belief_proposals": [],
                "emotion_proposals": [],
            }
        return {"memories": [], "belief_proposals": [], "emotion_proposals": []}


INPUT_RE = re.compile(r'Player input \(channel: \w+\): "(.*?)"\n', re.S)


def input_responder(table: dict[str, dict]):
    """Fake Intent Interpreter keyed on the player's own input line only: the rendered context
    also carries descriptors and recent dialogue, which must not steer the fake."""

    def pick(req: ModelRequest):
        m = INPUT_RE.search(req.user + "\n")
        text = m.group(1) if m else req.user
        for phrase, out in table.items():
            if phrase in text:
                return out
        raise AssertionError(f"no fake intent for input: {text[:200]}")

    return pick


def make_fake(script: Script) -> FakeModelProvider:
    fake = FakeModelProvider()
    fake.register("intent_interpreter", input_responder(INTENTS))

    def actors(req: ModelRequest):
        if is_actor(req, "Mira"):
            return script.mira(req)
        if is_actor(req, "Renn") or is_actor(req, "Captain Renn"):
            return script.renn(req)
        if is_actor(req, "Elara"):
            return script.elara(req)
        if is_actor(req, "Tomas"):
            return script.tomas(req)
        if "Dock thief" in req.user[:400]:
            return script.thief(req)
        raise AssertionError(f"no fixture for actor in request: {req.user[:200]}")

    fake.register("npc_actor", actors)
    fake.register("ai_player", actors)
    fake.register("npc_tactical", actors)
    fake.register("rules_adjudicator", RULING_SHOVE)
    fake.register("narrator", "Rain ticks on the shutters. Nothing here is finished.")
    fake.register("canon_extractor", {"candidates": []})
    fake.register("claim_extractor", {"conveys": []})
    fake.register("belief_processor", {"confidence_adjustment": 0, "inferences": [], "reason": ""})
    fake.register("memory_processor", script.memory)
    fake.register("journal_writer", {"title": "Frostbridge", "body": "The innkeeper knows more."})
    fake.register("world_simulator", {"actions": []})
    return fake


def make_orch(session: AsyncSession, fake: FakeModelProvider) -> SessionOrchestrator:
    return SessionOrchestrator(
        session,
        Settings(a9_token="", spotlight_visible_reactions=1, narrator_enabled=True),
        engine=RulesEngine.load("core_adventure", master_seed=MASTER_SEED),
        provider=fake,
    )


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------


async def beliefs(session: AsyncSession, actor_id: uuid.UUID) -> list[Belief]:
    return list(
        (
            await session.execute(
                select(Belief).where(Belief.actor_id == actor_id, Belief.status != "superseded")
            )
        )
        .scalars()
        .all()
    )


async def has_fact_belief(session: AsyncSession, actor_id: uuid.UUID, fact_id: uuid.UUID) -> bool:
    return any(b.fact_id == fact_id for b in await beliefs(session, actor_id))


async def has_predicate(session: AsyncSession, actor_id: uuid.UUID, fragment: str) -> bool:
    rows = await beliefs(session, actor_id)
    return any(fragment in b.proposition.get("predicate", "") for b in rows)


async def discoveries(session: AsyncSession, actor_id: uuid.UUID) -> set[tuple[str, str, str]]:
    rows = (
        await session.execute(
            select(Clue.key, ClueDiscovery.route, ClueDiscovery.fidelity)
            .join(Clue, Clue.id == ClueDiscovery.clue_id)
            .where(ClueDiscovery.actor_id == actor_id)
        )
    ).all()
    return {(k, r, f) for k, r, f in rows}


async def count(session: AsyncSession, model, w: FrostbridgeWorld) -> int:
    rows = (
        await session.execute(select(model).where(model.campaign_id == w.h.campaign_id))
    ).scalars()
    return len(rows.all())


async def current_scene(session: AsyncSession, actor_id: uuid.UUID) -> Scene:
    s = await PerspectiveService(session).repo.current_scene(actor_id)
    assert s is not None
    return s


async def play(orch: SessionOrchestrator, w: FrostbridgeWorld, text: str, **kw):
    return await orch.process_player_input(w.h, PlayRequest(w.actors["Alex"], text, **kw))


# ---------------------------------------------------------------------------------------------
# the slice
# ---------------------------------------------------------------------------------------------


async def test_frostbridge_vertical_slice(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession], test_settings
) -> None:
    w = await seed_frostbridge(session, name="slice", engine_version="test")
    await session.commit()
    script = Script()
    orch = make_orch(session, make_fake(script))
    psv = PerspectiveService(session)
    A, E, T, M, R = (w.actors[n] for n in ("Alex", "Elara", "Tomas", "Mira", "Renn"))
    social_calls: dict[str, int] = {}
    turn_ids: list[uuid.UUID] = []

    def note(label: str, res) -> None:
        social_calls[label] = res.metrics["sync_model_calls"]
        turn_ids.append(res.turn_id)

    # ---- 1. the gate: a public notice gives the party Oric's name, nothing else -----------------
    res = await play(orch, w, "I read the notice on the gatepost.")
    note("notice", res)
    assert res.actions[0]["action"] == "read" and "Oric Dane" in res.actions[0]["text"]
    assert (await psv.known_entities(A))[w.entities["Oric"]] == "Oric Dane"
    assert await has_fact_belief(session, A, w.facts["oric_missing"])
    assert not await has_fact_belief(session, E, w.facts["oric_missing"])  # only the reader
    doc = DocumentService(session)
    assert await doc.text(w.items["gate_notice"]) == await doc.text(w.items["gate_notice"])

    # ---- 2. enter the Red Lantern: the party joins Mira and Renn's scene -----------------------
    tick0 = (await orch.world.clock(w.h)).current_tick
    res = await play(orch, w, "We head to the Red Lantern, all three of us.")
    note("travel_tavern", res)
    assert res.actions[0]["action"] == "travel" and res.actions[0]["status"] == "succeeded"
    tavern = await current_scene(session, A)
    assert tavern.location_id == w.locations["red_lantern"]
    for who in (E, T, M, R):
        assert (await current_scene(session, who)).id == tavern.id
    assert (await orch.world.clock(w.h)).current_tick == tick0 + 180  # gate→market→tavern
    assert tavern.local_tick == tick0 + 180
    gate = await session.get(Scene, w.scene)
    assert gate.status == "active" and gate.local_tick == tick0  # scripted guards stay, offscreen
    assert await count(session, Claim, w) == 0  # arriving is observed, never asserted

    # ---- 3. Mira: same knowledge, different context ---------------------------------------------
    res = await play(orch, w, "Innkeeper, has Oric Dane been in lately?")
    note("mira_evade", res)
    mira_lines = [s for s in res.speakers if s["actor_id"] == str(M)]
    assert mira_lines and mira_lines[0]["text"].startswith("Not for a while")
    assert not await has_fact_belief(session, A, w.facts["renn_met_oric"])
    res = await play(
        orch, w, "/whisper the innkeeper Just between us: did he meet someone before he vanished?"
    )
    note("mira_reveal", res)
    mira_lines = [s for s in res.speakers if s["actor_id"] == str(M)]
    assert mira_lines and "They argued" in mira_lines[0]["text"]
    # partial fidelity: the clue is discovered by testimony, the fact row is not linked
    for who in (A, E, T):
        assert ("mira_account", "testimony", "partial") in await discoveries(session, who), who
        assert await has_predicate(session, who, "met privately")
        assert not await has_fact_belief(session, who, w.facts["renn_met_oric"])
    # naming moved with the Claim: the party now knows the captain by Mira's name for him
    assert (await psv.known_entities(A))[w.entities["Renn"]] == "Captain Renn"
    assert (await psv.known_entities(T))[w.entities["Renn"]] == "Captain Renn"
    claim = (
        (await session.execute(select(Claim).where(Claim.speaker_actor_id == M))).scalars().all()
    )
    about_facts = [c for c in claim if c.source_fact_id is not None]
    assert about_facts and all(c.fidelity == "partial" for c in about_facts)
    assert not any(c.deliberate_false for c in claim)
    # objective truth untouched
    assert (await session.get(Fact, w.facts["renn_killed_oric"])).truth_status == "true"

    # ---- 4. the private whisper (c&k §8 / belief-update §4 worked values) ------------------------
    res = await play(
        orch, w, "/whisper Elara I think the innkeeper had something to do with his disappearance."
    )
    note("whisper", res)
    alex_line = [s for s in res.speakers if s["actor_id"] == str(A)][0]
    assert alex_line["channel"] == "whisper" and alex_line["recipients"] == [str(E)]
    eb = {(b.proposition["predicate"], b.belief_type): b for b in await beliefs(session, E)}
    assert eb[("asserted", "known")].confidence == 1.0
    involved = eb[("involved in the disappearance of", "suspected")]
    assert float(involved.confidence) == pytest.approx(0.585)  # trust 60, familiarity 50, cap .60
    ab = {b.proposition["predicate"]: b for b in await beliefs(session, A)}
    assert ab["involved in the disappearance of"].belief_type == "stated"
    assert float(ab["involved in the disappearance of"].confidence) == 0.55
    for who in (T, M, R):
        assert not await has_predicate(session, who, "involved in the disappearance"), who
    assert "Mira had" not in str(await psv.context_candidates(T))
    assert "involved" not in str(await psv.context_candidates(T))

    # ---- 5. companion disagreement: Tomas defends the badge, Elara pushes back -----------------
    res = await play(orch, w, "Tomas, what do you make of the captain?")
    note("disagreement", res)
    texts = {s["actor_id"]: s["text"] for s in res.speakers}
    assert "benefit of the doubt" in texts[str(T)]
    assert await has_predicate(session, A, "deserves the benefit of the doubt")
    if str(E) in texts:  # the bounded AI-to-AI wave fired
        deltas = (
            (
                await session.execute(
                    select(RelationshipDelta).where(RelationshipDelta.reason.like("%badge%"))
                )
            )
            .scalars()
            .all()
        )
        assert deltas and all(d.event_id is not None for d in deltas)
    assert res.metrics["sync_model_calls"] <= 4

    # ---- 6. split party: Tomas to the guard house (his own decision), Alex+Elara to the warehouse
    res = await play(orch, w, "Tomas, would you look at the guard house records?")
    note("tomas_leaves", res)
    guard = await current_scene(session, T)
    assert guard.location_id == w.locations["guard_house"] and guard.id != tavern.id
    assert (await current_scene(session, A)).id == tavern.id
    res = await play(orch, w, "Elara and I go to the shuttered warehouse with the merchant sign.")
    note("travel_warehouse", res)
    warehouse = await current_scene(session, A)
    assert warehouse.location_id == w.locations["oric_warehouse"]
    assert (await current_scene(session, E)).id == warehouse.id
    assert (await current_scene(session, M)).id == tavern.id  # Mira and Renn stay; offscreen now
    clock = await orch.world.clock(w.h)
    assert warehouse.local_tick == clock.current_tick  # live scene follows the clock
    assert (await session.get(Scene, tavern.id)).local_tick < clock.current_tick  # offscreen lags

    # ---- 7. warehouse discoveries: ledger (document), mud (physical), dagger (hidden property)
    res = await play(orch, w, "I search the office.")
    note("search_office", res)
    found = [a for a in res.actions if a["action"] == "action.search"]
    assert found and found[0]["status"] == "succeeded"
    ledger = await session.get(Item, w.items["ledger"])
    assert ledger.concealed is False
    assert ("ledger", "document", "partial") in await discoveries(session, A)
    assert ("ledger", "document", "partial") in await discoveries(session, E)  # she saw it found
    assert not await has_fact_belief(session, A, w.facts["ledger_shows_discrepancies"])  # unread
    res = await play(orch, w, "I read the ledger.")
    note("read_ledger", res)
    assert await has_fact_belief(session, A, w.facts["ledger_shows_discrepancies"])
    assert ("ledger", "document", "full") in await discoveries(session, A)
    assert not await has_fact_belief(session, E, w.facts["ledger_shows_discrepancies"])
    ledger_claims = (
        (await session.execute(select(Claim).where(Claim.speaker_actor_id == w.actors["Oric"])))
        .scalars()
        .all()
    )
    assert ledger_claims and all(c.conveyance_source == "document" for c in ledger_claims)
    res = await play(orch, w, "I search the main floor.")
    note("search_floor", res)
    dagger = await session.get(Item, w.items["dagger"])
    assert dagger.concealed is False
    for who in (A, E):
        assert await has_fact_belief(session, who, w.facts["satchel_has_dock_clay"])
        assert ("dock_mud", "physical", "full") in await discoveries(session, who)
    res = await play(orch, w, "I pick up the dagger.")
    note("pick_up", res)
    inv = {i.item_id: i for i in await psv.inventory(A)}
    assert w.items["dagger"] in inv
    assert "spirit" not in str(inv[w.items["dagger"]]) and "lore" not in str(inv[w.items["dagger"]])
    assert "spirit" not in str(await psv.context_candidates(A))
    assert "spirit" not in str(await psv.context_candidates(E))
    dagger_row = await session.get(Item, w.items["dagger"])
    assert dagger_row.hidden_properties["bonus_damage_vs_tags"] == {"spirit": 2}

    # ---- 7b. Tomas's offscreen scene caught up with at most one bounded call -------------------
    assert script.calls["Tomas"] >= 1
    caught = (
        (
            await session.execute(
                select(Event).where(
                    Event.event_type == "scene.caught_up", Event.scene_id == guard.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert caught and max(e.payload["model_calls"] for e in caught) <= 1
    assert await has_fact_belief(session, T, w.facts["guard_log_gap"])
    assert ("log_numbering", "physical", "full") in await discoveries(session, T)
    for who in (A, E):
        assert not await has_fact_belief(session, who, w.facts["guard_log_gap"]), who
    assert not await has_fact_belief(session, T, w.facts["ledger_shows_discrepancies"])
    assert not await has_fact_belief(session, T, w.facts["satchel_has_dock_clay"])
    # the human received nothing from the guard house (human-visibility §3)
    guard_obs = (
        (
            await session.execute(
                select(Observation).where(
                    Observation.scene_id == guard.id, Observation.actor_id == A
                )
            )
        )
        .scalars()
        .all()
    )
    assert guard_obs == []

    # ---- 8. two thieves: initiative, AI turns, improvisation, surrender --------------------------
    scenes = SceneService(session)
    t1, t2 = w.actors["Dock thief 1"], w.actors["Dock thief 2"]
    await scenes.travel(w.h, [t1, t2], w.locations["oric_warehouse"])
    wh = await session.get(Scene, warehouse.id)
    space = dict(wh.state["space"])
    pos = dict(space["positions"])
    my_zone = pos[str(A)]["zone"]
    for t in (t1, t2):
        pos[str(t)] = {
            "zone": my_zone,
            "engaged_with": [str(A)],
            "cover": "none",
            "elevated": False,
        }
    pos[str(A)] = {**pos[str(A)], "engaged_with": [str(t1), str(t2)]}
    wh.state = {**wh.state, "space": {**space, "positions": pos}}
    await session.commit()
    sides = {A: "party", E: "party", t1: "thieves", t2: "thieves"}
    enc = await orch.actions.start_encounter(w.h, warehouse.id, sides)
    await session.commit()
    while enc.current_actor != str(A):
        await orch.actions.next_turn(w.h, warehouse.id)
        enc = (await orch.actions.load_scene(w.h, warehouse.id)).ctx.encounter
    with pytest.raises(NeedsClarification) as exc:
        await play(orch, w, "Attack him!")
    cl = exc.value
    assert len(cl.candidates) == 2
    res = await play(orch, w, "the first one", clarification_id=cl.clarification_id)
    note("attack", res)
    assert res.actions[0]["action"] == "action.attack"
    assert res.visible_rolls and all(r.get("expression") for r in res.visible_rolls)
    rounds = 0
    while True:
        loaded = await orch.actions.load_scene(w.h, warehouse.id)
        if loaded.ctx.encounter is None or loaded.ctx.encounter.status != "active":
            break
        rounds += 1
        assert rounds < 8, "combat did not end"
        res = await play(orch, w, "I shove the heavy shelf over." if rounds == 1 else "I wait.")
        note(f"combat_{rounds}", res)
    wh = await session.get(Scene, warehouse.id)
    features = {z["key"]: z.get("features", []) for z in wh.state["space"]["zones"]}
    assert "a heavy shelf toppled across the floor" in features["floor"]  # persists (§31)
    assert "a heavy shelf" not in features["floor"]
    ended = (
        (
            await session.execute(
                select(Event).where(
                    Event.event_type == "encounter.ended", Event.scene_id == warehouse.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert ended
    surrendered = (
        (
            await session.execute(
                select(Event).where(
                    Event.event_type == "actor.surrendered", Event.scene_id == warehouse.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert surrendered
    rolls = (
        (await session.execute(select(Roll).where(Roll.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    assert rolls and all(r.seed is not None for r in rolls)  # programmatic, reproducible

    # ---- 9. rejoin: reunion merges scenes; knowledge is still asymmetric ------------------------
    claims_before = await count(session, Claim, w)
    obs_before = await count(session, Observation, w)
    res = await play(orch, w, "We go over to the guard house.")
    note("reunion", res)
    merged = await current_scene(session, A)
    assert merged.id == guard.id and (await current_scene(session, T)).id == merged.id
    assert (await current_scene(session, E)).id == merged.id
    assert merged.local_tick == (await orch.world.clock(w.h)).current_tick
    left_behind = await session.get(Scene, warehouse.id)
    await session.refresh(left_behind)
    if left_behind.status == "ended":
        assert warehouse.id in (merged.merged_from or [])  # a whole scene arrived: merged
    else:  # the surrendered thieves keep the warehouse scene alive, offscreen
        assert {t1, t2} <= {p.actor_id for p in await scenes.participants(warehouse.id)}
        assert (await current_scene(session, t1)).id == warehouse.id
    assert await count(session, Claim, w) == claims_before
    arrivals = (
        (
            await session.execute(
                select(Observation).where(
                    Observation.observation_type == "arrived", Observation.scene_id == guard.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert arrivals  # what everyone can plainly see: people arriving
    assert await count(session, Observation, w) > obs_before
    for who in (A, E):
        assert not await has_fact_belief(session, who, w.facts["guard_log_gap"]), who
    assert not await has_fact_belief(session, T, w.facts["ledger_shows_discrepancies"])

    # ---- 10. exchange: propagation only through actual speech ---------------------------------
    res = await play(orch, w, "Tomas, we found Oric's ledger. The dock numbers don't match.")
    note("exchange", res)
    assert await has_predicate(session, T, "kept a ledger of dock shortfalls")
    tomas_lines = [s for s in res.speakers if s["actor_id"] == str(T)]
    assert tomas_lines and "numbering gap" in tomas_lines[0]["text"]
    for who in (A, E):
        assert await has_fact_belief(session, who, w.facts["guard_log_gap"]), who
        assert ("log_numbering", "testimony", "full") in await discoveries(session, who)
    gap = [b for b in await beliefs(session, A) if b.fact_id == w.facts["guard_log_gap"]][0]
    assert gap.source_type == "told" and gap.source_actor_id == T and gap.claim_id is not None

    # ---- 11. Renn lies: Claim with private flags, no Fact -------------------------------------
    res = await play(orch, w, "We go back to the tavern.")
    note("travel_back", res)
    assert (await current_scene(session, R)).id == (await current_scene(session, A)).id
    res = await play(orch, w, "Captain, when did you last speak to Oric Dane?")
    note("renn_lie", res)
    renn_lines = [s for s in res.speakers if s["actor_id"] == str(R)]
    assert renn_lines and renn_lines[0]["text"] == "Weeks ago."
    lie = (
        (
            await session.execute(
                select(Claim).where(
                    Claim.speaker_actor_id == R, Claim.speaker_stance == "asserts_false"
                )
            )
        )
        .scalars()
        .all()
    )
    assert lie and lie[0].deliberate_false is True
    assert await has_predicate(session, T, "not met privately")
    heard = await psv.heard_claims(T)
    assert heard and not any(hasattr(c, "deliberate_false") for c in heard)
    truth = await session.get(Fact, w.facts["renn_met_oric"])
    assert truth.truth_status == "true" and truth.canon_status == "established"
    assert all(b.belief_type == "known" for b in await beliefs(session, R) if b.fact_id == truth.id)

    # ---- 15. scene end is the memory checkpoint; the party leaves town ---------------------------
    tavern_now = await current_scene(session, A)
    checkpoint = await orch.end_scene(w.h, tavern_now.id)
    assert checkpoint["checkpoints"] and checkpoint["journals"]
    elara_mems = (await session.execute(select(Memory).where(Memory.actor_id == E))).scalars().all()
    assert any("trusted me" in m.subjective_summary for m in elara_mems)
    tomas_mems = (await session.execute(select(Memory).where(Memory.actor_id == T))).scalars().all()
    assert not any("trusted me" in m.subjective_summary for m in tomas_mems)
    await scenes.travel(w.h, [A, E, T], w.locations["town_gate"])  # heading out of town

    # ---- 12. four days pass: clocks process, prerequisites hold, the mystery stays solvable ------
    await orch.world.advance_time(w.h, 4 * DAY, reason="the party leaves Frostbridge for four days")
    await session.commit()
    sched = ScheduleService(session)
    status = {
        p.payload["key"]: p.status
        for p in [
            *(await sched.pending(w.h)),
        ]
    }
    # still pending: the simulator's work (Day +5 travel and departure) and the Day +8 clock
    assert set(status) == {"day5_renn_to_dock", "day5_shipment", "day8_quarry"}
    caravan = await session.get(Fact, w.facts["caravan_arrival"])
    assert caravan.canon_status == "established"
    draft = await session.get(Clue, w.clues["log_draft"])
    assert draft.state == "destroyed"
    assert (await session.get(Item, w.items["log_draft"])).destroyed_event_id is not None
    plan = await session.get(Plan, w.plan)
    # the Day +3 scheduled event completes step 1 (documentation), which counts the earlier
    # cargo step as done; later steps belong to the simulation run (08), not a bare advance
    assert plan.current_step == 2 and plan.status == "active"
    rr = await MysteryService(session).routes_remaining(w.mystery)
    assert rr.solvable and rr.intact_by_fact[w.facts["guard_log_gap"]] == 1
    fired = (
        (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == w.h.campaign_id,
                    Event.event_type == "scheduled_event.fired",
                )
            )
        )
        .scalars()
        .all()
    )
    assert {e.payload["outcome"] for e in fired} == {"processed"}
    quarry = await session.get(Fact, w.facts["quarry_disturbance"])
    assert quarry.canon_status == "latent"

    # ---- 13–14. restart: a fresh engine, session and orchestrator see the same world ------------
    tick_before = (await orch.world.clock(w.h)).current_tick
    await session.close()
    engine2 = make_engine(test_settings.database_url)
    try:
        async with async_sessionmaker(engine2, expire_on_commit=False)() as s2:
            psv2 = PerspectiveService(s2)
            inv2 = {i.item_id: i for i in await psv2.inventory(A)}
            assert w.items["dagger"] in inv2 and "spirit" not in str(inv2[w.items["dagger"]])
            assert (await s2.get(Item, w.items["dagger"])).hidden_properties[
                "bonus_damage_vs_tags"
            ] == {"spirit": 2}
            assert (await s2.get(WorldClock, w.h.timeline_id)).current_tick == tick_before
            assert await has_fact_belief(s2, T, w.facts["guard_log_gap"])
            assert await has_fact_belief(s2, A, w.facts["ledger_shows_discrepancies"])
            assert not await has_predicate(s2, T, "involved in the disappearance")
            assert (await s2.get(Clue, w.clues["log_draft"])).state == "destroyed"
            assert (await s2.get(Plan, w.plan)).current_step == 2
            goals = await psv2.repo.goals(E)
            assert any("Joren" in g.description for g in goals)
            mems = (await s2.execute(select(Memory).where(Memory.actor_id == E))).scalars().all()
            assert any("trusted me" in m.subjective_summary for m in mems)
            tm = (await s2.execute(select(Memory).where(Memory.actor_id == T))).scalars().all()
            assert not any("trusted me" in m.subjective_summary for m in tm)
            rels = await psv2.repo.relationships_from(E)
            assert any(r.target_entity_id == w.entities["Alex"] and r.trust == 60 for r in rels)
            metrics = (
                (
                    await s2.execute(
                        select(TurnMetrics).where(TurnMetrics.campaign_id == w.h.campaign_id)
                    )
                )
                .scalars()
                .all()
            )
            assert {m.turn_id for m in metrics} >= set(turn_ids)  # every turn measured
            runs = (
                (await s2.execute(select(ModelRun).where(ModelRun.campaign_id == w.h.campaign_id)))
                .scalars()
                .all()
            )
            snaps = (
                (
                    await s2.execute(
                        select(ContextSnapshot).where(
                            ContextSnapshot.campaign_id == w.h.campaign_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert runs and snaps  # debug traceability survives
            # the murder truth never reached a non-Renn context
            for snap in snaps:
                if snap.actor_id != R and snap.actor_id is not None:
                    assert "killed" not in (snap.rendered_context or ""), snap.role
            # 18: continue naturally after reload
            orch2 = make_orch(s2, make_fake(Script()))
            res = await orch2.process_player_input(
                w.h, PlayRequest(A, "/say Elara, a quiet word before we sleep.")
            )
            assert res.turn_id and res.metrics["sync_model_calls"] >= 1
    finally:
        await engine2.dispose()

    # ---- budgets (§41b): tavern turns at ≤ 3 synchronous calls, one more for an AI-to-AI exchange
    for label in ("mira_evade", "mira_reveal", "whisper"):
        assert social_calls[label] <= 3, (label, social_calls)
    assert social_calls["disagreement"] <= 4


# ---------------------------------------------------------------------------------------------
# focused scenario tests around the slice
# ---------------------------------------------------------------------------------------------


async def test_scheduled_evidence_destruction_is_cancelled_when_renn_is_detained(
    session: AsyncSession,
) -> None:
    from app.persistence.models import ConditionInstanceRow

    w = await seed_frostbridge(session, name="slice-detained", engine_version="test")
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
    await w.world.advance_time(w.h, 4 * DAY, reason="four days")
    await session.commit()
    draft = await session.get(Clue, w.clues["log_draft"])
    assert draft.state == "intact"
    assert (await session.get(Plan, w.plan)).current_step == 0  # no simulation run happened
    fired = {
        e.payload["scheduled_type"]: e.payload["outcome"]
        for e in (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == w.h.campaign_id,
                    Event.event_type == "scheduled_event.fired",
                )
            )
        ).scalars()
    }
    assert fired["clue.destroy"] == "cancelled" and fired["plan.advance"] == "cancelled"
    assert fired["fact.establish"] == "processed"  # the caravan does not depend on Renn


async def test_ai_actor_cannot_convey_a_clue_nobody_found(session: AsyncSession) -> None:
    """knowledge-leakage §19: Elara 'mentions' the guard-log gap before anyone found it."""
    from app.services.speech import ConveysItem, LeakageError, SpeechService

    w = await seed_frostbridge(session, name="slice-leak", engine_version="test")
    await session.commit()
    scene = await session.get(Scene, w.scene)
    with pytest.raises(LeakageError):
        await SpeechService(session).utter(
            w.h,
            scene.id,
            w.actors["Elara"],
            "The patrol log has a gap on that night.",
            channel="say",
            conveys=[
                ConveysItem("fact_ref", ref_id=str(w.facts["guard_log_gap"]), stance="asserts_true")
            ],
            conveyance_source="structured",
        )
    session.expire_all()
    assert (
        not (
            await session.execute(select(Claim).where(Claim.speaker_actor_id == w.actors["Elara"]))
        )
        .scalars()
        .all()
    )
    rejected = (
        (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == w.h.campaign_id,
                    Event.event_type == "proposal.rejected_leakage",
                )
            )
        )
        .scalars()
        .all()
    )
    assert rejected and rejected[-1].payload["ref_id"] == str(w.facts["guard_log_gap"])
