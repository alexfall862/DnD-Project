"""The deterministic stand-in embedder behaves like an embedder."""

from __future__ import annotations

import pytest

from app.ai.embeddings import HashingEmbedder, cosine, sigmoid

pytestmark = pytest.mark.unit


async def test_hashing_embedder_is_deterministic_normalised_and_lexical():
    e = HashingEmbedder(1024)
    a, b, c = await e.embed(
        [
            "Alex privately trusted me with his suspicion about Mira.",
            "Alex privately trusted me with his suspicion about Mira.",
            "The bridge toll went up again.",
        ]
    )
    assert len(a) == 1024 and a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
    q = (await e.embed(["what did Alex say about Mira"], input_type="query"))[0]
    assert cosine(q, a) > cosine(q, c)


async def test_hashing_rerank_orders_by_overlap():
    e = HashingEmbedder()
    docs = [
        "The bridge toll went up again.",
        "Alex told me he suspects Mira.",
        "Mira poured the ale.",
    ]
    res = await e.rerank("what did Alex tell me about Mira", docs, top_n=2)
    assert [r.index for r in res] == [1, 2]


def test_sigmoid_bounds():
    assert sigmoid(0) == 0.5 and sigmoid(10) > 0.99 and sigmoid(-10) < 0.01
