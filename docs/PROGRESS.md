# Progress report — 2026-10-04

Where the AI TTRPG engine stands against the v0.2 plan (`tasks/README.md`), what is proven, and
what remains before v0.1. Milestone status detail lives in each `tasks/milestone-*.md`;
architectural decisions in `DECISIONS.md`.

## At a glance

| # | Milestone | Status |
|---|---|---|
| 00 | Bootstrap (FastAPI, Postgres+pgvector, Alembic, settings, health) | Done |
| 01 | World + Events (entities, locations, actors, scenes, append-only ledger, world clock) | Done |
| 02a | Rules core (Core Adventure ruleset, checks, dice, stats, effects primitives) | Done |
| 02b | Actions + combat (theater-of-the-mind positioning, initiative, reactions, replay) | Done |
| 03 | Perspective (Facts vs Beliefs/Claims/Observations, PerspectiveService, whisper gate) | Done |
| 04 | Memory (subjective memories, lineage, embeddings + rerank retrieval) | Done |
| 04b | Model capability spike (GLM-4.5-Air on A9; go/adjust decided) | Done |
| 05 | AI infrastructure (roles, prompts, Context Compiler, ModelRunner, A9 adapter, audit) | Done |
| 06a | Intent + orchestrator (interpreter, resolution, clarifications, assertions, budgets) | Done |
| 06b | AI actors (AI PCs and NPCs, `conveys[]` authorization, deception, fallback policies) | Done |
| 06c | Narration + governor + memory processing (narrator stream, spotlight, checkpoints, journal) | Done |
| 06d | CLI play harness (HTTP-only terminal client; first live A9 sessions) | Done |
| 07 | Frostbridge fixture (full world, mysteries/clues, documents, travel, deterministic slice) | Done |
| 08 | World simulation (scheduled events, plan clocks, World Simulator, background worker) | Done |
| 09 | Campaign generation (staged World Author, imports, guided creation, genre modules; runs on A9) | Done |
| 10 | Player UI (browser client: desktop + phone, dev visibility toggle, Frostbridge playable) | Done |
| 11 | Persistence stress (long campaigns, bounded context, ANN revisit) | Not started |
| 12 | Branching (timelines from an event) | Not started |
| 13 | Polish / v0.1 release | Not started |

Full backend suite: 379 passing tests (FakeModelProvider + real `ttrpg_test` database), about
6 minutes, with 6 opt-in real-model evals skipped. Browser client: 10 Vitest and 15 Playwright
tests (`make web-test`, `make e2e`).

## What is proven (by tests you can run with `make test`)

**Authority boundaries.** The engine owns truth: every projection mutation commits with an Event
in the same transaction (`tests/invariants`); perspective reads never select `truth_status`,
`deliberate_false` or `hidden_properties`; AI actor context goes only through
`PerspectiveService`/`ContextCompiler`, with an audit snapshot per call.

**Knowledge isolation (the first critical gate).** Alex whispers to Elara; Elara stores exactly
the belief rows the spec predicts (`known 1.0` that Alex asserted it, `suspected 0.585`); Tomas
has no observation, no belief, nothing in context, nothing retrievable; reunion synchronises
nothing. AI output that references a fact outside the speaker's perspective is rejected with a
`proposal.rejected_leakage` event, Claim and all.

**The whole vertical slice (frostbridge-demo §43)** runs deterministically with the fake model:
gate notice → tavern → Mira's evasion and partial reveal → whisper → companion disagreement →
split party (live warehouse / offscreen guard house, one bounded call) → ledger, mud and dagger
(hidden property stays hidden in inventory and context) → two-thief combat with an improvised,
persistent shelf topple → reunion with knowledge still asymmetric → exchange → Renn's recorded
lie → scene-end memory checkpoint → four days of clocks → restart from a fresh engine → one
more turn. Every turn has `turn_metrics`; no non-Renn context snapshot ever contains the murder.

**World that moves without the party.** Six days away: plan clocks assemble the cargo and load
the barge, Renn walks to the dock by scheduled travel, the World Simulator is asked once whether
the barge departs, the quarry escalates on Day +8 with no call; detaining Renn cancels all of it
by prerequisite revalidation before any model is consulted. Every run is a `simulation.run`
event with interval, candidates and budget.

**Played by a human, then fixed against the real model.** The first browser session's lines
replay on A9 (`docs/spikes/play-session-2026-10-05.md`):
- no failed turns;
- the merchant comes alive on the second exchange and remembers it;
- checks pause for a click-to-roll with real skills and stakes;
- OOC answers from the character's perspective;
- every model call shows live in dev view.

**Playable in the browser, on desktop and phone.** The whole Frostbridge scenario plays through
the UI in a Playwright test. A developer can flip the DEV switch mid-play and expand any turn
into its actions, rolls (hidden ones marked), events and model calls with their context.
Normal views never show hidden data (`tests/integration/test_player_api.py`, `frontend/e2e`).

**A world generated by the real model.** The full 18-stage pipeline completes on GLM-4.5-Air
and the world it builds passes the quality checks and starts
(`docs/spikes/worldgen-a9-2026-10-04.md`). The heavy stages are written one item at a time.
A bad item retries alone, good items are kept, and a failed run resumes where it stopped. Imports, guided creation and genre modules feed the
same pipeline.

**A brand-new world, generated and playable.** Eighteen World Author stages (FakeModel in CI) produce validated envelopes for a campaign that is not Frostbridge; rerolling a stage invalidates exactly its dependents; a contradiction of established canon or the locked mystery truth is rejected and corrected within one retry; `start` builds the world in one unit of work and refuses (rolling everything back) a world that fails the quality checks; the player then plays the opening scene through the ordinary orchestrator. Outline places materialize on demand against established canon.

**Play at the terminal against the real model.** `make play ARGS="--new"` seeds the full
Frostbridge world and plays it over HTTP; three live GLM sessions measured ~36–38 s social
turns (interpreter ≈10 s is the fixed cost) and produced the fixes logged in milestone 06d.

## What is built, by layer

- **Persistence (15 migrations, 64 tables):** campaigns/timelines/clock; entities, locations,
  edges; actors, controllers, factions, parties; scenes/participants; events + event_entities;
  transcripts; scheduled_events; rules metadata, rolls, intents/actions/steps/traces, pending
  clarifications; resources, conditions, items (+concealment), item history, documents; facts,
  claims, observations, beliefs, identity knowledge, relationships (+deltas); memories (+sources,
  1024-d vectors); emotions, goals, plans, AI profiles; mysteries, truth facts, clues, clue
  discoveries; model runs, context snapshots/items, decision traces, turn metrics; journal and
  encyclopedia projections; background jobs; generation runs and stages.
- **Rules engine:** declarative Core Adventure ruleset (attributes, skills, checks, conditions,
  equipment, actions); dice service with seeded, replayable rolls; registered effect primitives
  (including `alter_feature` for persistent environmental consequences); positioning bands,
  cover, encounters, initiative, reactions, fallback-policy tactics.
- **Services (objective vs. perspective made explicit):** World, Scenes (travel, join/merge,
  live vs offscreen clocks), Actions, Speech (`conveys[]` → Claims → Beliefs, naming by
  communication, testimony clue discovery), Knowledge, Documents, Mystery, Schedule, Simulation,
  Psychology (goals, emotions, relationships, plans), Memory + MemoryProcessing (checkpoints,
  journal, encyclopedia), Narration (+ canon extractor, allowlist), PlayerCanon, Perspective,
  Observations (template-generated, never model-written), Turns (budgets, ladder, metrics),
  Jobs + worker.
- **AI layer:** 13 roles with versioned prompts and Pydantic output schemas; Context Compiler
  (authorization before retrieval, stable-prefix layout for caching, token fit, audit);
  ModelRunner (bounded repair, concurrency, audit rows); A9 adapter that defeats provider-side
  memory/persona/tool-dropping; FakeModelProvider for CI; A9 embeddings + rerank.
- **Campaign generation (`app/worldgen/`):** CampaignBrief and Surprise Me, the 18-stage
  pipeline, validation, the world builder, quality checks, progressive materialization.
- **API:** `/play` (SSE: accepted → mechanics → speakers → narration deltas → complete →
  result), perspective endpoints (scene, inventory, beliefs, journal, encyclopedia), debug
  endpoints (seed, actors, events, perspective/compare, model-run context, metrics, scene end,
  advance-time with simulation, jobs); generation (create campaign, brief, runs, regenerate,
  preview, start).
- **Browser client (`frontend/`, Milestone 10):** Vite + React + TypeScript.
  - Views: Play (streamed mechanics, then speaker-labelled lines, then narration),
    Character, Party, Journal, Encyclopedia, World, Settings and Debug.
  - Layouts for desktop, tablet and phone.
  - A per-browser DEV switch (only with `DEBUG_MODE`) adds per-turn traces and the
    omniscient Debug view; developer material is shown in violet.
  - New API: campaign list and detail, player settings, the focus actor's sheet, the party
    as perceived, and the debug turn trace. FastAPI serves the built client.
- **Tooling:** `make db-up/migrate/reset-db/api/test*/seed-demo/play/worker/eval-local`,
  `make web/web-install/web-build/web-test/e2e`; offline seed CLI; terminal harness with
  `/debug` subcommands.

## Gates

- Whisper gate (03): passed and re-asserted by the slice.
- 04b spike: decided "proceed with adjustments" on GLM-4.5-Air; numbers in `HARDWARE-TARGET.md`.
- 06d: 20-turn real-model session and first playtest rubric — three live sessions were run and
  measured; a formal 20-turn rubric fill is still owed (`testing/design-iteration.md`).

## What is left

**Milestone 11 — Persistence stress.** Long synthetic campaigns; prove bounded context (a
500-session campaign needs no 500-session prompt), memory compression at scale, retrieval
quality; revisit the "no ANN index" decision (per-actor partitioning or iterative index scans).

**Milestone 12 — Branching.** Create a timeline from an event, rebuild projections for the
branch, switch active timeline, continue independently, mechanical replay.

**Milestone 13 — v0.1 polish.** Three consecutive playtest sessions meeting the design-iteration
exit criteria; latency work against the real model; release packaging.

**Carried backlog (recorded in `DECISIONS.md`):**
- From the real-model runs (`docs/spikes/frostbridge-a9-2026-10-04.md`,
  `docs/spikes/play-session-2026-10-05.md`):
  - The median turn takes about 34 s; the worst turns take 70–130 s (claim extraction in
    sequence, and interpreter repairs).
  - GLM sometimes omits the spoken `utterance`.
  - Game-master pacing (a director nudge) is deferred until after these fixes.
  - Narration occasionally misplaces known things.
  - The interpreter sometimes takes a request to a companion as the player's own action.
- Browser client: unnamed places show as "Somewhere unfamiliar" (no public descriptor in the
  scene view). The 20-turn playtest rubric is now unblocked.
- Intent Interpreter cost (~10 s/turn): shorter prompt or a small co-resident model for
  `fast_structured` roles — a question for the A9 host.
- Section 4 catch-up for NPC scenes uses plan clocks and scheduled events; "plan step completes
  within delta" as a trigger for an offscreen AI *player* call is approximated by "an AI party
  member is present".
- Generation on GLM takes ≈ 2 h with itemized stages; a per-call canon filter now shows only
  related facts (09d), and its effect on A9 run time is not yet measured. Guided creation rarely declares
  itself done (the 8-answer bound ends it).
- `grant_capability` tags on generated items are not yet interpreted by any rule.
- YAML seed directory (frostbridge §40) not adopted; the seed is declarative Python.
- A9's two-model residency (`local-general` only); `npc_tactical` registered but unused.
