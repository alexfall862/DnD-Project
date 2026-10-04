"""Milestone 06c: narration that follows resolution, a bounded spotlight, canon extraction
through the allowlist, memory checkpoints, journal and encyclopedia, the full degradation
ladder.

Tests (task card): narrator input is the focus actor's perception only and narration never
touches state; spotlight limits in a crowded scene; disallowed extractor candidates rejected
and an allowed one stored latent then established by a player action; Elara remembers the
whisper and Tomas has nothing; the journal keeps Alex's misconception; ladder steps logged
under an artificial time budget."""

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
    Campaign,
    ContextSnapshot,
    Entity,
    Event,
    Location,
    Memory,
    MemorySource,
    ModelRun,
    Observation,
    Scene,
    SceneParticipant,
)
from app.services.orchestrator import PlayRequest, SessionOrchestrator
from tests.fixtures.frostbridge import World
from tests.integration.test_ai_actors import by_actor, npc, pc
from tests.integration.test_orchestrator import intent, responder

pytestmark = pytest.mark.integration

NARRATION = (
    "The taproom hushes as Mira leans over the bar. Rain drums on the shutters and a row of "
    "barrels sweats in the lantern light. She answers you quietly, and the thief at the far "
    "table drops dead on the spot."  # a tempting contradiction: nobody dies in this turn
)


def make(session: AsyncSession, fake: FakeModelProvider, **settings) -> SessionOrchestrator:
    return SessionOrchestrator(
        session,
        Settings(a9_token="", **{"narrator_enabled": True, **settings}),
        engine=RulesEngine.load("core_adventure", master_seed=11),
        provider=fake,
    )


def ask_mira_fixture(fake: FakeModelProvider) -> dict:
    """Registers the fixtures for 'I ask Mira ...' and returns the mutable intent table (the
    responder matches phrases against the whole request, so keys must be distinctive)."""
    table = {
        "been in lately": intent(
            "say",
            intents=[("ask", "mira", None)],
            conveys=[
                {
                    "kind": "proposition",
                    "proposition": {"subject_entity_id": "oric", "predicate": "was here lately"},
                    "stance": "question",
                }
            ],
            band="brief",
        )
    }
    fake.register("intent_interpreter", responder(table))
    fake.register(
        "npc_actor",
        by_actor(
            {
                "Mira": npc("Not for a week. He kept to himself.", conveys=[], act="evade"),
                "Renn": npc(None, act="silence"),
            }
        ),
    )
    fake.register("narrator", NARRATION)
    return table


async def narrator_context(session: AsyncSession, campaign_id: uuid.UUID) -> str:
    run = (
        (
            await session.execute(
                select(ModelRun)
                .where(ModelRun.campaign_id == campaign_id, ModelRun.role == "narrator")
                .order_by(ModelRun.started_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert run is not None
    snap = await session.get(ContextSnapshot, run.context_snapshot_id)
    return snap.rendered_context


# --- narrator ----------------------------------------------------------------------------------


async def test_narrator_sees_only_the_focus_actors_perception_and_cannot_change_state(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Oric"], "Oric")
    fake = FakeModelProvider()
    ask_mira_fixture(fake)
    orch = make(session, fake)
    emitted: list[tuple[str, dict]] = []
    events_before = len(
        (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    res = await orch.process_player_input(
        w.h,
        PlayRequest(w.actors["Alex"], 'I ask Mira "has Oric been in lately?"'),
        emit=lambda n, p: emitted.append((n, p)),
    )
    assert res.narration == NARRATION
    names = [n for n, _ in emitted]
    assert names[0] == "accepted" and names[-1] == "complete"
    assert names.index("mechanics") < names.index("narration_delta")
    assert names.index("speaker") < names.index("narration_delta")
    assert res.metrics["ms_to_first_narration_token"] is not None
    assert res.metrics["calls_by_role"]["narrator"] == 1
    ctx = await narrator_context(session, w.h.campaign_id)
    # the bundle: Mira's line verbatim, Alex's own question, the scene as Alex knows it
    assert "Not for a week. He kept to himself." in ctx and "Mira" in ctx
    assert "has Oric been in lately" in ctx
    # and nothing Alex cannot perceive: the murder, Renn's private knowledge, Tomas's beliefs
    assert "killed" not in ctx and "met privately" not in ctx
    assert "ordinary people" not in ctx and "authority deserves" not in ctx
    assert str(w.facts["renn_killed_oric"]) not in ctx
    # narration is presentation: no Observation carries it, nobody died, no state changed
    obs = (
        (await session.execute(select(Observation).where(Observation.actor_id == w.actors["Alex"])))
        .scalars()
        .all()
    )
    assert all("drops dead" not in str(o.raw) for o in obs)
    types = {
        e.event_type
        for e in (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    }
    assert not types & {"damage.dealt", "actor.incapacitated"}
    assert res.state_changes == []
    after = len(
        (await session.execute(select(Event).where(Event.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    assert after > events_before  # speech and observations, not narration


# --- spotlight governor -------------------------------------------------------------------------


async def test_spotlight_limits_visible_ai_turns_in_a_crowded_scene(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    campaign = await session.get(Campaign, w.h.campaign_id)
    campaign.settings = {**campaign.settings, "spotlight": {"max_visible_ai_turns": 3}}
    scene = await session.get(Scene, w.scene)
    for i in range(5):
        a = await w.world.create_actor(
            w.h,
            f"Patron {i}",
            actor_type="npc",
            controller_type="ai",
            location_id=w.tavern,
            importance_tier="important",
            mechanical_profile={"attributes": {"attr.presence": 5}},
            metadata={"descriptor": "a patron"},
        )
        session.add(SceneParticipant(scene_id=scene.id, actor_id=a.id))
    await session.flush()
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder(
            {
                "anyone": intent(
                    "say",
                    intents=[("ask", None, None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {"predicate": "saw Oric"},
                            "stance": "question",
                        }
                    ],
                    band="brief",
                )
            }
        ),
    )
    fake.register("npc_actor", npc("Not me.", conveys=[]))
    fake.register("ai_player", pc("Not me.", conveys=[]))
    fake.register("narrator", "Heads turn; a few voices answer, the rest go back to their cups.")
    orch = make(
        session,
        fake,
        spotlight_visible_reactions=5,
        max_sync_model_calls_per_turn=10,
        hard_cap_sync_model_calls_per_turn=12,
    )
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I ask the room, "did anyone see Oric?"')
    )
    ai_lines = [s for s in res.speakers if s["actor_id"] != str(w.actors["Alex"])]
    assert len(ai_lines) == 3, res.metrics  # the governor's cap, not the reaction budget
    assert res.metrics["reactions"]["visible"] == 5 and res.metrics["reactions"]["spoke"] == 3
    scene = await session.get(Scene, w.scene)
    ledger = scene.state["spotlight"]
    assert ledger["visible_ai_turns"] == 3 and len(ledger["compressed"]) == 2
    ctx = await narrator_context(session, w.h.campaign_id)
    assert "2 other(s) present react quietly" in ctx  # compressed into narration, not invented
    assert sum(1 for n in res.metrics["notes"] if n.startswith("spotlight:")) == 2


# --- canon extraction ---------------------------------------------------------------------------


async def test_canon_extractor_allowlist_latent_then_established(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Oric"], "Oric")
    fake = FakeModelProvider()
    table = ask_mira_fixture(fake)
    table["search the barrels"] = intent("do", intents=[("search", "bar", None)])
    fake.register(
        "canon_extractor",
        {
            "candidates": [
                {"classification": "furnishing", "description": "a row of barrels along the wall"},
                {"classification": "condition", "description": "rain drumming on the shutters"},
                {"classification": "furnishing", "description": "a brass key on the table"},
                {"classification": "furnishing", "description": "a secret passage behind the bar"},
                {
                    "classification": "appearance",
                    "description": "mud-caked boots",
                    "target_ref": str(w.entities["Oric"]),  # not present
                },
                {
                    "classification": "appearance",
                    "description": "a grey scarf",
                    "target_ref": str(w.entities["Mira"]),
                },
                {
                    "classification": "furnishing",
                    "description": "a cursed idol",
                    "effects": {"x": 1},
                },
            ]
        },
    )
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I ask Mira "has Oric been in lately?"')
    )
    assert res.metrics["canon"] == {"accepted": 3, "rejected": 4, "status": "ok"}
    assert res.metrics["background_model_calls"] == 1
    loc = await session.get(Location, w.tavern)
    feats = loc.properties["features"]
    assert {f["description"] for f in feats} == {
        "a row of barrels along the wall",
        "rain drumming on the shutters",
    } and all(f["canon_status"] == "latent" for f in feats)
    mira = await session.get(Entity, w.entities["Mira"])
    assert mira.metadata_["latent_descriptors"] == ["a grey scarf"]
    added = (
        (
            await session.execute(
                select(Event).where(
                    Event.event_type == "canon.detail_added", Event.campaign_id == w.h.campaign_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(added) == 3
    rejected = [n for n in res.metrics["notes"] if n.startswith("canon candidate rejected")]
    assert (
        len(rejected) == 4
        and any("items" in n for n in rejected)
        and any("topology" in n for n in rejected)
    )
    assert any("present" in n for n in rejected) and any("mechanical" in n for n in rejected)
    # a later player action that names the barrels establishes them
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I search the barrels.")
    )
    assert res.metrics["canon_established"] == ["a row of barrels along the wall"]
    loc = await session.get(Location, w.tavern)
    status = {f["description"]: f["canon_status"] for f in loc.properties["features"]}
    assert status["a row of barrels along the wall"] == "established"
    assert status["rain drumming on the shutters"] == "latent"


# --- memory checkpoint, journal, encyclopedia ---------------------------------------------------


def memory_fixture(req: ModelRequest) -> dict:
    """Cite the heard-whisper observation if this actor has one; otherwise remember nothing."""
    refs = re.findall(r"(o_[0-9a-f]{8}) \[t\d+\] [^\n]*suggests[^\n]*", req.user)
    if not refs:
        return {"memories": [], "belief_proposals": [], "emotion_proposals": []}
    return {
        "memories": [
            {
                "summary": "Alex privately trusted me with his suspicion about Mira.",
                "emotional_interpretation": "touched, and a little wary of Mira",
                "salience": 0.8,
                "emotional_weight": 0.5,
                "is_core": False,
                "source_observation_ids": refs,
            }
        ],
        "belief_proposals": [],
        "emotion_proposals": [],
    }


async def test_memory_checkpoint_journal_and_encyclopedia(
    session: AsyncSession, frostbridge: World, app, client
) -> None:
    w = frostbridge
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Oric"], "Oric")
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
        by_actor({"Elara": pc("Keep your voice down.", channel="whisper", target="alex")}),
    )
    fake.register("narrator", "You lean close and share your suspicion; Elara's eyes narrow.")
    fake.register("memory_processor", memory_fixture)
    fake.register(
        "journal_writer",
        {
            "title": "The Red Lantern",
            "body": "I told Elara what I suspect: Mira had something to do with Oric vanishing. "
            "She told me to keep my voice down.",
        },
    )
    orch = make(session, fake)
    await orch.process_player_input(
        w.h,
        PlayRequest(
            w.actors["Alex"],
            'I whisper to Elara "I think Mira had something to do with Oric\'s disappearance."',
        ),
    )
    summary = await orch.end_scene(w.h, w.scene)
    assert (
        summary["calls_by_role"].get("memory_processor") == 1
    )  # Elara only; Tomas had nothing new
    assert summary["calls_by_role"].get("journal_writer") == 1
    elara_mem = (
        (await session.execute(select(Memory).where(Memory.actor_id == w.actors["Elara"])))
        .scalars()
        .all()
    )
    assert len(elara_mem) == 1 and "suspicion about Mira" in elara_mem[0].subjective_summary
    src = (
        (
            await session.execute(
                select(MemorySource).where(MemorySource.memory_id == elara_mem[0].id)
            )
        )
        .scalars()
        .all()
    )
    obs = await session.get(Observation, src[0].observation_id)
    assert obs.actor_id == w.actors["Elara"] and obs.observation_type == "heard_claim"
    assert (
        not (await session.execute(select(Memory).where(Memory.actor_id == w.actors["Tomas"])))
        .scalars()
        .all()
    )
    assert (await session.get(Scene, w.scene)).status == "ended"
    await session.commit()
    # journal: Alex's perspective, misconception preserved (the engine knows Renn did it)
    r = await client.get(f"/api/v1/characters/{w.actors['Alex']}/journal")
    assert r.status_code == 200 and len(r.json()) == 1
    assert "Mira had something to do with" in r.json()[0]["body"]
    assert "Renn" not in r.json()[0]["body"]
    # encyclopedia: Mira's entry carries the suspicion as a suspicion, not a fact
    r = await client.get(f"/api/v1/characters/{w.actors['Alex']}/encyclopedia?category=person")
    assert r.status_code == 200
    entries = {e["display_name"]: e for e in r.json()}
    assert "Mira" in entries and "Elara" in entries
    assert any(
        "involved in the disappearance of" in line
        for line in entries["Mira"]["knowledge"].get("stated", [])
    )
    assert "known" not in entries["Mira"]["knowledge"] or not any(
        "involved" in x for x in entries["Mira"]["knowledge"]["known"]
    )
    r = await client.get(f"/api/v1/characters/{w.actors['Alex']}/encyclopedia/{w.entities['Renn']}")
    assert r.status_code == 404  # Alex does not know Renn by name; knowing the id grants nothing
    # an AI actor's journal is never served to the client
    r = await client.get(f"/api/v1/characters/{w.actors['Elara']}/journal")
    assert r.status_code == 403


# --- degradation ladder -----------------------------------------------------------------------


async def test_degradation_ladder_steps_under_an_artificial_time_budget(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Oric"], "Oric")
    campaign = await session.get(Campaign, w.h.campaign_id)
    campaign.settings = {
        **campaign.settings,
        "latency_budget": {
            "first_narration_simple_ms": 1,
            "first_narration_complex_ms": 1,
            "first_narration_hard_ms": 1,
        },
    }
    fake = FakeModelProvider()
    ask_mira_fixture(fake)
    fake.register(
        "canon_extractor",
        {"candidates": [{"classification": "furnishing", "description": "a bench"}]},
    )
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], 'I ask Mira "has Oric been in lately?"')
    )
    steps = res.metrics["degradation_steps"]
    assert steps[:3] == [
        "drop_canon_extractor",
        "defer_memory_processing",
        "reduce_visible_reactions_to_1",
    ]
    assert "short_narrator_prompt" in steps and "skip_narrator" not in steps
    assert res.narration == NARRATION and res.metrics["budget_breached"] is True
    assert "canon_extractor" not in res.metrics["calls_by_role"]  # step 1
    assert res.metrics["reactions"]["visible"] <= 1  # step 3
    ctx = await narrator_context(session, w.h.campaign_id)
    assert "resolve in two sentences" in ctx  # step 5
    assert "canon" not in res.metrics
