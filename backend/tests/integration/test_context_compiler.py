"""Milestone 05 acceptance: an audited context for Elara contains exactly what Elara should
know, and nothing from the global world. Plus authorization failure, section filtering, and
budget fitting."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextAuthorizationError, ContextCompiler, ContextItemDraft
from app.ai.embeddings import HashingEmbedder
from app.engine.core import RulesEngine
from app.persistence.models import ContextItem, ContextSnapshot
from app.services.memory import MemoryService
from app.services.speech import ConveysItem, SpeechService
from tests.fixtures.frostbridge import World

pytestmark = [pytest.mark.integration, pytest.mark.leakage]


@pytest.fixture
def rules() -> RulesEngine:
    return RulesEngine.load("core_adventure", master_seed=5)


async def whisper(session, w: World):
    return await SpeechService(session).utter(
        w.h,
        w.scene,
        w.actors["Alex"],
        "I think Mira had something to do with Oric's disappearance.",
        channel="whisper",
        target_actor_ids=[w.actors["Elara"]],
        conveyance_source="fixture",
        conveys=[
            ConveysItem(
                "proposition",
                proposition={
                    "subject_entity_id": str(w.entities["Mira"]),
                    "predicate": "involved in the disappearance of",
                    "object_entity_id": str(w.entities["Oric"]),
                },
                stance="uncertain",
            )
        ],
    )


async def test_elara_context_is_exactly_her_perspective(
    session: AsyncSession, frostbridge: World, rules: RulesEngine
) -> None:
    w = frostbridge
    mem = MemoryService(session, HashingEmbedder())
    r = await whisper(session, w)
    elara = w.actors["Elara"]
    await mem.create_memory(
        w.h,
        elara,
        "Joren left home after we argued; I still search for my brother.",
        seed=True,
        is_core=True,
        salience=0.95,
    )
    await mem.create_memory(
        w.h,
        elara,
        "Alex privately trusted me with his suspicion about Mira.",
        source_observation_ids=[o.id for o in r.observations if o.actor_id == elara],
        salience=0.8,
        entity_ids=[w.entities["Alex"], w.entities["Mira"]],
    )
    compiler = ContextCompiler(session, memory=mem, engine=rules)
    ctx = await compiler.compile(
        w.h,
        "ai_player",
        actor_id=elara,
        purpose="respond to whisper",
        situation="Alex just whispered to you. Decide how to respond.",
        query="What did Alex tell me about Mira?",
        focus_entity_ids=[w.entities["Mira"]],
    )

    text = ctx.rendered
    # what she should know
    assert "authority deserves scrutiny" in text  # her belief
    assert (
        "involved in the disappearance of" in text and "suspected 0.5" in text
    )  # from the whisper
    assert "Alex: trust 60" in text  # her own relationship row
    assert "Lady Veyra" in text  # she knows that name
    assert "Joren" in text and "Core memories" in text
    assert "Alex privately trusted me" in text  # retrieved memory
    assert "## scene" in text and "Mira" in text and "Red Lantern Tavern" in text
    assert "Attributes" in text and "agility 7" in text  # her own sheet, player-agent layer
    # what she must not know
    assert "killed" not in text and "renn_killed" not in text  # mystery truth
    assert "Masked Woman" not in text  # Alex's name for Veyra
    assert (
        "spirit" not in text and "relay salvage" not in text
    )  # hidden item lore (not hers anyway)
    assert "Captain Renn" not in text and "Renn" not in text.replace(
        "Red Lantern", ""
    )  # she has no name for Renn
    assert "a man you have not met" in text  # Renn as she perceives him
    assert "most guards are ordinary people" not in text  # Tomas's belief
    # audit rows
    snap = await session.get(ContextSnapshot, ctx.snapshot_id)
    assert (
        snap is not None
        and snap.role == "ai_player"
        and snap.actor_id == elara
        and snap.rendered_context == text
    )
    items = (
        (
            await session.execute(
                select(ContextItem).where(ContextItem.snapshot_id == ctx.snapshot_id)
            )
        )
        .scalars()
        .all()
    )
    assert items and all(i.authorization in ("allowed", "public") for i in items)
    assert all(i.owner_actor_id in (elara, None) for i in items)
    assert {i.section for i in items} >= {
        "identity",
        "beliefs",
        "scene",
        "memories",
        "core_memories",
        "relationships_own",
        "situation",
        "heard_claims",
    }
    # stable prefix first: identity/behaviour/sheet before scene and observations
    assert (
        text.index("## identity")
        < text.index("## beliefs")
        < text.index("## scene")
        < text.index("## situation")
    )
    assert ctx.stable_prefix_chars > 0 and text[: ctx.stable_prefix_chars].startswith("## identity")
    # ref map lets conveys reference only her own beliefs
    assert ctx.belief_refs and all(k.startswith("b_") for k in ctx.belief_refs)
    from app.persistence.models import Belief

    for key in list(ctx.belief_refs)[:3]:
        assert (await session.get(Belief, ctx.ref_map[key])).actor_id == elara


async def test_alex_context_uses_his_names_and_tomas_context_lacks_the_whisper(
    session: AsyncSession, frostbridge: World, rules: RulesEngine
) -> None:
    w = frostbridge
    await whisper(session, w)
    compiler = ContextCompiler(session, engine=rules)
    alex = await compiler.compile(
        w.h,
        "intent_interpreter",
        actor_id=w.actors["Alex"],
        purpose="parse",
        situation='"I ask Mira about Oric."',
    )
    assert "Masked Woman" in alex.rendered and "Lady Veyra" not in alex.rendered
    assert (
        "chipped near the tip" in alex.rendered and "spirit" not in alex.rendered
    )  # his dagger, public side only
    tomas = await compiler.compile(
        w.h,
        "ai_player",
        actor_id=w.actors["Tomas"],
        purpose="react",
        situation="Decide what to do.",
    )
    assert (
        "involved in the disappearance" not in tomas.rendered
        and "Mira had something" not in tomas.rendered
    )
    assert (
        "most guards are ordinary people" in tomas.rendered
        and "authority deserves scrutiny" not in tomas.rendered
    )


async def test_unauthorized_item_aborts_and_is_recorded(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    compiler = ContextCompiler(session)
    forged = ContextItemDraft(
        "beliefs",
        "belief",
        "forged",
        w.actors["Tomas"],
        "b_dead: Renn killed Oric — known 1.00",
        reason="smuggled in",
    )
    with pytest.raises(ContextAuthorizationError) as exc:
        await compiler.compile(
            w.h,
            "ai_player",
            actor_id=w.actors["Elara"],
            purpose="x",
            situation="x",
            extra_items=[forged],
        )
    items = (
        (
            await session.execute(
                select(ContextItem).where(ContextItem.snapshot_id == exc.value.snapshot_id)
            )
        )
        .scalars()
        .all()
    )
    assert any(i.authorization == "denied" and i.source_id == "forged" for i in items)
    # non-strict mode still records the denial but does not raise (never used in CI/dev)
    lenient = ContextCompiler(session, strict=False)
    ctx = await lenient.compile(
        w.h,
        "ai_player",
        actor_id=w.actors["Elara"],
        purpose="x",
        situation="x",
        extra_items=[forged],
    )
    assert "Renn killed Oric" in ctx.rendered  # which is exactly why strict is the default


async def test_role_section_filter_and_budget_fit(
    session: AsyncSession, frostbridge: World, rules: RulesEngine
) -> None:
    w = frostbridge
    compiler = ContextCompiler(session, engine=rules)
    # narrator: beliefs and memories are forbidden sections; they are dropped, not rendered
    n = await compiler.compile(
        w.h,
        "narrator",
        actor_id=w.actors["Elara"],
        purpose="narrate",
        situation="narrate the entrance",
        extra_sections={"style": "second person, 80-120 words"},
    )
    assert (
        "## beliefs" not in n.rendered
        and "## style" in n.rendered
        and "## observations" in n.rendered
        or "## scene" in n.rendered
    )
    items = (
        (await session.execute(select(ContextItem).where(ContextItem.snapshot_id == n.snapshot_id)))
        .scalars()
        .all()
    )
    assert any(i.section == "beliefs" and i.authorization == "dropped" for i in items)
    # budget: flood observations beyond the fast profile budget; lowest-scored (oldest) are trimmed
    from app.persistence.models import Observation

    for i in range(900):
        session.add(
            Observation(
                campaign_id=w.h.campaign_id,
                actor_id=w.actors["Alex"],
                source_event_id=(await _any_event_id(session, w)),
                channel="vision",
                observation_type="event",
                raw={
                    "event_type": "actor.repositioned",
                    "participants": [{"known_as": "Tomas", "role": "subject"}],
                    "outcome_visible": {"from_zone": "door", "to_zone": "floor"},
                },
                confidence=1.0,
                game_tick=i,
                scene_id=w.scene,
            )
        )
    await session.flush()
    big = await compiler.compile(
        w.h, "intent_interpreter", actor_id=w.actors["Alex"], purpose="parse", situation="x" * 2000
    )
    assert big.estimated_tokens <= 4000 - 300 + 50
    kept = (
        (
            await session.execute(
                select(ContextItem).where(
                    ContextItem.snapshot_id == big.snapshot_id,
                    ContextItem.section == "observations",
                )
            )
        )
        .scalars()
        .all()
    )
    assert kept and len(kept) <= 12  # recent_observations caps at 12 before fitting


async def _any_event_id(session: AsyncSession, w: World) -> uuid.UUID:
    from app.persistence.models import Event

    return (
        await session.execute(select(Event.id).where(Event.campaign_id == w.h.campaign_id).limit(1))
    ).scalar_one()
