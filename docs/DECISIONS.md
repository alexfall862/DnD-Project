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
  8. **No embedding endpoint on A9.** Milestone 04 needs one: either A9 exposes
     `/v1/embeddings` or the backend runs a small local embedding model (CPU is fine for
     v0.1 volumes). **Decide before Milestone 04 starts.**
- Models behind A9's two slots and Deep mode: **still unknown** (`local-coder` is what was
  measured; name/size/quant/ctx to be recorded in `HARDWARE-TARGET.md`).
