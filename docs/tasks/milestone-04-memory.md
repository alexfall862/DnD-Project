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
