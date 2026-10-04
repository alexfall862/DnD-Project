"""Milestone 08-0: an NPC's structured output may whisper. Only the target (and anyone able to
overhear) receives the Claim; the private channel is visible to developers through the model
run's structured output, never through another actor's perspective."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider
from app.persistence.models import ModelRun, Observation
from app.services.orchestrator import PlayRequest
from app.services.perspective import PerspectiveService
from tests.fixtures.frostbridge import World
from tests.integration.test_ai_actors import by_actor, make, npc, pc
from tests.integration.test_orchestrator import intent, responder

pytestmark = [pytest.mark.integration, pytest.mark.leakage]


async def test_npc_whispers_reach_only_the_target(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider().register(
        "intent_interpreter",
        responder(
            {
                "quietly": intent(
                    "whisper",
                    intents=[("whisper", "mira", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {"subject_entity_id": "mira", "predicate": "is afraid"},
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
                "Mira": {
                    **npc(
                        "Not here. Not with him at the door.",
                        conveys=[
                            {
                                "kind": "proposition",
                                "proposition": {"predicate": "cannot speak freely here"},
                                "stance": "asserts_true",
                                "about_speaker_self": True,
                            }
                        ],
                        act="evade",
                    ),
                    "speech_channel": "whisper",
                    "speech_target_ref": "alex",
                },
                "Renn": npc(None, act="silence"),
            }
        ),
    )
    fake.register("ai_player", by_actor({"Elara": pc(None), "Tomas": pc(None)}))
    # Mira has been told the newcomer's name, so "alex" is a candidate ref for her
    await w.knowledge.learn_identity(w.h, w.actors["Mira"], w.entities["Alex"], "Alex")
    orch = make(session, fake, spotlight_visible_reactions=1)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "/whisper Mira quietly: are you afraid of him?")
    )
    mira = [s for s in res.speakers if s["actor_id"] == str(w.actors["Mira"])]
    assert (
        mira
        and mira[0]["channel"] == "whisper"
        and mira[0]["recipients"] == [str(w.actors["Alex"])]
    )
    psv = PerspectiveService(session)
    for n in ("Tomas", "Elara", "Renn"):
        heard = (
            (
                await session.execute(
                    select(Observation).where(
                        Observation.actor_id == w.actors[n],
                        Observation.observation_type == "heard_claim",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert heard == [], n
        assert "speak freely" not in str(await psv.context_candidates(w.actors[n])), n
    assert any(
        b.proposition["predicate"] == "cannot speak freely here"
        for b in await psv.beliefs(w.actors["Alex"])
    )
    # developers see the channel on the model run; players never see another actor's run
    run = (
        (
            await session.execute(
                select(ModelRun)
                .where(ModelRun.actor_id == w.actors["Mira"])
                .order_by(ModelRun.started_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert run is not None and run.structured_output["speech_channel"] == "whisper"
