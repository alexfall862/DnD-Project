# Milestone 11 — Persistence & Stress

## Goal
Prove durability, long-campaign retrieval, and bounded model context.

## Read
`testing/testing-strategy.md` §9, §14–§15, §19; `specifications/turn-budget-and-latency.md` §3, §8; `architecture/03-ai-orchestration.md` §13 (Invariant 13 bounded context).

## Tests
Save/reload with beliefs, memories, relationships, items/hidden properties, goals, conditions, clues, scheduled events, world time, AI audit records.

Generate at least 10,000 events, 1,000 memories, 100 important NPCs for initial stress. Measure DB query latency, memory retrieval latency, context size, model calls per turn, and job backlog.

## Invariants
Context size does not grow linearly with transcript length. Old high-salience/core memories remain retrievable. Unauthorized data stays excluded at scale.

## Acceptance
Campaign resumes after full restart and relevant old context remains available without feeding historical transcript wholesale.
