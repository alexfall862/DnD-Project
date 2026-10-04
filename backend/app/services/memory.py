"""MemoryService — durable subjective memory and authorized retrieval (Milestone 04;
world-memory §10, orchestration §30–§32, observation-authoring §4/§6).

Writes:
- `create_memory` requires lineage: every source observation must belong to the remembering
  actor (memory derives from the actor's own experience, never from omniscient events).
  Seeded core memories (fixtures, character creation) use `source_role="seed"`.
- `compress` makes a summary memory whose sources are the compressed memories; the originals
  stay, marked `compressed`, with `parent_memory_id` pointing at the summary.
- Embedding failure never blocks a write: the memory is stored without a vector and
  `embed_pending` backfills later.

Retrieval (`retrieve`), in this order and never otherwise:
1. **authorize** — only this actor's memories, never `inaccessible`, `compressed` only on request;
2. **structured candidates** — core memories, memories mentioning focus entities, most salient;
3. **vector shortlist** — exact cosine over the authorized set (`input_type=query` for the query);
4. **rerank** the union of candidates (optional);
5. **score** with relevance, salience, emotion, recency, entity match and core bonus.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import Embedder, EmbeddingError, sigmoid
from app.domain import events as ev
from app.persistence.models import Memory, MemorySource, Observation
from app.services.events import EventTransaction
from app.services.world import CampaignHandle, WorldError

RECENCY_HALF_LIFE_S = 7 * 24 * 3600
WEIGHTS = {
    "relevance": 0.55,
    "salience": 0.15,
    "emotion": 0.10,
    "recency": 0.10,
    "entity": 0.15,
    "core": 0.20,
}
VECTOR_SHORTLIST = 40
ENTITY_CANDIDATES = 20
CORE_CANDIDATES = 10


class MemoryLineageError(WorldError):
    """A memory may only derive from the remembering actor's own observations."""


@dataclass
class RetrievedMemory:
    memory_id: uuid.UUID
    summary: str
    is_core: bool
    score: float
    relevance: float
    reasons: list[str] = field(default_factory=list)


class MemoryService:
    def __init__(self, session: AsyncSession, embedder: Embedder | None = None) -> None:
        self.session = session
        self.embedder = embedder

    # -- writes ----------------------------------------------------------------------------------

    async def create_memory(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        summary: str,
        *,
        source_observation_ids: list[uuid.UUID] | None = None,
        seed: bool = False,
        emotional_interpretation: str | None = None,
        salience: float = 0.5,
        emotional_weight: float = 0.0,
        is_core: bool = False,
        entity_ids: list[uuid.UUID] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        obs_ids = list(source_observation_ids or [])
        if not obs_ids and not seed:
            raise MemoryLineageError("a memory needs source observations (or seed=True)")
        observations: list[Observation] = []
        if obs_ids:
            observations = list(
                (await self.session.execute(select(Observation).where(Observation.id.in_(obs_ids))))
                .scalars()
                .all()
            )
            if len(observations) != len(set(obs_ids)):
                raise MemoryLineageError("unknown source observation")
            foreign = [o.id for o in observations if o.actor_id != actor_id]
            if foreign:
                raise MemoryLineageError(f"observations {foreign} belong to another actor")
        vector = await self._embed_one(summary)
        async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
            mem = Memory(
                campaign_id=h.campaign_id,
                actor_id=actor_id,
                subjective_summary=summary,
                emotional_interpretation=emotional_interpretation,
                salience=salience,
                emotional_weight=emotional_weight,
                is_core=is_core,
                entity_ids=list(entity_ids or []),
                created_tick=tx.clock.current_tick,
                embedding=vector,
                embedding_model=self.embedder.model
                if (vector is not None and self.embedder)
                else None,
                metadata_=metadata or {},
            )
            self.session.add(mem)
            await self.session.flush()
            event = await tx.emit(
                ev.MemoryCreated(
                    memory_id=mem.id,
                    actor_id=actor_id,
                    is_core=is_core,
                    source_event_ids=sorted({o.source_event_id for o in observations}),
                )
            )
            mem.created_event_id = event.id
            for o in observations:
                self.session.add(
                    MemorySource(
                        memory_id=mem.id,
                        event_id=o.source_event_id,
                        observation_id=o.id,
                        source_role="observation",
                    )
                )
            if seed and not observations:
                self.session.add(
                    MemorySource(memory_id=mem.id, event_id=event.id, source_role="seed")
                )
        return mem

    async def compress(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        memory_ids: list[uuid.UUID],
        summary: str,
        *,
        salience: float | None = None,
    ) -> Memory:
        rows = list(
            (await self.session.execute(select(Memory).where(Memory.id.in_(memory_ids))))
            .scalars()
            .all()
        )
        if len(rows) != len(set(memory_ids)) or any(m.actor_id != actor_id for m in rows):
            raise MemoryLineageError("can only compress this actor's own memories")
        vector = await self._embed_one(summary)
        async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
            summary_mem = Memory(
                campaign_id=h.campaign_id,
                actor_id=actor_id,
                subjective_summary=summary,
                salience=salience if salience is not None else max(float(m.salience) for m in rows),
                emotional_weight=max(float(m.emotional_weight) for m in rows),
                is_core=any(m.is_core for m in rows),
                specificity=0.5,
                entity_ids=sorted({e for m in rows for e in (m.entity_ids or [])}),
                created_tick=tx.clock.current_tick,
                embedding=vector,
                embedding_model=self.embedder.model
                if (vector is not None and self.embedder)
                else None,
                metadata_={"compressed_from": [str(m.id) for m in rows]},
            )
            self.session.add(summary_mem)
            await self.session.flush()
            event = await tx.emit(
                ev.MemoryCompressed(
                    memory_id=summary_mem.id, actor_id=actor_id, compressed_ids=[m.id for m in rows]
                )
            )
            summary_mem.created_event_id = event.id
            for m in rows:
                self.session.add(
                    MemorySource(
                        memory_id=summary_mem.id,
                        source_memory_id=m.id,
                        event_id=event.id,
                        source_role="compressed_from",
                    )
                )
                m.status = "compressed"
                m.parent_memory_id = summary_mem.id
        return summary_mem

    async def embed_pending(self, actor_id: uuid.UUID | None = None, *, batch: int = 64) -> int:
        """Backfill vectors for memories stored while the embedder was unavailable.
        Embeddings are derived data (no event), like a cache of the summary text."""
        if self.embedder is None:
            return 0
        q = select(Memory).where(Memory.embedding.is_(None))
        if actor_id is not None:
            q = q.where(Memory.actor_id == actor_id)
        rows = list((await self.session.execute(q.limit(batch))).scalars().all())
        if not rows:
            return 0
        vectors = await self.embedder.embed(
            [m.subjective_summary for m in rows], input_type="document"
        )
        for m, v in zip(rows, vectors, strict=True):
            m.embedding = v
            m.embedding_model = self.embedder.model
        await self.session.commit()
        return len(rows)

    async def _embed_one(self, text: str) -> list[float] | None:
        if self.embedder is None:
            return None
        try:
            return (await self.embedder.embed([text], input_type="document"))[0]
        except (EmbeddingError, OSError):
            return None  # do less rather than invent state; backfill later

    # -- lineage -------------------------------------------------------------------------------

    async def lineage(self, memory_id: uuid.UUID) -> list[MemorySource]:
        return list(
            (
                await self.session.execute(
                    select(MemorySource).where(MemorySource.memory_id == memory_id)
                )
            )
            .scalars()
            .all()
        )

    # -- retrieval -------------------------------------------------------------------------------

    async def retrieve(
        self,
        actor_id: uuid.UUID,
        query: str,
        *,
        k: int = 5,
        focus_entity_ids: list[uuid.UUID] | None = None,
        now_tick: int | None = None,
        include_compressed: bool = False,
        rerank: bool = True,
    ) -> list[RetrievedMemory]:
        focus = list(focus_entity_ids or [])
        # 1. authorization predicate — every query below carries it
        statuses = ["detailed", "fuzzy", "altered"] + (["compressed"] if include_compressed else [])
        authorized = (Memory.actor_id == actor_id, Memory.status.in_(statuses))

        # 2. structured candidates
        cands: dict[uuid.UUID, Memory] = {}
        core = (
            (
                await self.session.execute(
                    select(Memory)
                    .where(*authorized, Memory.is_core.is_(True))
                    .order_by(Memory.salience.desc())
                    .limit(CORE_CANDIDATES)
                )
            )
            .scalars()
            .all()
        )
        for m in core:
            cands[m.id] = m
        if focus:
            ent = (
                (
                    await self.session.execute(
                        select(Memory)
                        .where(*authorized, Memory.entity_ids.overlap(focus))
                        .order_by(Memory.salience.desc())
                        .limit(ENTITY_CANDIDATES)
                    )
                )
                .scalars()
                .all()
            )
            for m in ent:
                cands[m.id] = m

        # 3. vector shortlist over the authorized set only (exact scan; no ANN post-filtering)
        qvec: list[float] | None = None
        vec_rank: dict[uuid.UUID, float] = {}
        if self.embedder is not None and query.strip():
            try:
                qvec = (await self.embedder.embed([query], input_type="query"))[0]
            except (EmbeddingError, OSError):
                qvec = None
        if qvec is not None:
            dist = Memory.embedding.cosine_distance(qvec)
            rows = (
                await self.session.execute(
                    select(Memory, dist.label("d"))
                    .where(*authorized, Memory.embedding.is_not(None))
                    .order_by(dist)
                    .limit(VECTOR_SHORTLIST)
                )
            ).all()
            for m, d in rows:
                cands[m.id] = m
                vec_rank[m.id] = 1.0 - float(d)
        if not cands:
            fallback = (
                (
                    await self.session.execute(
                        select(Memory)
                        .where(*authorized)
                        .order_by(Memory.salience.desc(), Memory.created_tick.desc())
                        .limit(k)
                    )
                )
                .scalars()
                .all()
            )
            cands = {m.id: m for m in fallback}
        if not cands:
            return []

        # 4. rerank the union
        ordered = list(cands.values())
        relevance: dict[uuid.UUID, float] = {
            m.id: max(0.0, vec_rank.get(m.id, 0.0)) for m in ordered
        }
        reranked = False
        if rerank and self.embedder is not None and query.strip() and len(ordered) > 1:
            try:
                results = await self.embedder.rerank(query, [m.subjective_summary for m in ordered])
                for r in results:
                    relevance[ordered[r.index].id] = sigmoid(r.score)
                reranked = True
            except (EmbeddingError, OSError):
                reranked = False

        # 5. score
        now = now_tick if now_tick is not None else max(m.created_tick for m in ordered)
        focus_set = set(focus)
        out: list[RetrievedMemory] = []
        for m in ordered:
            rel = relevance.get(m.id, 0.0)
            age = max(0, now - m.created_tick)
            recency = math.exp(-math.log(2) * age / RECENCY_HALF_LIFE_S)
            entity_hit = bool(focus_set & set(m.entity_ids or []))
            s = (
                WEIGHTS["relevance"] * rel
                + WEIGHTS["salience"] * float(m.salience)
                + WEIGHTS["emotion"] * float(m.emotional_weight)
                + WEIGHTS["recency"] * recency
                + (WEIGHTS["entity"] if entity_hit else 0.0)
                + (WEIGHTS["core"] if m.is_core else 0.0)
            ) * float(m.accessibility)
            how = "rerank" if reranked else "vector" if m.id in vec_rank else "structured"
            reasons = [f"relevance {rel:.2f} ({how})"]
            if entity_hit:
                reasons.append("mentions a focus entity")
            if m.is_core:
                reasons.append("core memory")
            out.append(
                RetrievedMemory(
                    m.id, m.subjective_summary, m.is_core, round(s, 4), round(rel, 4), reasons
                )
            )
        out.sort(key=lambda r: (-r.score, str(r.memory_id)))
        return out[:k]
