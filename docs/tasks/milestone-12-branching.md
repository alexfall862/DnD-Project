# Milestone 12 — Timeline Branching

## Goal
Implement alternate timeline branches for development and eventual player use.

## Read
`architecture/01-world-memory.md` §3 (Timeline), §17; `specifications/database-schema.md` §3, §18–§20; `specifications/api-contracts.md` §17, §21; `testing/testing-strategy.md` §8.

## Implement
Branch creation from event, parent/branch references, projection rebuild/materialization for branch, active-timeline switch, independent continuation, mechanical replay support.

## Invariants
Parent timeline is immutable. Branch events/state do not leak back into parent. Retcons prefer explicit compensating events or branch rather than historical mutation.

## Tests
Branch before a decision, perform divergent action, compare state hashes, switch timelines repeatedly, ensure parent unchanged.

## Acceptance
Two timelines continue independently from one shared historical prefix.
