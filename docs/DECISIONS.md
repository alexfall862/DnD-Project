# Locked Design Decisions v0.2

This file records decisions already made during planning. Treat these as defaults/requirements unless later explicitly revised.

## Identity, actors, organizations

- Actor and Faction are separate concepts.
- Human and AI PCs use the same character/mechanical representation.
- NPCs use promotable importance tiers; background NPCs can become full actors without replacement.
- Creatures use templates plus persistent individual instances.
- Personality uses both prose and structured dimensions.
- Actors have long-term goals and short-term intentions.
- Goals are persistent entities with status/progress/history.
- Relationships are qualitative + numeric and directional.
- Relationship values are normally hidden outside debug mode.
- Control (`human|ai|scripted|dormant`) is runtime state, not identity.
- Humans may control multiple PCs; control can move human↔AI seamlessly while preserving actor state.
- Parties are persistent entities; multiple parties can exist.
- Important historical/dead/destroyed entities remain referencable; death/destruction is lifecycle state, not deletion.

## Knowledge, belief, observation, memory

- Facts, beliefs, suspicions, rumors, lies, opinions, assumptions, inferences, and false memories are distinct.
- Actors can represent uncertainty/confidence.
- Knowledge tracks provenance/source.
- Actors can genuinely forget/lose specificity, but memory evolution is fully auditable.
- False memories are supported.
- Each witness receives an independent Observation.
- Matter-of-fact sensory resolution is deterministic whenever possible rather than delegated to an LLM.
- Not every incidental noun becomes a full database entity; lightweight canonical observations can exist.
- Visible declarative narration can create lightweight canonical observations.
- Both prestructured canon-before-narration and post-narration incidental extraction are supported, chosen by importance.
- IDs are hidden outside debug mode.
- Identity is separate from names/aliases.
- Entity resolution is perspective-specific.
- Location identity/knowledge can likewise differ by actor.
- Languages and sensory channels are individual capabilities; “common/English” will cover most initial play.
- Written documents persist with immutable original text.
- Core memories exist and are strongly retrieval-favored.
- Subjective memories can interpret objective events differently.
- Actors may revise beliefs through private reasoning without new external facts; resulting beliefs are inferences, not objective truth.
- Private internal intentions/emotions exist, but raw hidden chain-of-thought is not stored.
- Emotions can be explicit temporary state.

## Canon and narrative authority

- Engine → validated World Author → validated DM proposal → explicit debug override are legitimate state/canon authorities.
- NPC speech/AI thoughts do not create objective truth.
- Generated unseen content may be revised; observed/consequential content becomes established canon and cannot silently change.
- Latent world detail can progressively materialize when referenced/visited/queried.
- Player questions can trigger materialization.
- Distant simulation can operate on shallow latent structures without materializing every detail.
- Major generated item mechanics become immutable once established unless explicitly modified in-world or retconned in debug.

## World and locations

- Flexible location hierarchy begins world → region → settlement → district → building → room/zone, but supports planets, ships, planes, dream realms, etc.
- Locations store explicit topology/connections/access/travel relationships.
- Multi-plane/multi-world/multi-timeline structure should be possible from the beginning.
- Theater-of-the-mind zones/distances are the default instead of a grid.
- Combat uses the same general location/zone system as exploration.

## Rules and randomness

- Rules engine is system-agnostic from day one.
- Initiative is a plugin mechanic; default is conventional initiative order.
- Dice expression engine is generic.
- Deterministic replay is required.
- All randomness comes from the engine, never the LLM.
- LLMs can propose new mechanics at runtime using approved primitives.
- Generated content can intentionally be unbalanced when narratively appropriate; structural validity/safety is separate from balance.
- Unknown item properties objectively exist before discovery.
- Mechanics may query authorized subjective knowledge (e.g., true-name gates).
- Inventory supports containers/physical location.
- Ownership and possession are separate.
- Currency can be abstract resources or physical items.
- Resources generalize health/mana/sanity/oxygen/fuel/ammo/political capital/etc.
- Conditions are generic effect containers with categories/tags.
- Rules precedence is explicit: engine primitives → base ruleset → module → campaign → house rule → temporary ruling/effect.
- Community rulesets begin declarative (JSON/YAML); arbitrary executable plugins are deferred and would be trusted/sandboxed separately.
- AI-assisted ruleset compilation/import is desired eventually.
- Runtime rulings are logged and can become reusable precedent, but do not automatically become permanent law.
- Human advancement is directly editable within rules; AI advancement is chosen from legal options using character priorities.
- AI PCs have player-agent mechanical knowledge distinct from in-world character knowledge.
- NPC combat can use a tactical controller distinct from roleplay persona.
- Tactical competence varies independently of general intelligence.

## Events and auditability

- Event sourcing is authoritative persistence strategy with current projections for performance.
- Every important state mutation references the causative event.
- Unexplained LLM state changes are prohibited.
- Raw transcript is stored separately from high-level canonical events.
- Dialogue may be stored verbatim indefinitely as archive.
- Development mode stores prompts/model outputs/context snapshots.
- Context compilation is logged in development.
- Roll seeds/results/modifiers/purpose/visibility are logged.
- Retcons/memory corrections are debug-only and explicit; ordinary play does not silently rewrite history.
- Branching/forked timelines are supported structurally from the start.

## AI autonomy and interaction

- AI party members are genuine independent players, not DM-controlled followers.
- They may disagree, refuse, pursue goals, make mistakes, start fights, spend resources, romance, betray, or leave.
- Former party members continue existing and acting in the world.
- Any ordinary NPC can potentially be recruited based on character circumstances; no special recruitable flag is required.
- AI autonomy is configurable per domain with presets from assistant-like to fully independent.
- AI companions can proactively initiate meaningful actions/conversations.
- Private AI actions are supported.
- Human private actions relative to AI companions are supported.
- Explicit input channels include Say, Do, Whisper, Private/Think, OOC, with natural-language inference by default.
- Direct speech is assumed audible to eligible present actors unless marked otherwise.
- Knowledge propagates automatically from observed communications/events, actor-by-actor.
- Communications/sensory channels should be generic enough for speech, radio, telepathy, letters, etc.
- Spotlight governor prevents AI-to-AI conversations from monopolizing play.

## Input/action handling

- Freeform input is a core strength: the model interprets player intent while engine resolves consequences.
- Compound inputs decompose into interruptible atomic steps.
- Other actors can react between steps according to rules.
- Clarification frequency is configurable; ask only when ambiguity materially changes consequences.
- Conversation advances time at an estimated level rather than per literal sentence.
- Split-party concurrent scenes are supported.
- Unequal scene time requires temporal reconciliation before reunion.

## World simulation

- World time is real persistent in-fiction time/calendar.
- World simulation depth/scope is configurable.
- Offscreen simulation is mostly deterministic/rule-based; LLM calls occur at meaningful decisions.
- Simulation uses level of detail from aggregate distant state to full active-scene entities.
- Random world events can coexist with goal/resource-driven faction actions.
- Economy is story-relevant/baseline rather than exhaustive by default.
- Simulation subsystems are modular toggles/depth settings (politics, economy, ecology, weather, crime, relationships, survival, etc.).
- Campaign-level realism/complexity sliders are desirable.
- DM discretion/rules strictness is configurable.
- No continuous/unbounded autonomous agent loops.
- Game time normally advances from actions; optional real-world-to-game-time mapping may exist later.

## Adventures, mysteries, goals

- Campaign mode can be authored, sandbox, or emergent simulation.
- Adventure planning favors situations, actors, goals, clocks, and secrets over rigid scene scripts.
- Villain/faction plans can be executable goal trees with deadlines/clocks.
- Mysteries generate objective truth first, then evidence/clues.
- Important active mystery answers lock.
- Clues/evidence can be moved, destroyed, forged, or misunderstood.
- Mystery generation should validate logical solvability/redundant clue paths.
- World Author may know objective mystery truth; Narrator receives only what is relevant.
- Quests/objectives can exist for player-facing organization but should not force MMO-style structure; personal goals and journal objectives are distinct.

## Social/world modeling

- Reputation can exist per individual, party, and faction.
- Legal/social statuses such as wanted, citizen, noble, employee, guild member, debtor, married, licensed mage can be explicit.
- Family/social networks can be explicit.
- Relationships and reputations are not automatically symmetric.

## Death, control, branching

- Human and AI PCs can die permanently according to rules/campaign settings.
- Campaign may continue by transferring human control to another existing actor.
- Control can later be returned to AI.
- Death/destruction preserves historical entity record and can support resurrection/spirits where rules allow.
- Save forks/branching timelines are desired; default play can still feel ironman/tabletop.

## Narration and player UI

- Default narration is traditional second-person tabletop style; style/verbosity/humor/grit are configurable.
- NPC dialogue can render as distinct participants from DM narration.
- Generated images/maps and voice are not initial priorities.
- Mechanics visibility is configurable from explicit tabletop results to more immersive narration.
- Player can expand a turn to inspect underlying rolls/modifiers/state changes.
- Journal and encyclopedia are generated from the human character's perspective, not omniscient state.
- Normal production does not expose omniscient correction tools.
- Debug interface can be raw/powerful before player UI is polished.

## Providers and deployment

- Local-first default, provider-interchangeable architecture (local/OpenAI/Anthropic/Gemini/etc.).
- Concurrent/separate inference calls are acceptable and desirable when independent.
- Role-specific/dynamic model routing is desired.
- Embedding model is separate/small.
- Model provider conversation history is never campaign memory.
- Target v0.1 is a web app served from the local Ubuntu AI box, reachable remotely over Tailscale.
- PostgreSQL preferred over SQLite because concurrency, event sourcing, vectors, and workers are expected early.

## Content/tone

- Broad genres and genre mixing are supported when fictionally coherent.
- Genre changes mechanics/content/world assumptions, not just prose.
- User-facing content/tone boundaries should be configurable at campaign creation; implementation must still obey platform/product safety requirements.

## First proof-of-concept

The first vertical slice uses Frostbridge and must prove world generation/seed, one human + two AI PCs, NPC interaction/deception, private knowledge, unique hidden-property item, skill check, theater-of-the-mind combat, split party, world-time progression, faction/offscreen event, save/restart, durable memory, and exact perspective isolation.

## Added in v0.2

### Communication and belief
- Every utterance reaching another actor produces Claims with structured `conveys[]`; AI actor outputs must supply it; a Claim Extractor is a bounded fallback (one call per utterance max).
- `conveys` references are authorization-checked against the speaker's perspective; a violation is a leakage incident and rejects the proposal.
- Belief type and confidence are assigned by deterministic rules (`specifications/belief-update-rules.md`); the Belief Processor is gated and may only adjust within ±0.25 or add `inference`.
- Speech by a human-controlled actor records a `stated` self-belief; OOC never does.
- Clues can be discovered by testimony; `clue_discoveries.route` and `claim_id` record it.

### Observations and canon
- Observations are template-generated structure, rendered deterministically; no model-written Observation text.
- Human-facing narration is never an Observation source for anyone.
- Canon Extractor persists decoration only, as `latent`; the allowlist is enforced structurally.
- Player assertions are classified and handled by `player_canon_policy` (`strict | personal | collaborative`, default `personal`); accepted ones are events with `player_assertion` provenance.

### Human visibility and time
- The client renders one focus actor; offscreen scenes are hidden by default; `spectator_mode` is OOC-only and grants no knowledge.
- One world clock, driven by the live scene; offscreen scenes catch up in bounded steps; `scenes.local_tick ≤ world clock` in v0.1.
- Conversation advances time by Intent Interpreter bands with a 60-minute per-scene conversation cap.

### Budgets, hardware, process
- Per-turn synchronous call cap (default 4, hard 6), time budgets and a degradation ladder apply from Milestone 06a; `turn_metrics` recorded for every turn.
- `/play` streams mechanics before narration.
- `HARDWARE-TARGET.md` must be measured by the Milestone 04b spike before AI infrastructure is built; the spike's go/adjust decision is recorded here when made: **(pending)**.
- Milestones 02 and 06 are split (02a/02b; 06a/06b/06c/06d); 04b (spike) and 06d (CLI harness) added. First playable is 06d, before UI.
- Event payload upcasters are not written before v0.1; development campaigns are disposable and `make reset-db` is the migration path. **Revisit the day a campaign is declared non-disposable.**
- A playtest rubric and journal (`testing/design-iteration.md`) run after every milestone from 06d; v0.1 exit requires three consecutive sessions meeting its criteria.
- Each milestone carries a `## Read` context pack; `GLOSSARY.md` resolves terminology.

## Added at implementation start (2026-10-03)

### Environment and inference
- Development runs on a Windows 11 workstation (Git Bash + PowerShell, Docker Desktop for
  PostgreSQL + pgvector, GNU make via winget). The bundle's "Ubuntu local AI server" is the
  *inference* host only, not the app host, until v0.1 deployment is revisited.
- Inference is served by the **A9 gateway on afhserver over Tailscale** (see `HARDWARE-TARGET.md`).
  Routing profiles map to **A9 project names**; A9 chooses the actual model. The spike measures
  whatever A9 serves.
- A9 behaviours that would violate Invariants 3 and 13 are defeated structurally in the provider
  adapter, not by prompt: a dedicated no-persona, no-tools, `chat`-scope project; a unique
  `model_run_id` line opens every request so no two calls share an A9 session; retries on
  503/Retry-After and 409; no provider conversation state is ever referenced.
- Structured output is prompt-requested JSON validated by the engine. `response_format`
  passthrough is a spike measurement, not an assumption.

### Sequencing adjustments (architecture unchanged)
- **Milestone 04b runs as a parallel track** alongside 00–04 rather than after 04. It has no
  code dependencies and is the largest unknown; its go/adjust decision is still required before
  05 starts.
- **Next.js scaffold deferred from Milestone 00 to Milestone 10.** Nothing touches it for
  fifteen milestones and the CLI harness (06d) is the first playable. `frontend/` holds a
  placeholder README until then.

### Document corrections applied
- `specifications/frostbridge-demo.md` §10 now seeds companion↔Alex relationships (the
  belief-rule worked values assumed Elara→Alex trust ≈ 60 but no row existed).
- `testing/knowledge-leakage.md` §2 whisper text unified with the fixture ("I think Mira had
  something to do with Oric's disappearance").
- `tasks/milestone-03-perspective.md` states that `conveys[]` is supplied structurally until the
  Intent Interpreter exists in 06a.
- `specifications/turn-budget-and-latency.md` §2 no longer duplicates the hardware YAML;
  `HARDWARE-TARGET.md` is canonical.

### GLM re-validation of the 04b decision (2026-10-03) — decision (b) stands, with changes
- **Holds:** 0 `conveys` authorization violations in 270 samples; Renn's spoken text leaked the
  murder/smuggling 0/30; all five intent cases 100% schema-valid and key-passing, including
  "Attack him" (100% clarification — GLM, unlike the retired model, asks). Engine-side ambiguity
  detection stays as defence in depth but is no longer the sole mechanism.
- **Changed — schema validity:** actor roles are 67–93% valid raw (retired model: 94–100%),
  100% / 90–93% after one repair. Failures: `predicate` placed at the top level of a `conveys`
  item instead of inside `proposition` (12/90), and unterminated JSON on long outputs (7/90).
  → The bounded repair call is **mandatory** for actor roles, not optional, and the budget
  allows for it (`turn-budget-and-latency.md` counts repair calls as synchronous calls).
  The validator also accepts a top-level `predicate`/`value`/`subject_entity_id`/
  `object_entity_id` on a `proposition` item and normalises it before validation.
- **Changed — deception flags are unreliable (the important one):** Renn's reply was a false
  statement ("haven't spoken to him in weeks") in most samples but was labelled `evade` /
  `answer` with `knowingly_false=false` in 22/30; only 8/30 were flagged as lies. Spoken text
  never leaked, and a Claim is a Claim either way, but insight mechanics and the private
  `deliberate_false` record need to know. → **The engine derives `deliberate_false`; the model
  no longer asserts it.** Actor output replaces `deliberate_false`/`knowingly_false` with
  `contradicts_ref`: the id of a speaker-held fact or belief that the utterance contradicts
  (nullable). The engine sets `deliberate_false` when `contradicts_ref` names a *fact* the
  speaker holds (knowing falsehood) and leaves it false for contradicted *beliefs* (honest
  error). `speech_act.type` becomes advisory flavour only. To be re-measured in Milestone 06b;
  the 04b budget of two prompt iterations per case is spent, so this is a design change, not
  another tweak.
- **Changed — latency:** actor p50 14–19 s (≈ 260–330 completion tokens, ~2k-token prompts),
  intent p50 7–12 s, narrator p50 13.6 s total. At 22.5 tok/s, per-role `max_tokens` budgets
  and short outputs matter more than before; `ai-contracts.md` §21 limits stand. Complex-turn
  target is unreachable with two visible reactions — resolved: budgets relaxed, see
  "Latency budgets revised".
- **Unchanged:** `kind` advisory; lexical corroboration of refs; one A9 project/model for all
  profiles; embeddings still needed before Milestone 04.

### Latency budgets revised (2026-10-03, Alex)
Alex accepted longer turns so the local GLM-4.5-Air model can be used as-is (no second resident
model, no cloud fallback). Consequences, recorded in `turn-budget-and-latency.md` §3–§5:
- Time to first narration token: simple turn target 12 s / hard 20 s; complex turn 25 s / 40 s.
  Combat round 40 s / 75 s. Time to first visible output (mechanics, streamed) stays ≤ 2 s / 5 s.
- Default visible AI reactions per turn: ~~1~~ **2, run concurrently** (superseded the same day by the
  parallel re-probe below; tunable `spotlight_visible_reactions`, 1–2).
- Per-role `max_tokens` budgets (`ai-contracts.md` §21), mandatory repair call for actor roles,
  and stable-prefix-first prompt layout (prefix caching) remain requirements.
- Revisit if A9 gains a faster resident model; the budgets are campaign-configurable defaults.

### Parallel inference re-probe (2026-10-03)
Alex switched the A9 host to GUI-less mode (4 request slots). Measured (`HARDWARE-TARGET.md`):
single-call speed unchanged at 22 tok/s; effective concurrency is 2 (aggregate 31.5 tok/s,
plateau from 2 callers upward). Two concurrent calls ≈ 1.5x one call. Consequences:
- The orchestrator runs independent reaction calls concurrently, **max in-flight inference = 2**
  (`MAX_CONCURRENT_INFERENCE=2`); a third queues behind them.
- Two visible reactions run in parallel: intent ~8 s + 2 parallel reactions ~16 s + narrator
  first token ~1 s ≈ 25 s, which meets the revised complex-turn target (25 s) without dropping to
  one reaction. The relaxed budgets stay as agreed; they are now met with margin rather than
  needed. Default visible reactions restored to 2.
- Worth asking Alex: whether the server runs `--parallel 4` with experts offloaded to CPU; if
  decode is bandwidth/compute-bound by offload, more slots will not help.

### Embeddings and rerank via A9 (2026-10-03)
A9 now serves `ttrpg/local-embed` (Qwen3-Embedding-0.6B, 1024 dims) and `ttrpg/local-rerank`
(bge-reranker-v2-m3) to the `ai-ttrpg` token. Memory retrieval uses them in the order
authorize → structured candidates → query embedding (`input_type: query`) → vector shortlist →
rerank → score. Memories are embedded as `document`. Vector column is `vector(1024)`.
Rerank scores are logits and are only compared within one call (or squashed by a sigmoid).

**No ANN index in v0.1.** pgvector's HNSW/IVFFlat indexes apply `WHERE` filters after the
approximate search, which can under-fill results and inverts the "authorization before
semantic ranking" rule. Retrieval therefore does an exact cosine scan restricted to one actor's
memories (B-tree on `actor_id`); at ~1k memories per actor that is milliseconds. Revisit at
Milestone 11 (stress) with per-actor partitioning or iterative index scans if needed.

### AI actors (06b) — implementation decisions (2026-10-03)

- **Reaction significance is engine-side and cheap.** Signals are engine facts (addressed,
  asked, attacked, received a Claim, Claim touches a goal target, relationship row exists,
  novelty in this scene, strongest emotion, importance tier). Weights live in
  `app/engine/reactions.py`; `high ≥ 0.55` gets a model call (bounded by
  `SPOTLIGHT_VISIBLE_REACTIONS`), `medium ≥ 0.3` is noted silently, `low` is ignored. A
  question addressed to one actor does not make everyone who overheard it "asked".
- **In combat, initiative turns are the reactions.** No reaction calls are made during an
  encounter; AI combatants act on their turn, and the human's turn ends when their major
  action is spent (or they wait/flee/surrender).
- **Fallback policies are the default, not a degradation.** A stored policy is reused whenever
  `situation_unchanged` holds (same target standing and hostile, health above the flee
  threshold, no heavy damage since); the ladder step forces reuse even when it changed. This
  is what keeps a 5-combatant round near one or two calls after round 1.
- **Corroboration includes the question being answered.** "Weeks ago." carries no key term
  of the fact it lies about; the question it answers ("when did you last speak to Oric?")
  does. `communication-and-knowledge.md` §2 corroboration is therefore checked against the
  spoken text ∪ the terms of the last question-stance Claims the speaker heard.
- **Any ref the engine cannot map is leakage.** A short ref not in the supplied context, or
  a raw id outside the speaker's perspective, rejects the whole proposal and records
  `proposal.rejected_leakage`; dropping the item silently would let the rest of the speech
  through while hiding the incident.
- **Concurrent decisions, sequential writes.** `ModelRunner.run_many` creates all ModelRun
  rows, gathers provider calls concurrently, then validates/persists in order on the single
  session. Applying is sequential by significance with revalidation against the current
  scene.
- **Failed actions get a ledger event.** `action.resolved(status=failed)` is emitted after a
  dispatch error (costs were paid, partial mutations may stand). Previously such outcomes had
  no event, which broke the commit path once AI combatants started failing moves.
- **Contract additions:** `relationship_proposals` (±10 per dimension, event-linked),
  typed `goal_updates`, `fallback_policy`, `speech_act.knowingly_false`. `npc_tactical`
  is registered but unused.

### Narration, governor, memory (06c) — implementation decisions (2026-10-03)

- **The narrator is a prose role.** Streaming JSON would put `{"narration": "` in front of
  the first token; the client wants prose deltas. Decoration extraction is the separate,
  cheap Canon Extractor pass on the finished prose (allowlist-validated), so nothing is lost.
- **Compression means a count, not a summary.** When the spotlight budget is exceeded the
  narrator is told "N other(s) present react quietly"; it is never given invented content to
  summarise, and no Claims or Observations are produced for compressed actors.
- **Checkpoint windows are per actor per scene.** `scene.state.memory_checkpoints[actor]`
  holds the timestamp of the last processed observation, so a deferred checkpoint picks up
  exactly where it stopped; the window itself is the memory's lineage when the model cites
  nothing usable.
- **Model clarification requests are advisory.** Engine-side candidate resolution decides
  (04b, orchestration §10); GLM asked "which actor?" for `I ask Mira quietly …`. Loose target
  spellings from the model are matched to candidate refs by name tokens.
- **Encyclopedia is rebuilt on read.** It is a projection of identity knowledge + beliefs; no
  model, no event, cheap enough to rebuild per request until it is not.

### Terminal harness (06d) — implementation decisions (2026-10-03)

- **The seed lives in the app, not in tests.** `app/seeds/frostbridge_tavern.py` is the one
  Red Lantern; the pytest fixture, the debug `seed-demo` endpoint and the harness share it,
  so what the tests prove is what the terminal plays.
- **Debug endpoints are the harness's only privileged path.** Seeding, actor listing, scene
  end, metrics and model-run contexts are `/debug/*` (DEBUG_MODE). Everything the player sees
  comes from the normal perspective endpoints and `/play`.
- **Narration is streamed on a terminal and buffered elsewhere.** The harness writes
  `narration_delta` tokens straight to stdout when its sink is `print`; any other sink (tests,
  logs) receives the joined narration once, so output lines stay meaningful.

### Frostbridge fixture (07) — implementation decisions (2026-10-04)

- **07/08 boundary.** Milestone 07's required scenario "time advance / evidence destruction"
  needs scheduled events to fire, which Milestone 08 owns. Decision: the *deterministic* part
  lands in 07 (`ScheduleService`: schedule, fire when the clock passes `scheduled_tick`,
  revalidate prerequisites against current state, handlers `fact.establish`, `clue.destroy`,
  `plan.advance`, `location.state`); anything that needs the World Simulator stays `pending`
  (Day +5 shipment is `faction.shipment_departure`, untouched until 08). The background worker,
  faction/plan reasoning and deterministic catch-up systems remain 08.
- **Offscreen catch-up is bounded to one decision and to AI party members.** time-accounting §4
  in 07 form: when an offscreen scene lags the clock by more than 10 minutes, at most one AI
  decision (intentions only, full mechanics) for its most important AI *party member*, then
  `scene.caught_up`; at most two scenes per live turn; nothing reaches the human. NPC-only
  scenes (Mira and Renn waiting in the tavern) get no call until 08 adds plan steps and
  triggers, so idle rooms cost nothing.
- **Live scene = a scene with a human-controlled participant.** `_advance_clock` moves only
  live scenes' `local_tick`; offscreen scenes lag and are fast-forwarded when someone arrives
  (`scene.caught_up` inside the travel transaction). Reunion joins the active scene at the
  destination; `merged_from` is recorded only when a whole scene arrived (an emptied scene ends
  in the same transaction). No Observations or Claims are created by arriving except plain
  arrival observations ("Tomas arrives at Guard House").
- **Concealed items and search.** `items.concealed` + `concealment_difficulty`; a successful
  `action.search` of a zone reveals the concealed items there whose difficulty the total meets
  (`item.revealed`, per-observer Observations). Physical clues on a revealed object are
  evidence (`clue_discoveries route=physical`, belief `known 1.0`, belief-update §3); document
  clues are only *found* (`route=document fidelity=partial`) — reading stores the content.
- **Documents.** `WorldService.create_item(document=…)` creates the immutable `documents` row
  in the item's transaction (sha256 `content_hash`). `DocumentService.read` is an Observation
  (`read_document`) whose Claims come from the stored `conveys[]` with the author as speaker
  (no Claims without an actor author; beliefs still form at `0.85 × trust`, unsigned 0.7).
  A `conveys` item of kind `identity` teaches the reader a name (the gate notice names Oric).
- **Names move by communication.** A Claim about an entity conveys the speaker's name for it
  to listeners who have none (`SpeechService._convey_names`); nobody learns their own name
  this way. This is how the party learns "Captain Renn" from Mira without a scripted intro.
- **Testimony discovers clues.** c&k §6: when a Claim conveying a clue's supported fact reaches
  a PC, `clue_discoveries(route=testimony, claim_id, fidelity)` is recorded for every intact
  clue supporting that fact (partial fidelity never links the fact row to the belief).
- **Mystery lock is structural.** `MysteryService.replace_truth` raises `MysteryLockedError`
  while `solution_locked`; `routes_remaining().solvable` is the redundancy check the seed and
  the Day +3 destruction test use.
- **NPC autonomy defaults to autonomous.** The `ask` defaults protect the human's party from
  their companions' big decisions; an NPC without a profile has nobody to ask (a thief may
  surrender). Before this, `action.surrender` for a thief paused on the gate forever.
- **Fleeing is a route.** Fallback tactics now disengage first, head for the nearest exit zone
  and `flee` through it when in reach; spaces without exits keep the old behaviour.
- **An encounter can end on any action.** `encounter.ended` is emitted from the action commit
  when the status flips (last foe surrenders/falls), not only on an explicit turn advance;
  this is what fires the combat-end memory checkpoint.
- **Completeness heuristic counts referenced records' entities.** A `fact_ref`/`belief_ref`
  item references its fact's subject/object; previously only `proposition` items did, so a
  partial reveal about "the captain" always paid for a Claim Extractor call.
- **Seeding is one unit of work.** `services.events.unit_of_work` makes EventTransactions
  flush instead of commit; the seed commits once after `verify()` and a failure rolls back
  everything (the campaign row, created before the unit of work, is removed). Never used on
  the play path.
- **Persistent environmental consequences** use a registered primitive, `alter_feature`
  (zone feature text replaced/removed in the scene space, persisted with the scene state), so
  "a heavy shelf toppled across the floor" outlives the encounter without parsing prose.
- **§23 generated artifact** is a fixed, validated `mechanical_definitions` row in fixture
  mode (`validate_artifact`: ≤ 1 passive + 1 activated effect, registered primitives, no
  teleport/resurrection/permanent attribute increase). The World Author call for it belongs
  to Milestone 09's generation pipeline.
- **The seed is Python, not YAML.** §40 recommends a YAML directory; the seed stays declarative
  Python tables (`LOCATIONS`, `SPACES`, `EDGES`, builds, behaviour) with stable symbolic keys,
  which the tests and harness already consume. Revisit with worldgen (09) if authored content
  needs non-programmer editing.
- **Known gap:** NPC Actor output has no speech channel, so Mira's private reveal is spoken
  aloud (everyone present hears it). Adding `speech_channel` to `NPCActorOut` is a contract
  change for the design-iteration backlog.

### World simulation (08) — implementation decisions (2026-10-04)

- **A simulation run is an Event, not a table.** `SimulationService.tick(from_tick, to_tick)`
  records `simulation.run` with interval, candidates, event budget, model calls and what was
  applied/rejected (Invariant 14 made auditable). No `simulation_runs` table in v0.1.
- **Order inside a run is fixed:** deterministic scheduled events still pending → due
  `actor.travel` (through `SceneService.travel`, so arrivals are observed and scenes merge) →
  plan clocks → candidate selection with prerequisite revalidation (a failing prerequisite
  cancels deterministically, no model call) → at most ONE World Simulator call → the record.
- **Plan steps may carry a clock.** A step is a string (no clock; advanced only by events) or
  `{title, at_tick, kind, prerequisites}`. `kind: deterministic` steps advance when due and
  their prerequisites hold; `kind: decision` steps and non-deterministic scheduled events (e.g.
  `faction.shipment_departure`) are the simulator's candidates. A scheduled event may carry
  `on_proceed` (a deterministic handler spec) so "the barge leaves" becomes a Fact when the
  simulator lets it happen, and `plan_id` so the plan advances with it.
- **The simulator proposes only against the candidate map.** `WorldSimulatorOut.proposals`
  reference `s1`/`p1`/`l1` refs from the request; unknown subjects, wrong proposal types and
  anything over the event budget are rejected and listed on the run. `plan_hold` reschedules
  (default one day); `cancel`/`plan_abandon` end it with an event.
- **Triggers:** a live turn whose clock advance crosses `simulation_granularity_seconds`
  (default 6 h) or ends with wait/rest; the debug `POST /campaigns/{id}/advance-time`
  (`process_simulation`); the `simulation.advance` worker job. An idle world costs zero calls.
- **`actor.travel` is simulated, not clock-fired.** Travel needs scene transitions (their own
  EventTransactions), which cannot nest inside the clock's transaction; the simulation runs it
  after the clock. Milestone 07's `_advance_clock` hook therefore fires only the pure-data
  types (facts, clues, plan steps, location state).
- **Background queue = `background_jobs` + `FOR UPDATE SKIP LOCKED`.** Claim and work use
  separate sessions; a failing handler rolls back its own session, the job records the error
  and retries with backoff (5 s, 30 s, 2 min, 10 min) until `max_attempts`, then stays failed.
  Jobs are optional work only: memory.embedding, memory.process (deferred checkpoints),
  journal.update, simulation.advance; `world.materialize` is registered but raises until 09.
  The orchestrator enqueues what the degradation ladder deferred instead of dropping it.
- **Catch-up stays bounded (07 form).** The §4 "plan step completes within delta" trigger for
  offscreen AI PCs is still represented by "an AI party member is in the scene"; NPC scenes
  advance through plan clocks and scheduled events, which is what §4 step 2 asks for.
- **NPC speech has a channel (08-0).** `NPCActorOut.speech_channel` / `speech_target_ref`;
  whispers reach the target and legitimate overhearers only. Developers see the channel on
  the model run's structured output (`/debug/model-runs/{id}/context`).
- **Objective roles' supplied sections are public.** The context compiler's strict mode had
  treated the simulator's engine-built sections (interval, candidates, plans, budget) as
  unauthorized because only a fixed list of section names counted as public; for a
  non-actor-scoped role every supplied section is engine data.

### Campaign generation (09) — implementation decisions (2026-10-04)

- **Stage outputs are proposals; the world is built once, at start.** Each stage stores its
  validated `WorldAuthorOut` envelope on `generation_stages.output`. Nothing touches world
  tables until `POST /campaigns/{id}/start`, which merges every envelope and builds the world
  in one unit of work through the ordinary services (every row commits with its Event), runs
  the §25 quality checks, emits `campaign.started` and activates the campaign — or rolls the
  whole build back and leaves a generating draft. This is what makes pre-play rerolls and
  dependency invalidation cheap: replacing an output never has to retract an Event.
- **18 stages, one bounded call each, at most one corrective retry.** The pipeline follows
  campaign-generation §5 with two adjustments: mysteries are stated *truth first* in the
  `secrets` stage (truth facts, participants as minimal actors, timeline, red herrings) and
  their clues are attached in `opportunities`, once places and objects exist; political
  structures are factions of `kind: polity`. A rejected answer is retried once with the exact
  validation errors in the task; a second rejection fails the stage and the run.
- **Refs are the model's, ids are the engine's.** The World Author invents short refs
  (`loc_*`, `npc_*`); validation resolves every ref against the accepted stages; the builder
  maps refs to ids and stores `gen_ref` on each entity so later materialization can find them.
- **Latent actors may be refined.** A later stage may repeat an earlier actor's ref to fill
  empty fields (the secrets stage names the poisoner, the NPC stage gives him a desk and a
  sheet); a differing non-empty value is a contradiction and rejects the stage.
- **Contradiction rules (structural, not semantic):** a new fact about the same subject/object
  whose predicate is the negation (`not X` vs `X`) of an established fact or a mystery truth,
  or the same predicate with a different value, is rejected. Metaphysics facts are forced to
  `established`. This catches the contradictions the engine can state precisely; semantic
  near-contradictions remain a real-model evaluation concern.
- **Depth policy is enforced per stage** (`max_detail`): world stages produce outlines,
  the region latent places, only the settlement stage materialized places with zones; player
  characters only in the party stage, under the Core Adventure creation budget (attributes
  3–8 summing to ≤ 25, skill ranks ≤ 3 summing to ≤ 10, ≤ 2 traits).
- **Knowledge is assigned, never inferred.** A generated fact is held only by the actors in
  its `known_by_refs` or whose `knows_fact_keys` name it; identity knowledge comes from
  `knows_refs` and the actor's own place hierarchy. The quality check refuses a world in
  which a party member starts holding a secret or a mystery truth.
- **Residents join new scenes.** `SceneService.travel` now includes actors already at the
  destination and in no scene (an innkeeper, a warden) when it starts a scene there.
- **Progressive materialization (§27)** is `MaterializeService.materialize_location`
  (`world.materialize` job): the World Author repeats the target ref as a materialized place
  with zones plus what it needs; the same validator runs against the campaign's established
  canon (read back from the database); `location.materialized` records the change.
- **Generation API** lives in the normal API (api-contracts §6) plus `POST /campaigns` to
  create a draft. Runs execute as a `campaign.generate` job, or inline with `?inline=true`
  for development and tests. Preview hides secrets unless debug mode and `include_secrets`.
- **Deferred at first, built in 09b** (below): guided creation, imports, genre-module ruleset
  content and real-model runs of the stage prompts.

### Campaign generation follow-ups (09b) — implementation decisions (2026-10-04)

- **Genre modules are declarative ruleset packages** (`rulesets/core_adventure/modules/<key>/`:
  `module.yaml` + content files in the ordinary sections). Four exist: fantasy (Arcana, Mana,
  Arcane Gift, staff, focus crystal), horror (Occult, Stability, Shaken, Stalwart), survival
  (Hungry, rations, waterskin, bedroll), sci-fi (Piloting, Hacking, Cybernetic Eye, energy
  pistol, scrap rifle). A module may only *add* definitions — redefining base content is a
  load error — and carries world-generation constraints that every stage is told. The brief's
  genres select modules once, at `create_run`, recorded as `campaign.settings.genre_modules`;
  from then on validation, building, play (`/play`, debug, journal) and worker jobs use
  `RulesEngine.for_campaign(...)`. Parsed rulesets are cached per module combination.
- **Imports are an `import` stage (order −1), established canon.** Structured JSON shaped like
  `WorldAuthorOut` is validated without a model; text/Markdown is read in paragraph-preserving
  chunks of ≤ 6 000 characters, at most 8 (a longer source is refused with a message, never
  silently truncated), one World Author extraction call per chunk plus one corrective retry,
  each chunk seeing the refs of the earlier ones. The source text is placed in the task as
  data. Imported content counts toward stage minimums, imported character sheets count toward
  the party (the party stage completes them), and a new generation run carries the latest
  successful import forward. An import is replaced by importing again, never "regenerated".
  PDFs, images and maps are not read: their text must be extracted first.
- **Guided creation is a bounded interview** (`brief_interviewer`, fast profile, ≤ 8 answers):
  each answer → one call → a *patch* applied field by field to `CampaignBrief`; unknown fields,
  invalid values and protected fields (`seed`) are refused and reported, so a confused answer
  cannot corrupt the brief. An unusable reply keeps the brief and the question. "done" ends it
  without a call. The conversation state lives in `generation_brief._guided`.
- **Item effects have a contract stricter than "registered primitive".** The first A9 run
  produced an artifact whose effects were `reveal_information` and `create_entity` with
  invented parameters and `{template}` placeholders — structurally valid, meaningless in play.
  Generated item mechanics now use only item-safe primitives (`modify_check`,
  `modify_resource`, `restore_resource`, `deal_damage`, `apply_condition`, `remove_condition`,
  `grant_capability`) with exactly the parameters each one reads, low-tier bounds (checks
  ±3, dice up to 1d8/2d4) and no placeholders; the contract is spelled out in the stage task.
  The Frostbridge fixed artifact was corrected to the parameter names `modify_check` reads.
- **Frostbridge §23 is generated when a provider is given** (`seed_frostbridge(...,
  artifact_provider=...)`, `make seed-demo ARGS="--generate-artifact"`): one bounded call
  before the seed's unit of work opens (no transaction waits on a model), one corrective
  retry, and the fixed definition as the fallback.
- **Strict structure, normalized links, salvaged length** (the real-model runs,
  `docs/spikes/worldgen-a9-2026-10-04.md`). Stage validation fails only on what defines the
  world: homes, object placement, clue objects, mystery truths, the opening place, player
  legality, contradictions of established canon or a locked truth. Links and quantities are
  normalized deterministically and recorded as `note:` entries on the stage row: dangling soft
  references dropped, NPC numbers clamped, 0..10 scales rescaled, repeats dropped (the earlier
  version stands), depth clamped, latent people/places/factions refined by ref (people may be
  revised before play; imported ones may not; places only deepen), player sheets fitted to the
  creation budget. No normalization widens knowledge or invents content.
- **Truncation is salvaged, then continued.** For list-shaped roles (`world_author`,
  `world_simulator`, `memory_processor`) a cut-off answer keeps every complete top-level item
  (never a half-written one) and the stage's bounded second call is a *continuation* told what
  exists and asked only for what is missing. Actor roles never salvage speech.
- **Bug fixed (06b):** the runner's truncation repair instruction was written for actor roles
  ("spoken_text", "conveys") and was sent to every role; a cut-off World Author stage answered
  with an NPC speech. The instruction is now role-specific. World Author output budget
  2400 → 4096 tokens.
- **Provider:** transport errors (timeouts, dropped connections) become `ProviderError` so a
  failed call is a recorded failed run, never an escaped exception; the read timeout scales
  with `max_tokens` (≈ 15 tok/s worst case + 60 s).

### Itemized generation stages (09c) — implementation decisions (2026-10-04)

- **The five heavy stages are outline-then-fill** (`app/worldgen/itemized.py`; `Itemized` in
  `stages.py`): secrets, starting settlement, NPCs, opportunities and party. One small call
  lists the stage's items (ref plus a line each); one call per item writes it in full, seeing
  the outline and the items already finished. Why: on GLM-4.5-Air these stages wrote 3–6k
  tokens in one answer, overran the output budget, and one bad entry cost the whole stage.
- **The retry boundary is one item.** Each item has its own bound (one call plus one
  corrective retry, told its own errors) and is validated with `scope="item"` (no stage
  minimums or party composition; outline refs resolve as siblings). Good items are kept when
  another fails. The outline is checked up front: range trimmed, repeats dropped, foreign
  refs refused, party composition required.
- **The merged stage is validated once more as a whole.** An error naming an item sends that
  item back; a shortfall in another section ("needs at least 2 clues") goes to the items with
  none of it; one repair round, then the stage fails with the unfinished items recorded. Only
  a shortfall of the items themselves discards the outline.
- **Progress is persisted** on `generation_stages.progress` (migration 0015) and committed
  after every item, so a rerun (or a crashed worker) resumes at the first unfinished item.
  Rerolls and dependent invalidation clear it; acceptance clears it.
- `attempts` on an itemized stage counts its calls. Plain stages keep salvage plus
  continuation for cut-off answers. The A9 eval resumes a run with `WORLDGEN_A9_RESUME=<run id>`.
- **The first itemized A9 run found five fixes** (`docs/spikes/worldgen-a9-2026-10-04.md`).
  The no-zones error names legal places. Budget fitting drops untrained skills, and player
  skills out of range are fitted, not rejected. The per-member party rules run per sheet.
  Generated schedules never land before the current clock, so day 0 means "as play
  begins". The settlement reachability check follows routes and containment transitively.

### Pending
- **2026-10-03, later:** A9 was updated after the spike. The project now serves **GLM-4.5-Air**
  as `ttrpg/local-general` (explicit model name; A9 never substitutes; 409 = not loaded, wait
  ~2 min; 503 = slots busy, wait 5 s; 32k context). The numbers below were measured on the
  retired `local-coder`. **Re-validated on GLM 2026-10-03** (`docs/spikes/model-capability-2026-10-03-glm.md`,
  N=30 × 9 cases, all responses echoed `ttrpg/local-general`); outcome in "GLM re-validation" below. Already known from the GLM probe (`HARDWARE-TARGET.md`): 22.5 tok/s
  output (half of before), prefix caching works (stable-prefix-first prompt layout becomes a
  Context Compiler requirement), concurrent calls serialize, and the complex-turn *target* in
  `turn-budget-and-latency.md` §3 is not reachable with two visible reactions — only the hard
  cap is. **Open for Alex:** accept slower complex turns (ladder drops to one visible reaction
  by default), or ask A9 to keep a small model co-resident for `fast_structured` roles.
- 04b spike go/adjust decision: **(b) proceed with adjustments — decided 2026-10-03; confirmed on GLM (see below).** First-run report (retired `local-coder`):
  `docs/spikes/model-capability-2026-10-03.md` (N=50 per case, 450 samples, A9 `ttrpg` →
  `local-coder`, `json_object` mode). Findings and the adjustments they force:
  1. **Schema stays as specified.** Raw schema-valid 94–100% with the full nested `conveys[]`
     schema; 99% after one bounded repair. No flattening needed.
  2. **Zero `conveys` authorization violations in 450 samples.** The structural guarantee holds.
  3. **`conveys[].kind` is advisory.** The model labels belief ids as `fact_ref` 80% of the
     time. The engine resolves the kind from the id (`b_*`/`f_*` tables), never from the label.
  4. **Fact refs need lexical corroboration.** ~8% of Renn samples attached a secret fact
     (`f_renn_4/5`) as `asserts_true` to speech that did not say it. Stored naively that is a
     structured leak via mislabeling. Rule: a `fact_ref`/`belief_ref` with `stance` ≠ question
     is stored only if the referenced record's key terms overlap `spoken_text`; otherwise the
     item is dropped and logged (`communication-and-knowledge.md` §2 amended). Spoken text
     itself never leaked (0/50 for Renn; 1/50 Mira said "ledger", a word she could plausibly
     use). Deception marking is reliable: 47/50 `knowingly_false`, 46/50 `deliberate_false`.
  5. **Ambiguity detection is engine-side.** 0/50 clarification requests for "Attack him" with
     two hostile candidates, even after a prompt iteration; the model picks one at 0.95
     confidence. Deterministic resolution (`03-ai-orchestration.md` §10) must detect
     pronoun/descriptor + multiple candidates and raise the clarification itself.
  6. **Output budgets are the latency lever.** Latency ≈ 0.023 s/completion token; prompt
     processing is cheap (TTFT 0.35 s at 887 tokens). Actor outputs averaged 520 tokens
     (12 s p50). Per-role `max_tokens` and shorter `decision_summary` (≤ 40 words) are now
     required (`ai-contracts.md` §21). Projected social turn: intent ~4 s + two reactions
     ~5–6 s each + narrator TTFT < 0.5 s ≈ 15–17 s to first narration token, inside the hard
     cap and at the complex-turn target with one reaction dropped by the ladder.
  7. **One A9 project for all profiles for now.** `local-general` was swapped out throughout.
     Routing stays logical; revisit when a second resident model exists.
  8. **No embedding endpoint on A9.** ~~Decide before Milestone 04.~~ Resolved: A9 added
     embeddings and rerank (see "Embeddings and rerank via A9").
- Models behind A9's two slots and Deep mode: **still unknown** (`local-coder` is what was
  measured; name/size/quant/ctx to be recorded in `HARDWARE-TARGET.md`).
