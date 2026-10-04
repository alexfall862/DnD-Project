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

## Tickets (decomposition, 2026-10-04)

| # | Ticket | Likely files |
|---|---|---|
| 08-0 | NPC Actor output gains `speech_channel` / `speech_target_ref` (whispers; visible in debug model runs) | `ai/roles.py`, `prompts/actors/npc_actor_v1.md`, tests |
| 08-1 | `background_jobs` (schema §17) + migration 0013; `JobQueue` (enqueue, claim `FOR UPDATE SKIP LOCKED`, complete/fail with attempts, backoff, `not_before`); worker loop `app/worker.py` (`make worker`); handlers memory.embedding, memory.process, journal.update, simulation.advance; optional-job failure never touches campaign state | `persistence/models/jobs.py`, `services/jobs.py`, `worker.py`, `Makefile` |
| 08-2 | Plan clocks: structured plan steps (`at_tick`, `kind`, `prerequisites`); deterministic advancement on time; `actor.travel` scheduled handler (important NPC travel through SceneService) | `services/schedule.py`, `services/psychology.py`, `services/simulation.py` |
| 08-3 | World Simulator role: `WorldSimulatorOut` schema, objective context (interval, candidates, plans, deterministic changes, budget), proposal validation and application; `SimulationService.tick` = scheduled events → deterministic systems → candidates → at most one bounded call; `simulation.run` event | `ai/roles.py`, `prompts/world/world_simulator_v1.md`, `services/simulation.py` |
| 08-4 | Triggers: clock advances ≥ granularity, wait/rest actions, debug `advance-time` endpoint with `process_simulation`; Frostbridge seed gains plan clocks and Renn's Day +5 dock travel | `services/orchestrator.py`, `api/v1/debug.py`, `seeds/frostbridge.py` |
| 08-5 | Tests: caravan, evidence destruction, shipment departs / is disrupted (detained Renn, missing cargo), quarry, NPC travel, job queue claim semantics, failed optional job safety, budgets | `tests/integration/test_world_simulation.py`, `tests/integration/test_jobs.py` |
| 08-6 | Docs: status, decisions, CLAUDE.md, progress report | `docs/` |

## Status
**Done — 2026-10-04.** Leaving Frostbridge for six days (`tests/integration/test_world_simulation.py`)
assembles the River Compact's cargo and loads the barge by plan clock, walks Renn to the
Restricted Dock by scheduled travel, asks the World Simulator exactly once whether the barge
departs, establishes "the shipment left" when it says so, fires the Day +8 quarry escalation
with no call at all, and records every run as a `simulation.run` event with its interval,
candidates and budget. Detaining Renn first cancels the travel, the loading, the documentation
burn and the departure by prerequisite revalidation before any model is asked.

- `SimulationService` (`services/simulation.py`): deterministic systems → candidates → one
  bounded call → record. Plan steps may carry `at_tick`/`kind`/`prerequisites`; scheduled
  events may carry `on_proceed`. Proposals are validated against the candidate map and the
  event budget; unknown subjects and wrong types are rejected and listed.
- World Simulator role: `WorldSimulatorOut` schema (`proceed | cancel | plan_hold |
  plan_advance | plan_abandon | actor_travel`), prompt v1 updated, 600 max tokens.
- Triggers: a live turn crossing the 6-hour granularity or ending with wait/rest
  (`turn_metrics.simulation`), `POST /api/v1/debug/campaigns/{id}/advance-time?seconds=…
  &process_simulation=true`, and the `simulation.advance` job.
- Background worker: `background_jobs` (migration 0013), `JobQueue` (claim with
  `FOR UPDATE SKIP LOCKED`, dedupe, backoff, stale recovery), `python -m app.worker [--once]`
  (`make worker`). Handlers: memory.embedding, memory.process, journal.update,
  simulation.advance; the orchestrator queues deferred checkpoints and journals.
  `GET /debug/campaigns/{id}/jobs` lists them.
- NPC Actor output has `speech_channel`/`speech_target_ref` (08-0): Mira can answer a whisper
  with a whisper; `tests/integration/test_npc_whisper.py`.
- Frostbridge seed: structured plan clocks for the River Compact, Renn's Day +5 dock travel,
  the `shipment_departed` fact as the departure's consequence.

Tests: `test_world_simulation.py` (departure, disruption, proposal validation/budget, idle
world), `test_simulation_triggers.py` (rest trigger, debug endpoint, deferred jobs),
`test_jobs.py` (disjoint claims, retry/failed, optional-job safety), `test_npc_whisper.py`.

Not in 08 (by design, see `DECISIONS.md`): deep economics, continuous NPC loops, a
`simulation_runs` table, `world.materialize` (09). The real-model simulator prompt has not been
run against A9 yet (`make eval-local` backlog).
