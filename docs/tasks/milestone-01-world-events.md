# Milestone 01 — World & Event Ledger

## Goal
Implement persistent campaign/world foundations and append-only authoritative events.

## Read
`architecture/01-world-memory.md` §3, §13, §17, §22; `architecture/05-implementation-plan.md` §5–§8; `specifications/database-schema.md` §1–§8, §18–§20, §22; `specifications/time-accounting.md` §3; `testing/testing-strategy.md` §11.

## Implement
Campaign, Timeline, WorldClock, Entity, Location, LocationEdge, Actor, ActorController, Scene, SceneParticipant, Event, EventEntity.

Add event transaction helper, timeline event sequence allocation, world/scene versioning.

## Invariants
Every authoritative projection mutation commits with an Event in the same transaction. Event order is deterministic per timeline. No ordinary hard deletion of fictional history.

## Tests
Create campaign/actor/location/scene; move actor; advance time; force transaction rollback; reopen DB session; verify persistence and event sequence.

## Out of scope
Rules, beliefs, LLMs.

## Acceptance
A deterministic world state can be created/mutated/reloaded with complete causal event history.

## Status
**Done — 2026-10-03.** Notes from implementation:
- Migrations `0001`–`0004` follow `database-schema.md` §23 grouping; forward references to
  `events` are added as deferred FKs in `0004`, which also installs the `scenes.local_tick ≤
  world clock` trigger (`time-accounting.md` §3). Faction/party and transcript/scheduled-event
  tables exist (schema only; no services yet).
- `app/services/events.py` `EventTransaction` is the only write path: locks campaign +
  timeline + clock, allocates sequence numbers, stamps `world_version_after`, bumps touched
  scene versions, commits atomically; refuses projection changes without an event.
- `app/services/world.py` `WorldService`: campaign/timeline/clock, locations + edges, actors +
  controller history, scenes + participants, `move_actor` (leaves scene, optional travel-time
  advance with causal link), `advance_time` (live scenes follow the clock).
- `app/domain/events.py`: typed payloads, `payload_version = 1`, `parse_payload` registry.
- Tests: `tests/integration/test_world_service.py` (lifecycle + reload in a fresh session,
  controller switch preserves actor, edge requirement, forward-only time) and
  `tests/invariants/test_event_ledger.py` (rollback leaves nothing, no-event mutation rejected,
  4 concurrent writers → contiguous unique sequences, DB rejects duplicate sequence, trigger
  rejects `local_tick` > clock).
