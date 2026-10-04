"""Opt-in (`--eval`): the real A9 model plays Mira through the orchestrator's reaction path.
Alex asks about the night Oric vanished; Mira's NPC Actor proposal must validate, every
Claim she produces must come from her own perspective, and no leakage incident may be
recorded. Latency and call counts are printed for the budget record."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import A9Embedder
from app.ai.providers import A9Provider
from app.config import get_settings
from app.engine.core import RulesEngine
from app.persistence.models import Claim, Event, ModelRun
from app.services.orchestrator import PlayRequest, SessionOrchestrator
from app.services.perspective import PerspectiveService
from tests.fixtures.frostbridge import World

pytestmark = [pytest.mark.eval, pytest.mark.integration]


async def test_mira_reacts_on_a9(session: AsyncSession, frostbridge: World) -> None:
    s = get_settings()
    if not s.a9_token:
        pytest.skip("A9_TOKEN not set")
    w = frostbridge
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Oric"], "Oric")
    await w.knowledge.learn_identity(w.h, w.actors["Alex"], w.entities["Renn"], "Captain Renn")
    await w.knowledge.learn_identity(w.h, w.actors["Mira"], w.entities["Oric"], "Oric")
    provider = A9Provider(s.a9_base_url, s.a9_token, client_name=s.a9_client_name)
    orch = SessionOrchestrator(
        session,
        s,
        engine=RulesEngine.load("core_adventure", master_seed=11),
        provider=provider,
        embedder=A9Embedder(s.a9_base_url, s.a9_token, client_name=s.a9_client_name),
    )
    res = await orch.process_player_input(
        w.h,
        PlayRequest(
            w.actors["Alex"],
            'I ask Mira quietly, "Was Captain Renn here the night Oric vanished?"',
        ),
    )
    print("METRICS", res.metrics)
    print("SPEAKERS", res.speakers)
    runs = (
        (
            await session.execute(
                select(ModelRun)
                .where(ModelRun.campaign_id == w.h.campaign_id)
                .order_by(ModelRun.created_at)
            )
        )
        .scalars()
        .all()
    )
    for r in runs:
        print(
            "RUN", r.role, r.status, r.latency_ms, "ms", r.prompt_tokens, "+", r.completion_tokens
        )
        if r.role == "npc_actor":
            print("MIRA RAW", (r.raw_output or "")[:800])
    assert res.metrics["calls_by_role"].get("intent_interpreter") == 1
    reactions = res.metrics.get("reactions", {})
    assert reactions.get("visible", 0) >= 1, res.metrics
    npc_runs = [r for r in runs if r.role == "npc_actor"]
    assert npc_runs and npc_runs[-1].status in ("ok", "repaired"), [r.validation for r in npc_runs]
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
    assert leaks == [], [e.payload for e in leaks]
    claims = (
        (await session.execute(select(Claim).where(Claim.speaker_actor_id == w.actors["Mira"])))
        .scalars()
        .all()
    )
    psv = PerspectiveService(session)
    for c in claims:
        if c.source_fact_id is not None:
            assert await psv.repo.holds_fact(w.actors["Mira"], c.source_fact_id)
        assert c.source_fact_id != w.facts["renn_killed_oric"]  # she cannot know this
    print("CLAIMS", [(c.predicate, c.speaker_stance, c.fidelity) for c in claims])
