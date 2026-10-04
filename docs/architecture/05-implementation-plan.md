# Persistent AI TTRPG Engine — Repository Implementation Plan v0.2

## 1. Purpose

This document turns the architecture into an incremental engineering plan suitable for an IDE coding agent.

The coding agent should not redesign foundational boundaries while implementing them. When details are ambiguous:

1. preserve architectural invariants;
2. choose the simplest implementation satisfying the current milestone;
3. avoid speculative future systems;
4. leave extension points only where already anticipated;
5. write tests around every important authority boundary.

## 2. Recommended monorepo

```text
ai-ttrpg/
├── README.md
├── .env.example
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── package.json
├── docs/
├── backend/
│   ├── migrations/
│   ├── app/
│   │   ├── api/
│   │   ├── domain/
│   │   ├── engine/
│   │   ├── ai/
│   │   ├── worldgen/
│   │   ├── persistence/
│   │   ├── services/
│   │   ├── workers/
│   │   └── tests/
│   └── rulesets/core_adventure/
├── frontend/
└── scripts/
```

Suggested backend domains: campaign, timeline, entity, actor, faction, party, location, scene, events, knowledge, memory, relationships, goals, items, mysteries, time, and rules.

Suggested engine modules: dice, expressions, actions, effects, modifiers, checks, combat, triggers, simulation.

Suggested AI modules: providers, routing, roles, context, contracts, prompts, validators, orchestration.

## 3. Initial stack

Backend baseline:

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- Alembic
- PostgreSQL
- pgvector
- httpx
- pytest

Frontend:

- current supported Node 20+
- Next.js
- React
- TypeScript

Backend remains independently runnable.

## 4. Environment configuration

Initial `.env.example` should include database URL, app/debug mode, local LLM base URL/key/model profiles, embedding endpoint/model, cloud fallback toggle, optional cloud credentials, concurrency caps, and default ruleset.

Provider credentials are not required for deterministic development/tests.

## 5. Database strategy

Use UUID primary keys; JSONB for intentionally extensible ruleset-dependent structures; normalized columns/foreign keys for identity, ownership, authorization-relevant links, timeline references, events, and relationships.

Do not place an entire campaign inside one JSON document.

## 6. Migration order

Recommended dependency order:

1. campaign/timeline/world clock;
2. entity/location/topology;
3. actors/controllers/factions/parties;
4. scenes/events/transcripts/scheduled events;
5. rules actions/rolls;
6. resources/conditions/items/documents;
7. facts/claims/observations/beliefs/identity knowledge;
8. memories/relationships/emotions/goals/plans;
9. mysteries/clues;
10. rules metadata/generated definitions/precedent;
11. ModelRun/ContextSnapshot/DecisionTrace;
12. generation/background jobs;
13. journal/encyclopedia projections.

## 7. Event ordering and transactions

Each timeline receives deterministic sequence numbers independent of fictional time. Timeline row allocation should reserve event sequence ranges atomically.

Projection mutation and event creation occur in one database transaction. Application services should not casually mutate projections outside the event transaction boundary.

Campaign/world versions and scene versions support optimistic revalidation of AI proposals.

## 8. Repository/service split

Repositories perform persistence/retrieval and do not contain game rules. Services coordinate domain behavior. Engine modules implement mechanics.

Use Pydantic/domain schemas for API requests/responses, AI contracts, rules definitions, and domain commands; do not expose raw SQLAlchemy models directly.

## 9. Rules implementation sequence

Build the definition registry early, then safe expression evaluator, dice engine, attributes/resources/checks/modifiers/effects, followed by action state machine, conditions/triggers, theater-of-the-mind positioning, encounters/initiative, items/abilities/creatures/character creation/advancement, and finally generated mechanics/rulings/precedents.

Core Adventure content lives in ruleset data rather than generic engine logic.

## 10. Perspective implementation gate

Before any serious AI companion work, implement Fact/Claim/Observation/Belief/IdentityKnowledge, audibility/visibility/language mechanics, and `PerspectiveService`.

Blocking tests must prove that an actor cannot retrieve unknown objective facts, another actor's private belief, hidden item property, private whisper, unknown identity, or unobserved event.

## 11. Memory implementation

First implement durable memory records, source provenance, core memory, embeddings, and retrieval. Sophisticated forgetting/compression comes after retrieval quality works.

Authorization filters are applied before vector similarity ranking.

## 12. AI provider infrastructure

Define a provider protocol before prompts. Implement `FakeModelProvider` and local OpenAI-compatible provider first. Cloud adapters come later.

Model routing uses logical profiles rather than hardcoded model names.

Store ModelRun and ContextSnapshot before serious model experimentation so failures can be audited from the beginning.

## 13. Prompt repository

Prompts are versioned files grouped by role. Each prompt declares role, authority, expected schema, and restrictions. State-affecting outputs are always structured and validated.

## 14. SessionOrchestrator

Central service `process_player_input` should roughly:

1. store raw player message;
2. resolve/infer channel;
3. compile intent context;
4. parse intent;
5. resolve entity references;
6. create actions;
7. resolve deterministic mechanics;
8. invoke Rules Adjudicator only if needed;
9. commit authoritative events;
10. propagate observations;
11. calculate eligible reactions;
12. schedule/execute AI actor calls;
13. validate and resolve resulting intents;
14. build NarrativeBundle;
15. call Narrator;
16. extract incidental canon when needed;
17. queue memory processing;
18. update journal/encyclopedia projections;
19. return player response.

Do not bury orchestration inside API route handlers. Steps 2–4 also produce `conveys[]`, `asserted_facts[]` and a conversation time band; step 9 includes player-assertion handling; every step is timed into `turn_metrics` and may be dropped per the degradation ladder.

## 15. Spotlight governor v1

Initial configurable defaults can be simple: at most 3 consecutive visible AI actor turns, 1 incidental AI-to-AI exchange, and 2 unsolicited initiatives per player turn, with explicit overrides for combat/critical danger. Player interruption always has priority.

## 16. Background worker

Start with a PostgreSQL-backed queue using row locks (`FOR UPDATE SKIP LOCKED`) rather than Redis.

Initial jobs: memory.embedding, memory.process, journal.update, simulation.advance, world.materialize. Jobs have priority, attempt count, max attempts, not-before time, last error, and status.

Optional job failure must not invalidate authoritative campaign state.

## 17. World simulation v1

Do not build deep economics. Implement scheduled events, faction plan clocks, important NPC travel, and simple offscreen goal progression. LLM simulation is reserved for meaningful ambiguous strategy.

## 18. Campaign generation APIs/state machine

Generation stages should be separately tracked/rerunnable before campaign start. A campaign can progress from DRAFT → BRIEF_READY → PREMISE/WORLD/REGION/PARTY/OPENING readiness → PLAYABLE.

## 19. Initial API surface

Core endpoints cover health, campaigns, generation, characters/sheets/inventory, current scene, `/play`, party, journal, encyclopedia, rules lookup, provider status, and explicit debug APIs for state/events/facts/perspectives/model runs/context/resolution/time/controller/branch/retcon.

Normal endpoints are actor-perspective-safe. Debug endpoints are omniscient only when debug mode is enabled.

## 20. Frontend v1

A practical desktop layout has navigation/party left, narrative/action feed center, character state right. Primary views: Play, Character, Party, Journal, Encyclopedia, World, Settings, Debug.

The Debug drawer should expose events, rolls, intent, rule resolution, observations, beliefs, model calls/context, memory updates, clocks, and mysteries.

Frontend never infers mechanical truth by parsing prose.

## 21. Frostbridge seed

`make seed-demo` creates deterministic Core Adventure campaign data including human placeholder, Elara, Tomas, Mira, Renn, Oric, Frostbridge locations, locked mystery, clues, relationships, items, scheduled events, and opening scene.

This fixture is the primary development target until procedural generation is trustworthy.

## 22. Developer commands

Recommended Makefile targets:

- `make dev`
- `make api`
- `make web`
- `make worker`
- `make test`
- `make test-unit`
- `make test-integration`
- `make test-invariants`
- `make test-leakage`
- `make seed-demo`
- `make reset-db`
- `make migrate`

## 23. Milestone order

1. Bootstrap
2. Event-sourced world
3. Rules core (02a)
4. Actions/positioning/combat (02b)
5. Perspective engine (with deterministic Claim/belief rules)
6. Memory
7. **Model capability spike (04b) — gate**
8. Model infrastructure
9. Intent, orchestrator, player canon, telemetry, streaming (06a)
10. AI PCs/NPCs with `conveys[]` (06b)
11. Narration, spotlight governor, memory processing (06c)
12. **CLI play harness (06d) — first playable; playtest loop starts**
13. Frostbridge fixture
14. World simulation
15. Campaign generator
16. Player/debug UI
17. Persistence/stress (with latency gates)
18. Branching
19. v0.1 stabilization

`/tasks` holds one file per entry with a `## Read` context pack listing the sections that
matter for that milestone. Read `GLOSSARY.md` and `PROMPT.md` once; then read per ticket.

## 24. Key checkpoints

After deterministic rules: the project should be a functioning tabletop engine without AI.

After the model spike: `HARDWARE-TARGET.md` has measured numbers and a recorded decision; schemas may have been simplified. This is a blocking gate for AI infrastructure.

After the CLI harness: a developer can play 20 turns against the real model from a terminal with per-turn metrics; the first playtest rubric is filled.

After perspective: actors can know different things, whispers work, facts differ from beliefs, and hidden truth remains hidden. This is a blocking checkpoint.

After AI gameplay: natural human input, AI companions, and NPCs interact through the deterministic engine while contexts remain isolated.

After worldgen: a newly generated non-Frostbridge campaign can begin play.

## 25. Test strategy

Every milestone ships unit, integration, and invariant tests as appropriate. Critical systems additionally require leakage, replay, and stress tests.

Most CI tests use FakeModelProvider. Real model evaluation is an optional suite.

## 26. Implementation ticket format

Every ticket should include Goal, Context, likely files, Requirements, Invariants, Tests required, Out of scope, and Acceptance criteria.

Prefer focused tickets (“implement whisper propagation + leakage test”) over broad tasks (“build knowledge system”).

## 27. Coding-agent standing instruction

The agent should read relevant architecture/spec documents before each substantial task, inspect existing code/tests, implement the smallest coherent slice, add/run tests, update status, and document unresolved architectural concerns rather than silently redesigning.

## 28. Deferred work

Do not spend v0.1 effort on voice, image generation, native mobile clients, real-time multiplayer, elaborate tactical maps, giant content libraries, marketplace/plugins, arbitrary executable rules, or deep continuous economics.

## 29. Definition of v0.1 success

A human can create/load a campaign, play via natural language with two independent AI companions and persistent NPCs, use deterministic mechanics/dice, maintain asymmetric knowledge and durable memory, see the world advance offscreen, restart the server, and continue with state and perspective intact—without depending on one ever-growing model conversation.

## 30. Event payload versioning stance

`payload_version` exists from migration 0004, but **no upcasters are written before v0.1
ships**. Development campaigns are disposable; `make reset-db` is the migration path, and
replay fixtures are regenerated at the current version. The day a campaign is declared
non-disposable, upcasters become a required part of every payload change. This is recorded in
`DECISIONS.md` so the coding agent does not build migration machinery prematurely or, worse,
mutate historical payloads in place.

## 31. Context packs

The full bundle is roughly 50k tokens. The coding agent should not reread it per ticket. Each
milestone file's `## Read` section is the authoritative context pack; `GLOSSARY.md` resolves
terms. If a ticket needs a section not listed, add it to the milestone file as part of the
ticket.
