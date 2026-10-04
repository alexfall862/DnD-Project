"""Embedding and rerank providers (DECISIONS.md "Embeddings and rerank via A9").

`Embedder` is the protocol memory retrieval depends on. `A9Embedder` talks to the A9 gateway;
`HashingEmbedder` is a deterministic, dependency-free stand-in for CI (lexical overlap → cosine
similarity), so tests never depend on a stochastic or remote model.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

InputType = Literal["query", "document"]
MAX_BATCH = 256
MAX_CHARS = 6000  # ~2,000 tokens; A9 rejects longer inputs


class EmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float  # raw logit for A9/bge; only comparable within one call


class Embedder(Protocol):
    dimensions: int
    model: str

    async def embed(
        self, texts: list[str], *, input_type: InputType = "document"
    ) -> list[list[float]]: ...

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int | None = None
    ) -> list[RerankResult]: ...


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------------------------------------------
# A9 gateway
# ---------------------------------------------------------------------------------------------


class A9Embedder:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        client_name: str = "ai-ttrpg",
        model: str = "ttrpg/local-embed",
        rerank_model: str = "ttrpg/local-rerank",
        dimensions: int = 1024,
        timeout_s: float = 60.0,
        max_retries: int = 5,
    ) -> None:
        self.model = model
        self.rerank_model = rerank_model
        self.dimensions = dimensions
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}", "X-A9-Client": client_name},
            timeout=timeout_s,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, body: dict) -> dict:
        for _ in range(self.max_retries):
            r = await self._client.post(path, json=body)
            if r.status_code in (503, 409):
                await asyncio.sleep(float(r.headers.get("Retry-After", "2")))
                continue
            if r.status_code >= 400:
                raise EmbeddingError(f"{path} -> {r.status_code}: {r.text[:200]}")
            return r.json()
        raise EmbeddingError(f"{path}: A9 busy after {self.max_retries} retries")

    async def embed(
        self, texts: list[str], *, input_type: InputType = "document"
    ) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), MAX_BATCH):
            batch = [t[:MAX_CHARS] for t in texts[i : i + MAX_BATCH]]
            data = await self._post(
                "/embeddings", {"model": self.model, "input": batch, "input_type": input_type}
            )
            rows = sorted(data["data"], key=lambda d: d["index"])
            for row in rows:
                if len(row["embedding"]) != self.dimensions:
                    raise EmbeddingError(
                        f"expected {self.dimensions} dims, got {len(row['embedding'])}"
                    )
                out.append(row["embedding"])
        return out

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int | None = None
    ) -> list[RerankResult]:
        if not documents:
            return []
        if len(documents) > MAX_BATCH:
            raise EmbeddingError("rerank accepts at most 256 documents")
        body = {
            "model": self.rerank_model,
            "query": query[:MAX_CHARS],
            "documents": [d[:MAX_CHARS] for d in documents],
            "return_documents": False,
        }
        if top_n is not None:
            body["top_n"] = top_n
        data = await self._post("/rerank", body)
        return [RerankResult(int(r["index"]), float(r["relevance_score"])) for r in data["results"]]


# ---------------------------------------------------------------------------------------------
# Deterministic stand-in
# ---------------------------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9']+")
_STOP = frozenset(
    (
        "a an the and or of to in on at for with is was were be been i me my you your "
        "he she his her it they them we us our that this what did do"
    ).split()
)


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


class HashingEmbedder:
    """Signed feature hashing of unigrams and bigrams into `dimensions`, L2-normalised. Same text
    → same vector; shared words → positive cosine. Good enough to test retrieval plumbing."""

    model = "fake/hashing"

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dimensions
        toks = _tokens(text)
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        for f in feats:
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
            v[h % self.dimensions] += 1.0 if (h >> 63) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    async def embed(
        self, texts: list[str], *, input_type: InputType = "document"
    ) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int | None = None
    ) -> list[RerankResult]:
        q = set(_tokens(query))
        scored = []
        for i, d in enumerate(documents):
            dt = set(_tokens(d))
            overlap = len(q & dt)
            scored.append(
                RerankResult(i, overlap * 2.0 - 4.0 + (0.01 * len(dt & q) / (len(dt) or 1)))
            )
        scored.sort(key=lambda r: (-r.score, r.index))
        return scored[:top_n] if top_n else scored


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b, strict=False))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0
