# Persistent AI TTRPG Engine — System-Agnostic Rules Engine v0.1

## 1. Purpose

The engine must support multiple genres and future rulesets without hardcoding fantasy-specific concepts. It should support configurable dice mechanics, initiative systems, actor resources, items, powers, creatures, traps, crafting, advancement, and AI-generated mechanics while remaining deterministic, auditable, and safe.

> **Rulesets define what mechanics mean. The engine defines what mechanics are allowed to do.**

The engine understands generic primitives such as Actor, Attribute, Resource, Skill, Trait, Effect, Condition, Action, Check, Contest, Damage, Recovery, Item, Ability, Movement, Range, Duration, Target, Clock, Relationship, Currency, and Inventory.

Rulesets define concepts such as wizard, pistol, mana, sanity, laser rifle, spell, cyberdeck, or longsword.

## 2. Rules precedence

Rules resolve through explicit layers:

`engine primitives → base ruleset → genre/system module → campaign module → house rule → temporary ruling → active effect`

This allows campaign-specific overrides without mutating the underlying engine.

## 3. Ruleset packages

A ruleset is a declarative package containing a manifest and definitions for attributes, skills, resources, checks, actions, conditions, effects, equipment, abilities, character creation, advancement, combat, recovery, travel, and content templates.

Definitions use stable machine-readable IDs such as:

- `attr.agility`
- `skill.stealth`
- `resource.health`
- `condition.poisoned`
- `action.attack`
- `effect.damage`

Display names are separate from identifiers.

## 4. Safe expression language

Derived statistics and conditions use a whitelist-based expression evaluator, not arbitrary Python/JavaScript.

Initial operations include literal/ref, add/subtract/multiply/divide, min/max/clamp, floor/ceil/round, if, equality/comparison, boolean operators, count, and sum. Future operations may add lookup/foreach/has_tag as necessary.

Never use `eval()` or `exec()` for rules.

## 5. Attributes, skills, and traits

Attributes are broad capabilities with ruleset-defined range and defaults. Skills may have default attributes but can be paired with different attributes when fiction warrants it.

Traits represent persistent mechanical or narrative qualities such as Night Vision, Veteran Soldier, Synthetic, Undead, Noble, Psionic, or Amphibious. Traits may grant effects, actions, capabilities, or requirements.

## 6. Generic resources

Resources cover HP/Health, mana, stamina, stress, sanity, oxygen, fuel, ammo, hunger, luck, resolve, heat, corruption, and similar systems.

Resource definitions may include minimum, maximum formula, regeneration, depletion behavior, overflow behavior, and visibility.

## 7. Checks

A Check is the generic mechanism for uncertain resolution. Rulesets define roll expression, modifier formula, target type, success rule, critical rules, degrees of success, opposed checks, and tie behavior.

Not every uncertain-looking action requires a roll. The adjudicator should first ask whether the outcome is uncertain, whether failure matters, and whether a rule calls for a check.

## 8. Dice and randomness

All actual randomness comes from the engine's dice/random service. Initial notation should support at least:

- `1d20`
- `2d6+3`
- `4d6kh3`
- `2d20kh1`
- `d100`

Future support can include exploding dice, dice pools, rerolls, custom symbols, and success counting.

Every roll stores expression, seed, raw dice, modifiers, final result, actor, purpose, visibility, and associated event. Seeded rolls permit deterministic replay.

Random tables are first-class engine objects. Models may request a random selection but do not “choose randomly” themselves.

## 9. Modifiers

Modifiers are generic operations (add/subtract/multiply/set/advantage/disadvantage) with target, value, conditions, source, and priority.

Every applied modifier retains provenance so debug output can explain a result line-by-line.

## 10. Actions

Action definitions specify requirements, costs, targeting, resolution, effects, time cost, and tags.

Generic categories include movement, attack, defense, interaction, social, exploration, ability, resource, crafting, travel, and downtime.

Actions are not the same as actor intent. Intent means what an actor wants; Action is what the engine attempts to resolve.

## 11. Targeting and range

Targeting is declarative: self, actor, item, location, zone, area, all-in-zone, known entity, visible entity, etc., with range, line-of-sight, allegiance, alive/dead, tag, and size constraints.

The engine supports theater-of-the-mind range bands (`engaged`, `close`, `near`, `far`, `distant`) as the initial default while leaving room for rulesets that use meters, hexes, or squares.

## 12. Costs and action economy

Actions may consume resources, items, charges, time, actions, reactions, movement, currency, or conditions.

Action economy is ruleset-defined. Core Adventure initially uses one Major Action, one Movement, and one Reaction, but other rulesets can use action points, side initiative, simultaneous declarations, or phase-based systems.

## 13. Effects

Every mechanical mutation occurs through a registered effect primitive. Initial primitives include:

- `modify_resource`
- `deal_damage`
- `restore_resource`
- `modify_attribute`
- `modify_check`
- `apply_condition`
- `remove_condition`
- `move_entity`
- `transfer_item`
- `reveal_information`
- `create_entity`
- `transform_entity`
- `destroy_entity`
- `grant_capability`
- `remove_capability`
- `change_relationship`
- `trigger_event`
- `schedule_event`

An LLM may compose these primitives but cannot invent executable code.

## 14. Damage

Damage remains separate from generic resource modification because rules often intercept it. Damage types and armor/resistance/vulnerability behavior belong to the ruleset.

A typical pipeline is:

`raw damage → source modifiers → target resistance → armor → vulnerability → min/max rules → resource modification → damage-triggered effects`

Every stage should be inspectable.

## 15. Conditions and triggers

Condition definitions include stacking rules, effects, removal conditions, and tags. Stacking may be none, duration refresh, intensity increase, or independent instances.

Triggers include on_action_started/resolved, on_attack, on_hit, on_damage, on_condition_applied, on_resource_changed, on_enter/leave_location, on_rest, on_round_start/end, and on_time_elapsed.

Trigger processing has a hard nested depth/effect budget and detects obviously recursive definitions.

## 16. Initiative and encounters

Initiative is a plugin abstraction. Core Adventure defaults to `1d20 + Agility` descending, but side initiative, popcorn, speed order, simultaneous turns, or phase systems can replace it.

An Encounter tracks scene, initiative provider, round, participants, turn/action budgets, and encounter state.

## 17. Character representation

Every actor uses the same mechanical representation:

`attributes + skills + traits + resources + abilities + conditions + equipment + advancement`

Human and AI PCs are mechanically identical.

## 18. Character creation

Rulesets define creation steps, constraints, budgets, backgrounds, archetypes/classes if any, skill choices, equipment, and derived statistics.

Conversational creation is a translation layer. A user can say “older disgraced knight afraid of magic,” and the LLM proposes a valid mechanical build that the engine validates. The player may then edit it through a conventional form.

## 19. Advancement

Advancement can be XP levels, milestones, point-buy improvement, skill growth, or downtime training. Humans edit/select directly within rules; AI PCs choose among legal options using personality, goals, and tactical preferences.

## 20. Abilities

Spells, maneuvers, cybernetic programs, psionic powers, special attacks, and social maneuvers use the same general Ability/Action infrastructure: requirements, costs, targeting, resolution, effects, cooldown, charges, and tags.

## 21. Items and generated mechanics

Item templates define general mechanics; item instances retain unique history and state.

World Author generated items use this pipeline:

`narrative need → concept → primitive mechanics proposal → schema/reference validation → cycle/safety validation → balance analysis → template/instance → canon commit`

Validation distinguishes:

- invalid (cannot execute);
- unsafe (cycles/broken references);
- unbalanced (extreme relative to baseline);
- valid.

Unbalanced is not necessarily rejected; a legendary artifact may intentionally be powerful if the engine can represent it safely.

## 22. Hidden properties and perspective-sensitive mechanics

An item may objectively have hidden mechanics the owner does not know. The rules engine can use a hidden property when resolving a real interaction even though the property is absent from the character's context/UI.

Rules may also query authorized perspective state, e.g. a gate that opens only for someone who knows its true name.

## 23. Creature templates and promotion

Creatures use template-plus-instance. A random goblin can begin with mechanical state and minimal behavior, then be promoted into a full actor with personality, goals, memories, relationships, and name if it becomes important.

## 24. Encounter difficulty

Difficulty estimation is advisory and ruleset-defined. The world author can intentionally create overwhelming encounters. The engine should not enforce “balanced” story outcomes.

## 25. Hazards, traps, crafting, and invention

Hazards/traps use triggers, detection/avoidance checks, effects, reset rules, and duration.

Known crafting uses recipe definitions; novel crafting flows through intent → adjudication → ingredient capability analysis → temporary recipe proposal → validation → resolution. Successful inventions can become persistent recipes.

The same flow supports custom spells, weapons, vehicle modifications, chemicals, rituals, software, and magical devices.

## 26. Social mechanics

Social checks may modify willingness, belief, relationship, fear, or temporary behavior. Success is not unrestricted mind control.

Difficulty may consider goals, values, relationship, risk, stakes, fear, status, evidence, payment, and other contextual factors.

Insight-type mechanics should generally expose observations (“he hesitates”) rather than omniscient truths (“he is lying”) unless a rule explicitly grants truth detection.

## 27. Fail-forward and time

Fail-forward is configurable. Possible failure policies include hard failure, failure with cost, partial progress, or complication.

Actions can specify time costs in seconds, minutes, hours, days, rounds, or custom units that ultimately advance the world clock where appropriate.

## 28. Travel, rest, economy, encumbrance, ammunition

These are modular subsystems. Campaigns can choose none/light/deep survival detail. Currency may be an abstract resource or physical items. Encumbrance can be off/simple/detailed; ammunition can be ignored/abstract/individual.

## 29. Rules API

Core engine operations should include concepts such as:

- get available actions;
- validate action;
- resolve check;
- resolve action;
- calculate stat;
- apply effect;
- get modifiers;
- start encounter;
- advance turn;
- advance time.

LLM-facing tools are narrower: inspect capabilities, list legal actions, propose action/check/effect composition, lookup rules/item/condition, estimate content power.

Models never execute SQL or directly modify resource rows.

## 30. Mechanical proposals and validation

Generated mechanics return a `MechanicalProposal` with definition/effects/requirements/assumptions and pass:

1. schema validation;
2. reference validation;
3. type validation;
4. requirement validation;
5. cycle detection;
6. authority validation;
7. balance analysis;
8. canon conflict check.

Only the first six determine basic legality; balance can warn without rejecting.

## 31. Runtime rulings and precedent

When no existing rule applies, the Rules Adjudicator may propose a temporary ruling using registered primitives. Default scope is single-use.

Rulings can be stored as precedent with situation embedding, summary, mechanic, usage count, and history. Prior rulings improve consistency but do not automatically become immutable universal law.

## 32. Rules retrieval

Models should not receive the entire ruleset. The Context Compiler retrieves relevant rule definitions for the current action. A balcony-to-wagon jump needs fall/jump/moving-target rules, not crafting and underwater combat.

Every resolution records which rules were consulted.

## 33. Resolution traces

Resolved actions should preserve an optional trace containing input intent, resolved action, rules consulted, requirements checked, modifiers, rolls, proposed/applied/rejected effects, state mutations, and events created.

## 34. Imported/community rulesets

Community rulesets should begin as declarative packages validated for references, cycles, and test fixtures. AI-assisted import can translate source documents into this declarative schema for review.

Executable plugins, if ever allowed, should be a separate trusted extension mechanism with permissions and sandboxing expectations; they are not required for ordinary rulesets.

## 35. Versioning and snapshotting

Campaigns record ruleset/module versions. Updating a ruleset requires explicit migration rather than silently changing an existing campaign.

Established unique generated content snapshots its mechanics. If a base template later changes, the established artifact does not silently change.

## 36. Core Adventure role

The first ruleset is an original, deliberately conventional system used to test the generic engine. Its detailed numbers are in `../specifications/core-adventure-rules.md`.

## 37. Rules-engine invariants

- LLMs never generate authoritative random results.
- LLMs never directly mutate mechanical state.
- Every effect uses a registered primitive.
- All references resolve.
- State changes produce events.
- Modifiers retain provenance.
- Rolls are reproducible.
- Generated mechanics cannot execute arbitrary code.
- Trigger cycles are rejected/bounded.
- Perspective-sensitive mechanics use authorized queries.
- Established mechanics cannot silently change.
- Ruleset updates cannot silently alter existing campaign state.
- Human and AI PCs share one mechanical representation.
