# Milestone 08 — World Simulation

## Goal
Advance meaningful offscreen state when fictional time passes without continuous agent loops.

## Read
`architecture/01-world-memory.md` §22–§24; `architecture/03-ai-orchestration.md` §25–§26, §37; `architecture/05-implementation-plan.md` §16–§17; `specifications/ai-contracts.md` §14; `specifications/time-accounting.md` §4–§6; `specifications/database-schema.md` §8, §17; `testing/testing-strategy.md` §18.

## Implement
ScheduledEvent processing, PostgreSQL-backed background worker, faction goals/plans, plan clocks, important actor travel, simulation budgets, bounded World Simulator role.

## Invariants
Every simulation run has explicit interval, candidates, event budget, iteration/call limits. Deterministic systems run before LLM reasoning. Proposals revalidate current state.

## Tests
Day +2 caravan, Day +3 evidence destruction, Day +5 shipment, quarry escalation, player disruption changing planned result, failed optional job safety.

## Acceptance
Leaving Frostbridge for several days causes coherent world changes without running every NPC continuously.
