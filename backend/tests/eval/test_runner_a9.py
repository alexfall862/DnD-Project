"""Opt-in: the real A9 model receives Elara's audited context and returns a valid AI Player
proposal whose conveys refs stay inside her perspective (local provider smoke test)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.embeddings import A9Embedder
from app.ai.providers import A9Provider
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import get_settings
from app.engine.core import RulesEngine
from app.persistence.models import ModelRun
from app.services.memory import MemoryService
from app.services.speech import ConveysItem, SpeechService
from tests.fixtures.frostbridge import World

pytestmark = [pytest.mark.eval, pytest.mark.integration]


async def test_elara_responds_to_the_whisper_on_a9(
    session: AsyncSession, frostbridge: World
) -> None:
    s = get_settings()
    if not s.a9_token:
        pytest.skip("A9_TOKEN not set")
    w = frostbridge
    await SpeechService(session).utter(
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
    embedder = A9Embedder(s.a9_base_url, s.a9_token, client_name=s.a9_client_name)
    provider = A9Provider(
        s.a9_base_url,
        s.a9_token,
        client_name=s.a9_client_name,
        max_concurrent=s.max_concurrent_inference,
    )
    try:
        mem = MemoryService(session, embedder)
        await mem.create_memory(
            w.h,
            w.actors["Elara"],
            "Joren left home after we argued; I still search for my brother.",
            seed=True,
            is_core=True,
            salience=0.95,
        )
        ctx = await ContextCompiler(
            session, memory=mem, engine=RulesEngine.load("core_adventure")
        ).compile(
            w.h,
            "ai_player",
            actor_id=w.actors["Elara"],
            purpose="respond to whisper",
            situation=(
                "Alex just whispered to you that he thinks Mira is involved. Decide what to say "
                "or do, and to whom. Entity refs: alex, tomas, mira."
            ),
            query="What did Alex tell me about Mira?",
            focus_entity_ids=[w.entities["Mira"]],
        )
        res = await ModelRunner(session, ModelRouter(s, provider)).run(w.h, ctx)
    finally:
        await provider.aclose()
        await embedder.aclose()
    row = await session.get(ModelRun, res.model_run_id)
    print(
        f"\nstatus {res.status} calls {res.calls} latency {res.latency_ms} ms "
        f"echo {res.model_echo} tokens {res.prompt_tokens}/{res.completion_tokens} "
        f"cached {res.cached_tokens}"
    )
    print("summary:", res.output.decision_summary if res.output else res.errors)
    print("spoken:", res.output.spoken_text if res.output else None)
    print(
        "conveys:",
        [(c.kind, c.ref_id, c.stance) for c in res.output.conveys] if res.output else None,
    )
    assert res.ok, res.errors
    assert not res.model_mismatch and row.model_echo == s.model_profile_balanced_reasoning
    for c in res.output.conveys:
        if c.ref_id:
            assert c.ref_id in ctx.ref_map, f"ref outside Elara's context: {c.ref_id}"
    assert res.latency_ms < 40_000
