# Persistent AI TTRPG Engine — AI Orchestration Architecture v0.2

## 1. Purpose

The orchestration layer decides whether an LLM call is necessary, which specialized role should make it, which model/provider should handle it, what information the role may receive, what structured output it must return, when calls can run concurrently, how results are validated, and how many calls a single player turn is permitted to trigger.

> **No model receives “the campaign.” Every model receives a purpose-built, least-privilege context package for one specific task.**

> **A turn has a time budget and a call budget before it has a prompt.** Budgets, the degradation ladder, streaming and telemetry are defined in `../specifications/turn-budget-and-latency.md` and apply from the first orchestrator commit.

## 2. Core turn architecture

A typical path is:

`player input → deterministic preprocessing → intent interpretation if needed → action/rules engine → authoritative events → observation propagation → eligible actor reactions → validated AI proposals → more events → narrative bundle → narrator → player`

Background work includes memory extraction/compression, embeddings, journal/encyclopedia projection, world simulation, and latent materialization.

The orchestrator owns call order. Individual model roles do not recursively invoke one another.

## 3. Initial role registry

Roles include:

- intent_interpreter
- entity_resolver_assist
- rules_adjudicator
- ai_player
- npc_actor
- npc_tactical_controller
- narrator
- world_author
- world_simulator
- memory_processor
- belief_processor
- canon_extractor
- journal_writer
- rules_content_designer/importer
- claim_extractor (fallback; `../specifications/communication-and-knowledge.md` §5)

Each role defines allowed/forbidden context types, allowed tools, output schema, default model profile, temperature, context/output budgets, and authority to propose state/canon.

## 4. Least privilege applies to DM roles too

Even a narrator does not need the entire objective world. A cellar description requires the cellar, visible entities, player-facing observations, resolved events, and style guidance—not unrelated royal secrets or future villain plans.

Reducing irrelevant omniscient context lowers leakage risk, token use, accidental foreshadowing, and attention dilution.

## 5. Model profiles and routing

Roles refer to logical profiles rather than provider-specific names:

- `fast_structured`
- `balanced_reasoning`
- `creative_narrative`
- `deep_world_author`
- `embedding`

Routing considers role, importance, complexity, latency target, available hardware, context size, structured-output reliability, and campaign preference.

Minor bartender reactions can use a small local model; major villain negotiations or campaign creation can escalate to stronger configured models.

Provider modes can include `local_only`, `local_preferred`, `best_available`, and `cloud_only`. A local-only campaign never sends content externally.

## 6. Provider abstraction

Define a provider-neutral interface such as `generate(model_profile, messages, output_schema, tools, parameters)` with local OpenAI-compatible and future cloud adapters.

Campaign state must never contain provider conversation IDs or depend on provider-side memory.

## 7. Structured output

Any model role that can influence persistent state returns structured output. Freeform prose is primarily for narration, dialogue, descriptive documents, and flavor.

Every state-relevant response passes schema/reference/authorization/authority/world-version validation.

## 8. AI actor contracts

AI actor output contains concise decision summary, belief/emotion/goal proposals, action intentions, optional spoken text **with its structured information content (`conveys[]`)**, and fallbacks. It does not contain unrestricted hidden reasoning traces. Every `conveys` reference is authorization-checked against the speaker's perspective before a Claim is stored.

The model expresses what the actor wants. The engine determines whether it happens.

## 9. Intent interpretation

Deterministic syntax handles explicit OOC/private/whisper commands when possible. Otherwise Intent Interpreter receives player text, visible scene, known entities, capabilities, and recent conversation and returns channel, targets, ordered intents, ambiguities, and confidence.

Clarification occurs only when ambiguity materially changes consequences. The campaign setting controls how readily the DM makes reasonable assumptions versus asking.

## 10. Entity resolution

Use deterministic exact/alias/recent-reference/unique-visible matches first. If a model assists, it receives only entities the requesting actor could plausibly refer to.

An actor cannot resolve “the murderer” to an unknown secret actor merely because objective state knows the culprit.

Ambiguity is detected by the engine, not the model (04b spike: 0/50 clarification requests for
“Attack him” with two hostile candidates). When the input's target expression is a pronoun or a
bare descriptor and more than one perspective-visible candidate matches its class, and the
model's chosen target is not named in the text, the orchestrator raises the clarification
itself (`api-contracts.md` §10) regardless of the Intent Interpreter's `requires_clarification`.

## 11. Skip unnecessary model calls

The orchestrator aggressively avoids inference when deterministic state suffices. Opening an adjacent unlocked untrapped door might need only narration; it should not require six model calls.

Complex improvisation, AI companion reactions, NPC deception, or ambiguous rules warrant more calls.

## 12. Reaction eligibility and significance

Not every actor in a scene receives a model call after every event. Eligibility can require direct address, threat, goal/relationship impact, meaningful new information, reaction mechanics, strong emotion, or combat turn.

Eligible reactions receive significance scores using direct-target, danger, goal relevance, relationship relevance, novelty, emotional weight, scene importance, and actor importance.

Low significance can update silently; medium may adjust internal state; high may produce visible action/dialogue.

## 13. Spotlight governor

Track AI actions since human input, AI spoken turns, AI-to-AI exchanges, unsolicited initiatives, and narrative size.

Example defaults:

- max consecutive visible AI actor turns: 3;
- max incidental AI-to-AI exchanges: 1;
- max unsolicited AI initiatives per player turn: 2;
- player interruption always has priority.

If AI interaction remains relevant after the visible budget, compress it into narration rather than rendering an endless transcript.

## 14. Meaningful proactive AI behavior

Companions can initiate actions when triggered by urgent goals, strong emotion, relationship milestones, private plans, important observations, or scheduled personal activity.

Example: reaching the town where Elara has a brother lead may cause her to insist on visiting the harbor office before unrelated sightseeing.

## 15. Background activity

Incidental NPC chatter should generally be simulated/statistically summarized rather than model-generated. Background events can still affect familiarity or schedules when meaningful.

## 16. Private AI actions

AI actors may perform actions unknown to the human player. These resolve through the same engine and are revealed only if observed, reported, confessed, or evidenced.

Debug mode sees all of them.

## 17. Plans between scenes

Actors can hold short-term intention, current plan, and long-term goal. Meaningful transitions activate plan checks rather than continuously running agents.

## 18. Concurrency and snapshots

Independent inference calls can run concurrently. Example: several AI PCs can decide actions from the same scene snapshot. Mechanical execution still follows initiative or scene rules.

On the local hardware target, concurrent calls to one resident model serialize or batch; the DAG stays correct but wall time does not shrink. The orchestrator therefore groups calls by model profile within a turn and relies on the spotlight governor and fallback policies, not parallelism, to meet the turn budget (`../specifications/turn-budget-and-latency.md` §2, §5).

Each proposal records the world/scene version it was based on. Before commit, revalidate against current state. If another actor has already taken the target item or killed the target, invalidate or use a defined fallback.

## 19. Decision fallbacks

Combat decisions can include fallback policies such as “if target unavailable, attack nearest hostile; if none reachable, take cover.” This reduces repeated inference after ordinary initiative changes.

## 20. Tactical controller

Roleplay intent and tactical implementation may be separated. An AI PC may decide “protect Alex and keep distance”; a tactical controller chooses a legal move/action matching that intent.

Tactical competence varies independently of general intelligence/personality.

## 21. Narration

The narrator receives the focus actor's rendered observations and heard dialogue (`../specifications/observation-authoring.md` §5, `../specifications/human-visibility.md` §6) plus resolved mechanics visible to that actor and style; narration is streamed. It may choose sensory detail, phrasing, and modest harmless flavor, but cannot change mechanical outcomes, kill survivors, grant items, reveal hidden facts, teleport entities, or silently change relationships.

Narration should be batched around meaningful event bundles rather than emitted for every tiny internal event.

## 22. Canon extraction

A cheap post-narration pass can detect incidental persistent details not prestructured. It must distinguish concrete fact from metaphor, speculation, NPC claim, or subjective impression. What it may persist is bounded structurally by `../specifications/canon-extraction-allowlist.md`: decoration only; never mechanics, topology, history, secrets or relationships.

Important objects/locations/secrets should be structured before narration; post-extraction is primarily for lightweight incidental detail.

## 23. Memory pipeline

Memory processing is triggered by scene end, important event, relationship/goal event, major discovery, combat conclusion, rest/downtime, or session checkpoint—not every sentence.

Pipeline:

`event → authorized observation → belief processing → emotional interpretation → memory candidate → persistent memory`

Memory processors receive only actor-perceived information.

## 24. Belief processing

Observations and Claims become beliefs by the deterministic rules in `../specifications/belief-update-rules.md`. A model is consulted only under that document's §7 gating (important actor, goal-relevant or contradicting, near a type boundary), receives the deterministic result as the default, and returns bounded adjustment proposals only.

Actors can also form new inferences during downtime from previously known evidence; such results are stored as inferred beliefs, not objective truth.

## 25. World simulation orchestration

Time advancement first processes scheduled events and deterministic systems (resource changes, travel, recovery, weather tables, clocks), then identifies significant decision candidates for a bounded World Simulator call.

The simulator receives only relevant candidate actors/factions, goals/plans, state, elapsed interval, and event budget.

## 26. Simulation attention budget

Campaign settings can cap significant offscreen decisions per day/week and define world scope/depth. Far-away systems remain statistical until thresholds or relevance justify deeper materialization.

## 27. World Author

World Author receives campaign themes, genre modules, established canon, relevant latent canon, current generation need, nearby entities, and ruleset capabilities. It returns structured proposals for entities, facts, locations, relationships, goals, secrets, mysteries, and mechanical definitions.

Before commit, run schema/reference validation, established-canon comparison, rules compatibility, timeline consistency, and duplicate/entity matching.

Latent material may be revised with audit history; established material cannot silently change.

## 28. Staged generation

Campaign creation proceeds stage-by-stage so a failure or reroll of a starting settlement does not require regenerating cosmology. Before play, individual latent stages can be regenerated and dependent stages revalidated.

## 29. Narration style and recent history

Narration style is a separate profile (perspective, verbosity, dialogue style, description density, humor, combat style, mechanics visibility). Genre does not hardcode prose style.

Narrator context includes only a small recent transcript window; older continuity comes from structured state/memory retrieval.

## 30. Context Compiler

Every inference context is compiled fresh:

1. determine role;
2. determine authorization;
3. gather mandatory context;
4. retrieve relevant structured records;
5. semantic-search authorized memories/documents;
6. score candidates;
7. deduplicate;
8. compress if necessary;
9. fit role budget;
10. render context;
11. store ContextSnapshot.

Mandatory context cannot be evicted. Authorization filtering happens before semantic ranking.

## 31. Retrieval priority

Prefer:

`direct structured state → explicit knowledge/beliefs → relationships/entities → semantic retrieval → LLM inference`

Do not use vector search to answer questions already represented exactly in structured state.

## 32. Context contamination prevention

Do not build one omniscient context and slice strings for actors. `compile_context(actor=Elara, role=ai_player)` must independently query authorized sources.

Model sessions should be stateless from the provider's perspective.

## 33. Turn execution graph

A complex turn can be treated as a DAG: one authoritative event may create independent observation/reaction branches for several actors, whose model decisions can run concurrently before validated actions are committed and eventually narrated.

Safe parallel work includes independent reactions, memory processing, embeddings, and some worldgen. Conflicting state mutations are never blindly committed in parallel.

## 34. Optimistic state versioning

Model proposals record `based_on_world_version` and `based_on_scene_version`. Before execution, stale proposals are revalidated; invalid proposals are rejected or replanned.

## 35. Failure and repair

Model failure cannot corrupt state. Possible fallback order: retry same provider, retry alternate configured model, deterministic fallback, skip optional reaction, or surface recoverable error depending on role.

Invalid structured JSON can be trivially repaired if obvious, otherwise sent through a bounded repair/retry path. Never guess missing mechanical state.

## 36. AI call budgets and priority

Campaign/session settings limit calls per player action (default ≤ 4 synchronous, hard cap 6), background calls per game hour, simulation calls, and generation depth. Player-blocking work has higher queue priority than memory/journal/simulation jobs. Every turn records `turn_metrics`; the degradation ladder in `../specifications/turn-budget-and-latency.md` §5 is what the orchestrator does when a budget is at risk.

Local inference concurrency is explicitly capped for heavy models, small models, and embeddings to manage VRAM/RAM pressure.

## 37. Background worker

A database-backed worker handles embeddings, memory compression, journal/encyclopedia updates, world simulation, latent materialization, offscreen decisions, scheduled events, and low-priority model calls.

Player-blocking orchestration remains synchronous from the user's perspective.

## 38. Journal and encyclopedia

Journal generation receives only the human character's perspective and may preserve misconceptions. Encyclopedia is primarily a structured projection of known names, facts, relationships, last known locations, notes, and confidence; LLMs can turn that into readable prose.

## 39. Replay and prompt versioning

A recorded turn should support mechanical replay, renarration from the same authoritative events, and optionally AI reevaluation into a new branch.

Every prompt has stable ID/version stored with ModelRun so behavior changes can be traced.

## 40. Enforcement over prompting

Do not tell an AI actor “do not reveal secrets” while sending it the secret. Do not tell a narrator “do not change HP” while giving it a mutation tool.

Prompts guide behavior; permissions and typed contracts enforce behavior.

## 41. Initial implementation roles

For the first vertical slice, implement Intent Interpreter, AI Player, NPC Actor, Narrator, World Author, Memory Processor, Canon Extractor, and a generic Rules Adjudicator. World Simulator can start simple.

## 42. Practical model split

A practical first routing setup is:

- small model: intent parsing, memory/canon extraction, summaries, simple NPCs;
- main model: AI companions, important NPCs, narration, rulings;
- strongest configured model: campaign creation, major world authoring, major villain scenes.

If only one useful local model exists, all roles may share it without changing the architecture.

## 43. Orchestration invariants

- Every model call has exactly one declared role.
- Every role has explicit permissions.
- Every actor context is independently compiled.
- Authorization precedes semantic retrieval.
- Provider-side memory is never authoritative.
- AI decisions are proposals, not mutations.
- Only eligible actors receive reaction calls.
- AI-to-AI activity is spotlight-limited.
- Parallel inference does not bypass mechanical execution order.
- Persistent AI-derived changes retain ModelRun provenance.
- Optional AI failures do not invent world truth.
- Simulation is bounded by time/event/call budgets.
- Narration comes after resolution.
- Memory derives from actor observations, not omniscient events.
- Model providers can be swapped without changing campaign format.
