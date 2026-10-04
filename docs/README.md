# Persistent AI TTRPG Engine — Planning Bundle v0.2

This directory is the implementation handoff for a local-first, persistent AI-powered tabletop RPG engine.

The project is **not** an AI chatbot pretending to run a campaign. It is a persistent simulation engine in which the application owns objective truth, rules, randomization, world state, durable memory, and information boundaries, while LLMs provide interpretation, roleplay, actor decisions, world authoring, adjudication proposals, and narration.

## Core doctrine

- **Program controls truth. LLM controls narration, interpretation, improvisation, and planning within permissions.**
- **LLM proposes intent. Engine resolves consequence.**
- **Perspective is a security boundary.** An AI-controlled actor never receives omniscient state and is not merely told to ignore it.
- **Memory is not context.** Long-running campaigns are stored as structured state, events, actor perspectives, memories, and summaries; each model call receives a bounded, purpose-built context package.
- **All randomness comes from the engine.**
- **Important state changes are event-sourced and auditable.**
- **Established canon does not silently change.**
- **Mystery truths lock before clues are generated.**
- **Human and AI PCs share the same mechanical representation.** Controller identity is runtime state, not character identity.
- **Speech carries structured information content.** Utterances produce Claims with `conveys[]`; beliefs follow deterministic rules.
- **Every turn is budgeted and measured.** Call caps, latency targets, degradation ladder, telemetry from the first orchestrator commit.
- **The human is also a perspective.** One focus actor; offscreen scenes hidden; focus switches transfer no knowledge.

## Recommended reading order

1. `GLOSSARY.md`
2. `architecture/01-world-memory.md`
3. `architecture/02-rules-engine.md`
4. `architecture/03-ai-orchestration.md`
5. `architecture/04-campaign-generation.md`
6. `architecture/05-implementation-plan.md`
7. `specifications/communication-and-knowledge.md` — how speech becomes knowledge (new)
8. `specifications/belief-update-rules.md` — deterministic belief defaults (new)
9. `specifications/turn-budget-and-latency.md` — budgets, streaming, telemetry (new)
10. `specifications/database-schema.md`
11. `specifications/api-contracts.md`
12. `specifications/ai-contracts.md`
13. `specifications/core-adventure-rules.md`
14. `specifications/frostbridge-demo.md`
15. `specifications/human-visibility.md`, `specifications/time-accounting.md`, `specifications/player-authored-canon.md`, `specifications/observation-authoring.md`, `specifications/canon-extraction-allowlist.md` (new; pulled in by the milestones that need them)
16. `testing/testing-strategy.md`
17. `testing/knowledge-leakage.md`
18. `testing/vertical-slice.md`
19. `testing/design-iteration.md` (new)
20. `HARDWARE-TARGET.md` (fill in at Milestone 04b)
21. `tasks/` milestone files (each with a `## Read` context pack)
22. `PROMPT.md`
23. `CHANGELOG-v0.2.md` — what changed from v0.1 and why

## Initial technology target

- Backend: Python 3.12+, FastAPI, SQLAlchemy 2.x, Pydantic 2.x, Alembic
- Database: PostgreSQL + pgvector
- Frontend: Next.js / React / TypeScript
- AI: provider-neutral model abstraction; local OpenAI-compatible endpoint first
- Deployment: Ubuntu local AI server, browser UI, reachable over Tailscale
- Background work: database-backed Python worker first; no Redis requirement for v0.1

## v0.1 vertical slice

The first release is successful when a human can:

- create or load a campaign;
- play alongside two independent AI-controlled PCs;
- interact with persistent NPCs;
- use natural-language actions that are mechanically interpreted and resolved;
- make programmatic checks and dice rolls;
- have private conversations and split the party without knowledge leakage;
- encounter NPC deception and conflicting beliefs;
- acquire a unique persistent item with hidden properties;
- fight a small theater-of-the-mind encounter;
- advance world time and see offscreen consequences;
- stop and restart the application without losing world state, actor memory, beliefs, relationships, or hidden information;
- inspect a development/debug trace explaining why the engine and AI behaved as they did.

## First deterministic demo

`Frostbridge` is the reference fixture used before procedural world generation becomes authoritative. It contains a fixed murder/smuggling mystery, actors with asymmetric knowledge, AI companion disagreement, persistent clues, a hidden-property item, world clocks, and a small combat encounter.

## Implementation order

The intended sequence is:

1. Bootstrap
2. World + event ledger
3. Rules core, then actions/combat
4. Perspective/knowledge isolation (with deterministic Claim/belief rules)
5. Memory
6. **Model capability spike (gate)**
7. AI infrastructure
8. Intent/orchestrator → AI actors → narration/governor
9. **CLI play harness (first playable; playtest loop begins)**
10. Frostbridge fixture
11. World simulation
12. Procedural campaign generation
13. Player/debug UI
14. Persistence and stress testing (with latency gates)
15. Branching
16. v0.1 stabilization

Do **not** rush AI roleplay ahead of the perspective and event architecture. The most important early proof is that Alex can privately tell Elara something and Tomas is technically unable to retrieve it. The second most important early proof is that the configured local model can actually produce the structured outputs the architecture assumes, at the latencies the budgets assume — hence the spike before AI infrastructure.

## Deferred scope

Do not treat these as v0.1 requirements:

- voice;
- generated artwork or portraits;
- native mobile apps;
- real-time multiplayer;
- elaborate grid/map rendering;
- huge spell/monster/item catalogs;
- plugin marketplace;
- arbitrary executable community rules;
- deep economy simulation;
- continuous autonomous NPC loops.

## Using this bundle in a coding repo

Copy this directory into the target repository (or merge its contents into a `/docs` planning area), then give the IDE coding agent `PROMPT.md` as its standing implementation instruction. Work milestone-by-milestone and keep the architecture documents authoritative.
