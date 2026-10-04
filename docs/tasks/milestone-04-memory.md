# Milestone 04 — Durable Memory

## Goal
Provide persistent subjective memory without long transcript dependence.

## Read
`architecture/01-world-memory.md` §10; `architecture/03-ai-orchestration.md` §30–§32; `specifications/database-schema.md` §12; `specifications/observation-authoring.md` §4, §6; `testing/testing-strategy.md` §14.

## Implement
Memory, MemorySource, core-memory flag, salience/emotional metadata, embeddings, pgvector retrieval, retrieval scoring, structured-first retrieval.

## Invariants
Memory derives from actor-authorized observations. Source lineage is preserved. Authorization occurs before vector similarity search.

## Tests
Relevant old-memory retrieval among hundreds/thousands, core-memory priority, unauthorized memory exclusion, source lineage, save/reload.

## Out of scope
Sophisticated decay/compression automation beyond schema/basic support.

## Acceptance
An actor can retrieve a meaningful old personal memory without injecting full transcript history and without seeing another actor's memory.

## Status
**Done — 2026-10-03.** Acceptance holds: Elara retrieves "Alex privately trusted me with his
suspicion about Mira" as the top result among 1,000+ of her own memories although it is the
oldest, without any transcript, and a lexically *closer* Tomas memory never appears.
(`tests/integration/test_memory.py`)

- Embeddings/rerank via A9 (`ttrpg/local-embed` Qwen3-Embedding-0.6B 1024-d,
  `ttrpg/local-rerank` bge-reranker-v2-m3); `app/ai/embeddings.py` has the `Embedder`
  protocol, `A9Embedder` (batching ≤256, `input_type` query/document, 503/409 retry) and
  `HashingEmbedder` (deterministic CI stand-in).
- Migration `0008_memory`: `memories` (`vector(1024)`, `entity_ids uuid[]` + GIN, core flag,
  salience/emotion/specificity/accessibility, status, parent) and `memory_sources` (event,
  observation, or source memory; role observation/compressed_from/seed).
- `app/services/memory.py`: `create_memory` enforces lineage (source observations must be the
  actor's own; seed only explicitly); `compress` keeps originals (status `compressed`,
  `parent_memory_id`) and links the summary to them; embedder failure stores without a vector
  and `embed_pending` backfills; `retrieve` = authorize → structured candidates (core, focus
  entities) → exact cosine shortlist over the authorized set → rerank → weighted score
  (relevance, salience, emotion, recency half-life 7 days, entity match, core bonus) with
  reasons for the debug trace.
- Real-model eval (`tests/eval/test_memory_a9.py`, `make eval-local`): vector top-1 4/5,
  rerank top-1 4/5; query embed p50 0.06 s, rerank p50 0.28 s. The miss needs inference
  ("Is Mira afraid of someone?" → "Mira glanced at the guards"), which is the Belief
  Processor's job, not retrieval's.

Notes / deviations:
- No ANN index: exact per-actor scan keeps "authorization before semantic ranking" literal
  (DECISIONS.md). Revisit in Milestone 11.
- `entity_ids` column added to `memories` (not in schema §12) for structured-first retrieval.
- `last_recalled_tick` is not updated on read (a read must not mutate state without an event);
  recall tracking arrives with the Memory Processor in 06c.
- The Frostbridge test fixture moved to `tests/fixtures/frostbridge.py` (pytest plugin).
