"""Milestone 04: durable subjective memory with authorized retrieval.

Acceptance: an actor retrieves a meaningful old personal memory without transcript history and
without seeing another actor's memory."""

from __future__ import annotations

import random
import time

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embeddings import HashingEmbedder
from app.persistence.models import Memory, Observation
from app.services.memory import MemoryLineageError, MemoryService
from app.services.speech import ConveysItem, SpeechService
from tests.fixtures.frostbridge import World

pytestmark = [pytest.mark.integration]

FILLER_SUBJECTS = [
    "the weather",
    "the road north",
    "supper at the inn",
    "a lame horse",
    "the river ferry",
    "market prices",
    "a broken cart",
    "snow on the pass",
    "a beggar's song",
    "the guard rotation",
    "candle wax",
    "the smith's hammer",
]
FILLER_VERBS = [
    "noticed",
    "complained about",
    "remembered",
    "laughed at",
    "worried about",
    "argued over",
    "ignored",
    "counted",
]


def filler(rng: random.Random, n: int) -> list[str]:
    return [
        f"I {rng.choice(FILLER_VERBS)} {rng.choice(FILLER_SUBJECTS)} on day {rng.randint(1, 400)}."
        for _ in range(n)
    ]


async def whisper(session: AsyncSession, w: World):
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


async def test_memory_requires_the_actors_own_observations(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    mem = MemoryService(session, HashingEmbedder())
    r = await whisper(session, w)
    elara_obs = [o for o in r.observations if o.actor_id == w.actors["Elara"]]
    m = await mem.create_memory(
        w.h,
        w.actors["Elara"],
        "Alex privately trusted me with his suspicion about Mira.",
        source_observation_ids=[o.id for o in elara_obs],
        salience=0.8,
        emotional_weight=0.4,
        entity_ids=[w.entities["Alex"], w.entities["Mira"]],
    )
    lineage = await mem.lineage(m.id)
    assert [s.source_role for s in lineage] == ["observation"] and lineage[0].event_id == r.event.id
    # Tomas never observed it: he cannot derive a memory from Elara's observation, or from nothing
    with pytest.raises(MemoryLineageError):
        await mem.create_memory(
            w.h, w.actors["Tomas"], "Alex suspects Mira.", source_observation_ids=[elara_obs[0].id]
        )
    with pytest.raises(MemoryLineageError):
        await mem.create_memory(w.h, w.actors["Tomas"], "Alex suspects Mira.")
    # and the whisper event produced no observation for Tomas to cite
    tomas_obs = (
        (
            await session.execute(
                select(Observation).where(
                    Observation.actor_id == w.actors["Tomas"],
                    Observation.source_event_id == r.event.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert tomas_obs == []


async def test_retrieval_finds_the_old_memory_among_a_thousand_and_never_crosses_actors(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    emb = HashingEmbedder()
    mem = MemoryService(session, emb)
    elara, tomas = w.actors["Elara"], w.actors["Tomas"]
    r = await whisper(session, w)
    obs = [o.id for o in r.observations if o.actor_id == elara]
    target = await mem.create_memory(
        w.h,
        elara,
        "Alex privately trusted me with his suspicion about Mira.",
        source_observation_ids=obs,
        salience=0.8,
        emotional_weight=0.4,
        entity_ids=[w.entities["Alex"], w.entities["Mira"]],
    )
    core = await mem.create_memory(
        w.h,
        elara,
        "Joren left home after we argued; I still search for my brother.",
        seed=True,
        is_core=True,
        salience=0.95,
        emotional_weight=0.9,
    )
    # a Tomas memory that is lexically *closer* to the query than Elara's — must never appear
    await mem.create_memory(
        w.h,
        tomas,
        "Alex told me about Mira and his suspicion, privately trusted, word for word.",
        seed=True,
        salience=1.0,
    )

    # 1,000 filler memories for Elara, bulk-inserted directly (vectors from the same embedder)
    rng = random.Random(7)
    texts = filler(rng, 1000)
    vectors = await emb.embed(texts)
    session.add_all(
        [
            Memory(
                campaign_id=w.h.campaign_id,
                actor_id=elara,
                subjective_summary=t,
                salience=rng.uniform(0.1, 0.6),
                created_tick=rng.randint(0, 3_000_000),
                embedding=v,
                embedding_model=emb.model,
                metadata_={"filler": True},
            )
            for t, v in zip(texts, vectors, strict=True)
        ]
    )
    await session.commit()
    # the target memory is old relative to the filler: recency alone would bury it
    await session.execute(
        text("UPDATE memories SET created_tick = 0 WHERE id = :id"), {"id": target.id}
    )
    await session.commit()

    started = time.perf_counter()
    results = await mem.retrieve(
        elara,
        "What did Alex tell me about Mira?",
        k=5,
        focus_entity_ids=[w.entities["Mira"]],
        now_tick=3_000_000,
    )
    elapsed = time.perf_counter() - started
    ids = [x.memory_id for x in results]
    assert target.id == ids[0], [x.summary for x in results]
    assert "mentions a focus entity" in results[0].reasons
    assert all(x.memory_id != target.id or x.relevance > 0 for x in results)
    tomas_ids = (
        {
            m.id
            for m in (await session.execute(select(Memory.id).where(Memory.actor_id == tomas)))
            .scalars()
            .all()
        }
        if False
        else set(
            (await session.execute(select(Memory.id).where(Memory.actor_id == tomas)))
            .scalars()
            .all()
        )
    )
    assert not (set(ids) & tomas_ids)
    assert elapsed < 2.0, f"retrieval took {elapsed:.2f}s over 1,000 memories"

    # core memory is strongly favoured even for a loosely related query
    res2 = await mem.retrieve(elara, "family", k=3, now_tick=3_000_000)
    assert res2[0].memory_id == core.id and res2[0].is_core

    # Tomas can only ever see his own
    res3 = await mem.retrieve(tomas, "What did Alex tell me about Mira?", k=10)
    assert {x.memory_id for x in res3} <= tomas_ids and len(res3) == 1


async def test_compression_keeps_lineage_and_originals(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    mem = MemoryService(session, HashingEmbedder())
    elara = w.actors["Elara"]
    a = await mem.create_memory(
        w.h,
        elara,
        "Mira glanced at the guards before answering.",
        seed=True,
        entity_ids=[w.entities["Mira"]],
    )
    b = await mem.create_memory(
        w.h,
        elara,
        "Mira said people come and go and changed the subject.",
        seed=True,
        entity_ids=[w.entities["Mira"]],
    )
    summary = await mem.compress(
        w.h,
        elara,
        [a.id, b.id],
        "Mira avoids talking about that night, especially near the guards.",
    )
    lineage = await mem.lineage(summary.id)
    assert {s.source_memory_id for s in lineage} == {a.id, b.id} and all(
        s.source_role == "compressed_from" for s in lineage
    )
    for orig in (a, b):
        row = await session.get(Memory, orig.id)
        assert (
            row.status == "compressed"
            and row.parent_memory_id == summary.id
            and row.subjective_summary == orig.subjective_summary
        )
    broad = await mem.retrieve(elara, "Mira avoids talking", k=3)
    assert broad[0].memory_id == summary.id and a.id not in [x.memory_id for x in broad]
    specific = await mem.retrieve(elara, "Mira glanced at the guards", k=3, include_compressed=True)
    assert a.id in [x.memory_id for x in specific]
    with pytest.raises(MemoryLineageError):
        await mem.compress(w.h, w.actors["Tomas"], [a.id], "not his to compress")


async def test_embedder_failure_stores_without_vector_and_backfills(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge

    class Down(HashingEmbedder):
        async def embed(self, texts, *, input_type="document"):
            raise OSError("A9 unreachable")

    m = await MemoryService(session, Down()).create_memory(
        w.h, w.actors["Elara"], "The rain would not stop.", seed=True
    )
    assert (await session.get(Memory, m.id)).embedding is None
    # retrieval still works structurally while the embedder is down
    res = await MemoryService(session, Down()).retrieve(w.actors["Elara"], "rain", k=3)
    assert res and res[0].memory_id == m.id
    n = await MemoryService(session, HashingEmbedder()).embed_pending(w.actors["Elara"])
    assert n == 1 and (await session.get(Memory, m.id)).embedding is not None


async def test_memories_survive_reload(
    session: AsyncSession, frostbridge: World, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    w = frostbridge
    m = await MemoryService(session, HashingEmbedder()).create_memory(
        w.h,
        w.actors["Elara"],
        "Alex helped us on the frozen pass.",
        seed=True,
        is_core=True,
        salience=0.9,
    )
    async with session_factory() as s2:
        res = await MemoryService(s2, HashingEmbedder()).retrieve(
            w.actors["Elara"], "Who helped on the frozen pass?", k=1
        )
        assert res[0].memory_id == m.id and res[0].is_core
        row = await s2.get(Memory, m.id)
        assert (
            row.embedding is not None
            and len(row.embedding) == 1024
            and row.embedding_model == "fake/hashing"
        )
