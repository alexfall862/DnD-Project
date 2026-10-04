# AI TTRPG Engine — Implementation Agent Instructions

You are implementing a persistent AI-powered tabletop roleplaying engine.

The repository contains authoritative architecture and specification documents. Your job is to **implement those designs incrementally**, not redesign the application while coding.

## Read first

Before substantial implementation work, read:

- `/architecture/01-world-memory.md`
- `/architecture/02-rules-engine.md`
- `/architecture/03-ai-orchestration.md`
- `/architecture/04-campaign-generation.md`
- `/architecture/05-implementation-plan.md`
- `/specifications/database-schema.md`
- `/specifications/api-contracts.md`
- `/specifications/ai-contracts.md`
- `/specifications/core-adventure-rules.md`
- `/specifications/frostbridge-demo.md`
- `/testing/testing-strategy.md`
- `/testing/knowledge-leakage.md`
- `/testing/vertical-slice.md`
- `/specifications/communication-and-knowledge.md`
- `/specifications/belief-update-rules.md`
- `/specifications/turn-budget-and-latency.md`
- `/GLOSSARY.md`

Read `GLOSSARY.md` and this file in full once. For each milestone, read the `## Read` context
pack in its `/tasks` file rather than rereading every document. The remaining specifications
(`specifications/human-visibility.md`, `specifications/time-accounting.md`, `specifications/player-authored-canon.md`,
`specifications/observation-authoring.md`, `specifications/canon-extraction-allowlist.md`) are pulled in by the milestones
that need them.

## Core doctrine

This project is not an AI chatbot pretending to run an RPG. It is a persistent tabletop simulation engine with AI-powered interpretation, roleplay, actor decisions, world authorship, memory interpretation, and narration.

The application itself owns objective world truth, rules, mechanics, randomness, state, events, authorization, and persistence.

### Invariant 1 — LLMs propose; engine commits

A language model may propose intent, action, belief change, goal update, item mechanics, world content, a ruling, or dialogue. It must never directly mutate authoritative state.

All proposals pass through schema validation, reference validation, authorization, rules validation, and world-version validation before state changes.

### Invariant 2 — Objective truth and subjective knowledge are separate

The database may objectively know that Captain Renn killed Oric. An actor does not know this unless knowledge reached that actor through a valid path.

Never infer `database fact = party knowledge`.

There is no global party knowledge store.

### Invariant 3 — Perspective is an authorization boundary

An AI-controlled actor must not receive omniscient state and then merely be instructed not to use it.

Unauthorized information must not be retrievable. AI actor context must go through `PerspectiveService`, not direct objective-world repository access. Authorization happens before semantic/vector retrieval.

### Invariant 4 — Every important state mutation has an Event

No direct unexplained mutation of HP, location, inventory, ownership, conditions, relationships, goals, facts, or time.

Current state is stored as efficient projections, but mutations and their authoritative Events commit atomically.

### Invariant 5 — Randomness belongs to the engine

All randomness uses the random/dice service. LLMs never provide authoritative dice rolls, random-table selections, initiative rolls, or damage rolls.

A model may request that a roll occur. The engine produces the result.

### Invariant 6 — Narration follows resolution

Order:

`intent → mechanics → events → observations → actor reactions → narration`

The narrator describes resolved outcomes. It does not decide them. Do not parse narrator prose to determine whether an attack hit or someone died.

### Invariant 7 — Speech is not truth

When a character says, “The king is dead,” store a Claim, not automatically a Fact.

Characters may lie, be mistaken, repeat rumors, misremember, or speculate.

### Invariant 8 — Memory is subjective

Memory is based on actor observation plus actor interpretation, not global event truth. False or distorted memories are valid subjective state. Their objective sources remain auditable.

### Invariant 9 — Established canon is immutable

Latent unseen generated material may be revised. Once material is established through observation, communication, or consequences, do not silently rewrite it.

Development corrections use explicit retcon or timeline branch.

### Invariant 10 — Important mysteries lock their truth

Generate truth before clues. Once activated, `solution_locked = true`.

The system may dynamically vary how evidence is encountered. It may not change the answer because another solution would be narratively convenient.

### Invariant 11 — Human and AI PCs use the same game representation

A character is not mechanically different because it is AI-controlled.

Controller is runtime state: `human | ai | scripted | dormant`.

Switching controller does not replace memories, goals, relationships, mechanics, identity, or history.

### Invariant 12 — Generated mechanics use registered primitives

LLMs may compose new items, abilities, spells, traps, creatures, and rulings using registered rule/effect primitives.

Do not execute LLM-generated Python or JavaScript. Do not use `eval()` or `exec()` for rules.

Generated content may be intentionally unbalanced if permitted. It may not be structurally invalid.

### Invariant 13 — Context remains bounded

Do not solve campaign continuity by continually appending transcript history.

Use structured current state, beliefs, relationships, goals, core memories, recent conversation, and semantic retrieval to compile task-specific context.

A 500-session campaign should not require a 500-session prompt.

### Invariant 14 — No uncontrolled agent loops

Every AI-driven multi-step operation has an explicit purpose, candidate scope, maximum iterations, maximum calls, and maximum proposals.

World simulation always has a time interval, subject set, and event budget.

Never implement an unbounded “ask the model again until solved” loop.

### Invariant 15 — Human spotlight matters

AI actors may disagree, leave, initiate conversation, make mistakes, pursue personal goals, and act privately.

But AI-to-AI activity must not turn play into the human watching autonomous bots talk indefinitely. Respect Spotlight Governor limits.

### Invariant 16 — Speech carries structured information content

Every utterance that reaches another actor produces Claims with `conveys[]`; AI-produced
`conveys` references must lie within the speaker's perspective or the proposal is rejected.
Beliefs derive from Claims and Observations by deterministic rules; a model may adjust only
within `specifications/belief-update-rules.md` §7. Nothing reads prose to decide who knows what.

### Invariant 17 — Every turn is budgeted and measured

A turn has a synchronous call cap and a time budget (`specifications/turn-budget-and-latency.md`). The
orchestrator degrades optional work in the documented order rather than exceeding them, and
writes `turn_metrics` for every turn from the first orchestrator commit. Latency work is not
polish; it is part of each milestone's acceptance.

### Invariant 18 — The human is also a perspective

The client renders exactly one focus actor's perspective. Offscreen scenes are not shown and
focus/controller switches transfer no in-fiction knowledge. Player assertions about the world
go through `specifications/player-authored-canon.md`; they never become silent state.

## Preferred implementation style

Prefer clear modules, explicit types, Pydantic schemas, small services, database constraints, testable pure functions, and dependency injection for model providers.

Avoid giant manager classes, global mutable state, provider-specific logic in domain code, untyped JSON everywhere, and prompt-only security.

## PostgreSQL

PostgreSQL is authoritative persistence. Use JSONB where ruleset extension genuinely requires flexibility. Use relational fields for identity, foreign keys, event references, authorization, ownership, timelines, and relationships.

Do not store the entire campaign in one JSON blob.

## Events

Events are append-only during ordinary play. Each Timeline has deterministic event sequence numbers. Projection updates and Event creation must occur in the same transaction.

## Rule definitions

Rulesets should remain declarative. The first ruleset is `Core Adventure`.

Do not hardcode Core Adventure concepts into generic engine components when they can remain ruleset definitions.

## AI provider architecture

Models are referenced through logical profiles such as `fast_structured`, `balanced_reasoning`, `creative_narrative`, and `deep_world_author`.

Do not hardcode a specific local model name throughout the application.

The initial local provider should speak an OpenAI-compatible HTTP protocol. Future cloud providers use adapters.

## Provider-side memory

Never depend on a provider's hidden conversation state. Every model invocation should be reconstructable from database state, the Context Compiler, and prompt version.

The model process may restart without losing campaign continuity.

## Structured AI output

All AI output that may affect persistent state must be schema-valid structured data.

Freeform text is principally for narration, dialogue, descriptions, and documents. Even then, structured metadata may accompany prose.

## Model auditing

In development mode store ModelRun, ContextSnapshot, ContextItems, structured output, validation result, latency, and token counts.

Do not store or require hidden chain-of-thought. Store concise decision summaries and referenced state instead.

## Event payloads during development

`payload_version` is recorded but no upcasters exist before v0.1. Reset the database rather
than migrating event payloads; never edit historical payloads in place.

## Error philosophy

When an optional AI subsystem fails, **do less rather than invent state**.

- Narrator failure: show a plain structured result.
- Memory job failure: retain source events and retry later.
- World Author failure: commit nothing partial.

## Testing doctrine

Most automated tests use `FakeModelProvider`. Do not make CI dependent on stochastic external models.

Real-model behavior belongs in optional evaluation suites.

Blocking suites include architectural invariants, knowledge-leakage tests, deterministic replay, Frostbridge integration, and save/reload.

## Leakage debugging rule

If secret information reaches an unauthorized actor, do not begin by changing the prompt.

First identify which retrieval or authorization path exposed it. Fix the application boundary. Prompt hardening may then be added as defense in depth.

## Before modifying architecture

If the written architecture contains a genuine contradiction or prevents implementation:

1. Identify the exact conflicting documents/sections.
2. Explain the conflict.
3. Propose the smallest architectural adjustment.
4. Do not silently choose a new design.
5. Record the decision in documentation before implementing it.

Ordinary implementation inconvenience is not sufficient reason to redesign a foundational boundary.

## Gates that block the next milestone

- Milestone 03: the whisper gate (below).
- Milestone 04b: `HARDWARE-TARGET.md` measured and a go/adjust decision recorded in
  `DECISIONS.md` before Milestone 05 begins.
- Milestone 06d: a 20-turn real-model session from the CLI harness with per-turn metrics, and
  the first playtest rubric filled (`testing/design-iteration.md`).

## Milestone workflow

Work milestone-by-milestone. For each task:

1. Read the relevant architecture/specification sections.
2. Inspect current implementation.
3. Implement the smallest coherent slice.
4. Add required tests.
5. Run those tests.
6. Run relevant invariant/leakage tests.
7. Fix failures.
8. Update task status/documentation.
9. Summarize what changed and any unresolved concern.

Do not opportunistically implement unrelated future features.

## Ticket requirements

Every implementation ticket should identify Goal, Context, Likely files, Requirements, Invariants, Tests, Out of scope, and Acceptance criteria.

If a ticket lacks tests for an important domain behavior, add them as part of the ticket.

## Initial build sequence

Follow approximately:

`Bootstrap → World + Events → Rules Core → Actions/Combat → Perspective → Memory → Model Spike → AI Infrastructure → Intent/Orchestrator → AI Actors → Narration/Governor → CLI Harness → Frostbridge → World Simulation → World Generation → UI → Persistence Stress → Branching → v0.1 Stabilization`

Do not skip the Perspective milestone to get to impressive AI behavior sooner.

## First critical gate

Before AI PCs are considered usable, prove:

- Alex can privately tell Elara something.
- Elara receives it.
- Tomas cannot retrieve it.
- Tomas model context cannot contain it.
- Party reunion does not automatically synchronize it.

If that does not work, stop and fix the perspective architecture.

## First vertical slice

The Frostbridge fixture must eventually demonstrate:

- one human player;
- two independent AI PCs;
- persistent NPCs;
- NPC deception;
- different actor beliefs;
- private communication;
- split-party knowledge;
- a unique persistent item;
- a hidden item property;
- freeform action adjudication;
- programmatic dice;
- theater-of-the-mind combat;
- world-time advancement;
- offscreen consequences;
- durable memory;
- restart/reload;
- debug traceability.

Do not broaden product scope until this works.

## Deferred features

Do not implement unless the active task explicitly requires them:

- voice;
- generated portraits/images;
- native mobile apps;
- real-time multiplayer;
- large map renderer;
- huge content libraries;
- plugin marketplace;
- deep economy;
- continuous autonomous NPC simulation;
- arbitrary executable ruleset plugins.

## Code-quality expectation

Prefer understandable code over clever code. This application will contain difficult state semantics.

Make authority boundaries obvious in module names, types, method names, and tests.

A future maintainer should be able to answer, “Is this objective truth or one actor's perspective?” by looking at which service/repository is being used.

## Final implementation goal

The completed v0.1 should make this statement true:

> A human can play a persistent tabletop campaign with independent AI-controlled companions and NPCs. The game engine—not the language model—owns truth, mechanics, randomness, state, and history. Every actor knows only what that actor is entitled to know, while durable memory and targeted retrieval allow campaigns to continue for many sessions without relying on one ever-growing conversation.

Protect that property above all else.
