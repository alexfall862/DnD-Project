"""Opt-in real-model evaluation: memory retrieval with A9's embedder and reranker.

Run with `make eval-local` (pytest -m eval --eval). Scores, not exact strings."""

from __future__ import annotations

import time

import pytest

from app.ai.embeddings import A9Embedder
from app.config import get_settings

pytestmark = [pytest.mark.eval]

MEMORIES = [
    "Alex privately trusted me with his suspicion about Mira.",
    "Joren left home after we argued; I still search for my brother.",
    "Tomas defended Captain Renn's professionalism at the Red Lantern.",
    "We found Oric's ledger in the warehouse; the dock numbers did not match.",
    "The bridge toll went up again and the merchants were furious.",
    "A wagon lost a wheel by the town gate in the cold rain.",
    "Mira glanced at the guards before she answered Alex.",
    "The quarry lights flickered blue the night we arrived.",
]
QUERIES = {
    "What did Alex confide in me?": 0,
    "Do I have family I'm looking for?": 1,
    "What does Tomas think of the guard captain?": 2,
    "What evidence did we find about the smuggling?": 3,
    "Is Mira afraid of someone?": 6,
}


@pytest.fixture
async def a9():
    s = get_settings()
    if not s.a9_token:
        pytest.skip("A9_TOKEN not set")
    e = A9Embedder(
        s.a9_base_url,
        s.a9_token,
        client_name=s.a9_client_name,
        model=s.model_profile_embedding,
        rerank_model=s.model_profile_rerank,
        dimensions=s.embedding_dimensions,
    )
    yield e
    await e.aclose()


async def test_a9_vector_then_rerank_puts_the_right_memory_first(a9: A9Embedder) -> None:
    from app.ai.embeddings import cosine

    doc_vecs = await a9.embed(MEMORIES, input_type="document")
    hits_vec = hits_rerank = 0
    t_q, t_r = [], []
    for q, want in QUERIES.items():
        t0 = time.perf_counter()
        qv = (await a9.embed([q], input_type="query"))[0]
        t_q.append(time.perf_counter() - t0)
        ranked = sorted(range(len(MEMORIES)), key=lambda i: -cosine(qv, doc_vecs[i]))
        hits_vec += ranked[0] == want
        t0 = time.perf_counter()
        rr = await a9.rerank(q, [MEMORIES[i] for i in ranked[:5]], top_n=1)
        t_r.append(time.perf_counter() - t0)
        hits_rerank += ranked[rr[0].index] == want
        if ranked[rr[0].index] != want:
            print(f"\nmiss: {q!r} -> {MEMORIES[ranked[rr[0].index]]!r}")
    p50_q, p50_r = sorted(t_q)[len(t_q) // 2], sorted(t_r)[len(t_r) // 2]
    n = len(QUERIES)
    print(f"\nvector top-1 {hits_vec}/{n}, rerank top-1 {hits_rerank}/{n}")
    print(f"query embed p50 {p50_q:.2f}s, rerank p50 {p50_r:.2f}s")
    assert hits_rerank >= len(QUERIES) - 1
