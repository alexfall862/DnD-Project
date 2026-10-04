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
