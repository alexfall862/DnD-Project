# Milestone 02b — Actions, Positioning & Combat

## Goal
Resolve actions through a state machine with theater-of-the-mind positioning, initiative,
damage pipeline, reactions and rest.

## Read
`architecture/02-rules-engine.md` §10–§12, §14, §16–§20, §27, §29, §33; `specifications/core-adventure-rules.md`
§8–§11, §13; `specifications/time-accounting.md` §2; `specifications/database-schema.md` §10;
`testing/testing-strategy.md` §4, §8, §10.

## Implement
Action definitions and action state machine (`proposed → validated → resolving → …`),
action steps and decomposition, requirements/costs/time cost, targeting and range bands,
movement between bands, cover, encounter + pluggable initiative (Core Adventure default),
turn/round advance, damage pipeline with inspectable stages, reactions (Defend/Protect/
Opportunity), rest/recovery, basic equipment, resolution traces, remaining effect primitives
(`move_entity`, `transfer_item`, `create_entity`, `destroy_entity`, `grant/remove_capability`,
`trigger_event`, `schedule_event`, `reveal_information`, `change_relationship` stub).

## Invariants
Actions produce events in one transaction. Every resolution stores a trace. Time costs advance
the world clock through the time service. Hidden item properties apply mechanically without
entering any perspective (perspective itself lands in 03; here, keep hidden fields out of all
API responses).

## Tests
Two deterministic actors (Elara vs. thief template) complete a small combat with initiative,
movement, cover, reaction, damage, condition and surrender; mechanical replay from recorded
seeds/state hashes identically; stale-action revalidation (scene version) rejects a conflicting
item pickup.

## Out of scope
AI decisions, narration, perspective queries.

## Acceptance
`make test-rules` passes and a scripted combat is replayable byte-for-byte on state hash.

## Status
**Done — 2026-10-03.**
- Pure engine (`backend/app/engine/`): `positioning.py` (zone graph, bands engaged/close/near/
  far/distant, engagement, cover, elevation, exits), `encounter.py` (pluggable initiative —
  default 1d20+Agility, Awareness tie-break, engine random — rounds, per-turn Major/Movement/
  Reaction budgets, departure, end detection), `actions.py` (`ActionResolver`: proposed →
  validated → resolving → succeeded/failed/partial/interrupted/invalid; targeting incl. hidden
  and total-cover checks; requirements as safe expressions over resolver facts; economy and
  resource costs; attack with weapon range bands, high ground, cover via `condition.in_cover`,
  Defend/Protect/Opportunity reaction windows through a caller-supplied `ReactionChooser`;
  move/sprint/engage/disengage/withdraw/take_cover/rest/check/surrender/flee/pick_up/drop/wait;
  `ResolutionTrace` on every action; semantic `events` for the service), `stats.py` gains
  `ItemState` (public vs hidden properties) and creature tags; `effects.py` gains the remaining
  primitives (`move_entity`, `transfer_item`, `create/destroy_entity`, `grant/remove_capability`,
  `trigger_event`, `schedule_event`, `reveal_information`, `change_relationship` stub).
- Ruleset data: `actions.yaml` (18 actions), `equipment.yaml` (weapons with attribute damage
  contribution `floor(Might/2)`, armour incl. heavy-armour Agility cap, shield), three more
  conditions (`surrendered`, `fleeing`, `in_cover`).
- Persistence: migrations `0005_rules_actions_rolls` and `0006_resources_conditions_items`;
  `app/services/actions.py` `ActionService` loads a scene's objective state (profiles,
  resource_states, condition_instances, possessed items incl. hidden properties, space,
  encounter, loose items), resolves in memory, then commits in one `EventTransaction`: scene
  version re-checked under lock (`StaleStateError`), one ledger Event per mechanic event,
  Action/ActionStep/ResolutionTrace/Roll rows, projections written back, time cost advanced
  with the resolving event as cause. `start_encounter` / `next_turn` persist initiative and
  round ends (clock +6 s, triggers fired). `WorldService.create_item` and scene `space` support.
- Tests: `tests/rules/` positioning, encounter, actions (economy, range, hidden target, stale
  version, reactions, cover + high ground, hidden dagger bonus vs spirit, pickup/drop, rest,
  flee, surrender), `test_combat_replay.py` (10-seed warehouse fight exercising every mechanic,
  byte-for-byte replay on state hash + seeds, persisted environmental consequence);
  `tests/integration/test_action_service.py` (stale pickup rejected, no duplicate; version
  moved between load and commit caught under lock; combat turn persists rolls that replay
  from seed, traces, projections, encounter state, clock).

Notes / deviations:
- Cover is one mechanism: `condition.in_cover` (intensity 1 partial / 2 strong) modifies
  Defense against non-engaged attackers; moving or engaging clears it. Total cover makes the
  actor untargetable from outside engagement.
- Closing to melee from an adjacent zone is two movement steps (move + engage), per
  core-adventure §9; `action.sprint` covers two steps at the cost of the Major Action.
- Reactions are chosen by the caller (`ReactionChooser`); the resolver only offers legal ones
  and charges the budget. AI/orchestrator-driven choosers arrive in Milestone 06b.
- Flee via an exit zone when not engaged; the opposed-Athletics pursuit roll is left to the
  adjudicator/encounter layer in a later milestone.
