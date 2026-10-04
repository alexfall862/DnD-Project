# Milestone 02a — Rules Core

## Goal
Deterministic generic mechanics foundation: definitions, expressions, dice, stats, checks,
effects, conditions.

## Read
`architecture/02-rules-engine.md` §1–§9, §13–§15, §30, §37; `specifications/core-adventure-rules.md`
§2–§7, §12; `specifications/database-schema.md` §9, §14; `testing/testing-strategy.md` §3, §12, §16.

## Implement
Ruleset loader + manifest validation, definition registry, safe expression evaluator, dice
parser and seeded rolling with roll records, attributes/skills/traits, resources with
derivation formulas, modifiers with provenance, checks (simple, opposed, margins), effect
primitives (`modify_resource`, `deal_damage`, `restore_resource`, `modify_attribute`,
`modify_check`, `apply_condition`, `remove_condition`), conditions with stacking rules,
triggers with depth/effect budget.

## Invariants
No `eval`/`exec`. All randomness via the dice service with seed recorded. Every effect is a
registered primitive. Core Adventure numbers live in ruleset data.

## Tests
Reference validation, seeded reproducibility, derived stats for the Frostbridge builds,
check/opposed/margin tables, resource bounds/overflow, condition stacking, trigger cycle
rejection, invalid effect rejection.

## Out of scope
Actions, movement, encounters, combat, NL interpretation.

## Acceptance
`core_adventure` loads and validates; a scripted sequence of checks and effects on two actors
reproduces identical results from recorded seeds.

## Status
**Done — 2026-10-03.** `backend/app/engine/`: `expressions.py` (safe infix/JSON-AST
evaluator, whitelist only), `dice.py` (notation, `SeedStream` master seed, `RollRecord` replay,
engine-owned `choose`), `ruleset.py` (Pydantic definitions, YAML package loader, reference
validation, modifier-target validation, condition-trigger cycle rejection, content hash),
`stats.py` (`ActorState` ↔ `mechanical_profile`, `StatCalculator` with per-modifier
provenance, attribute clamping, `set` modifiers for armour caps), `checks.py` (difficulty
names, versus-stat, opposed with tie policy, advantage → `2d20kh1/kl1`, criticals flagged not
decisive), `effects.py` (seven registered primitives, damage pipeline with recorded stages,
stacking rules none/refresh/intensity/independent, expiry, shared chain budget), `triggers.py`
(depth/effect budget halts the chain with a recorded `noop`), `core.py` (facade + canonical
state hash). Ruleset data: `backend/rulesets/core_adventure/` (manifest with difficulty scale,
margin bands, settings; attributes, skills, resources, derived stats, checks, 11 conditions,
9 traits, damage types).

Tests: `tests/rules/` — 115 unit tests incl. the Frostbridge builds' derived stats, the margin
table, seeded replay of a two-actor scripted sequence (state hash + recorded seeds), cycle and
invalid-effect rejection.

Notes / deviations:
- YAML parses a bare `on:` key as boolean, so trigger definitions use `event:` instead.
- Persisting rolls/rulesets (`database-schema.md` §9, §14) is deferred to Milestone 02b where
  actions produce the first persisted rolls and traces; migration numbering continues from 0005
  there.
- Effects for 02b (`move_entity`, `transfer_item`, …) register through the same `@primitive`
  decorator.
