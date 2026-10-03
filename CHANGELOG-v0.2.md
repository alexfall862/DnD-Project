# Changelog — Planning Bundle v0.1 → v0.2

This revision closes the gaps identified in review. v0.1's architecture and sequencing are
unchanged; v0.2 specifies the places where v0.1 said "a model handles it" without saying what
the model receives and returns, adds budgets for time/latency/hardware, restructures
milestones so something is playable earlier, and adds a design-iteration loop.

## New documents

| File | Closes |
|---|---|
| `specifications/communication-and-knowledge.md` | Speech → structured knowledge was unspecified. Defines `conveys[]` on every utterance, authorization of references against the speaker's perspective, the Claim Extractor fallback (≤1 call/utterance), document conveyance, clue discovery by testimony, and Frostbridge worked examples. |
| `specifications/belief-update-rules.md` | No deterministic belief update rules. Gives confidence formulas for observation, documents and testimony (with worked Frostbridge values), contradiction/supersession, deception/insight handling, and strict gating for when the Belief Processor model is consulted. |
| `specifications/turn-budget-and-latency.md` | No latency/call budget. Sets targets and hard caps per turn and per combat round, a call plan, a degradation ladder, SSE streaming (mechanics before narration), the `turn_metrics` schema, and a hardware-target section. Applies from the first orchestrator commit. |
| `specifications/human-visibility.md` | Human visibility was under-modeled. Defines the focus actor, live vs. offscreen scenes, split-party rules (human receives nothing until communicated), multi-PC control, and OOC-only spectator mode. |
| `specifications/time-accounting.md` | Conversation time and scene reconciliation were requirements without mechanisms. One world clock driven by the live scene; conversation time bands with a 60-min cap; bounded catch-up for offscreen scenes; reunion as fast-forward only. |
| `specifications/player-authored-canon.md` | No policy for player assertions. Classifies assertions (`self_minor … contradiction`) and defines `player_canon_policy` (`strict | personal | collaborative`) with accept/adjudicate/refuse per class and limits. |
| `specifications/observation-authoring.md` | Who writes Observation text was undecided. Observations are template-generated structure rendered deterministically; no model-written Observation text; narration is never an Observation source. |
| `specifications/canon-extraction-allowlist.md` | Narrator → extractor back door for canon drift. Structural allowlist (decoration only, `latent`) and denylist enforced by validator, not prompt. |
| `testing/design-iteration.md` | No mechanism for "is it fun?". Playtest cadence, 10-dimension rubric, play journal, tunables exposed without deploy, prompt-change discipline, v0.1 exit criterion. |
| `GLOSSARY.md` | Many precise terms, no single reference. |
| `HARDWARE-TARGET.md` | Routing profiles had no concrete floor. Living file filled by the spike. |
| `tasks/milestone-04b-model-capability-spike.md` | Structured-output assumption untested before five milestones of infrastructure. Gate before Milestone 05. |
| `tasks/milestone-06d-cli-play-harness.md` | Nothing playable until Milestone 10. Terminal harness as first playable, before UI. |

## Restructured milestones

- 02 → **02a Rules Core** + **02b Actions, Positioning & Combat**.
- 06 → **06a Intent, Orchestrator & Player Canon** + **06b AI Players & NPCs** + **06c Narration, Governor & Memory Processing** + **06d CLI Play Harness**.
- Added **04b Model Capability Spike** (gate).
- Every milestone now has a `## Read` context pack listing the specific sections it depends on. `tasks/README.md` lists the 19-step order. `architecture/05-implementation-plan.md` §23 updated to match.

## Amended documents (summary of edits)

- `PROMPT.md` — read list adds the three core new specs and `GLOSSARY.md`; context-pack instruction; **Invariants 16–18** (speech carries structured content; every turn is budgeted and measured; the human is also a perspective); gates before 05 and after 06d; build sequence; event-payload stance.
- `DECISIONS.md` — "Added in v0.2" section recording all new locked decisions, with a pending slot for the spike's go/adjust decision.
- `README.md` — doctrine bullets, reading order, implementation order, the second early proof (model capability).
- `architecture/01-world-memory.md` — pointers from belief/provenance, observation, input-channel, split-scene and world-time sections to the new specs.
- `architecture/03-ai-orchestration.md` — budget doctrine, `claim_extractor` role, `conveys[]` in actor contracts, local-GPU serialization note, deterministic belief processing, extractor allowlist, call caps/telemetry, narrator input discipline and streaming.
- `architecture/05-implementation-plan.md` — milestone order, new checkpoints (spike, harness), orchestrator steps, §30 event-payload versioning stance, §31 context packs.
- `specifications/ai-contracts.md` — Intent Interpreter gains `conveys[]`, `asserted_facts[]`, `conversation_time_band`; AI Player/NPC Actor gain required `conveys[]` and fallback-policy reuse; Narrator streamed with input discipline; Canon Extractor validated against allowlist; Memory Processor input; Belief Processor gating; new §14a Claim Extractor; prompt tree; fixtures; §21 output-size discipline.
- `specifications/api-contracts.md` — `metrics` in `/play` response; §9a SSE streaming; §9b focus actor and spectator; stored clarifications with `clarification_id` (also used for refused assertions); new debug endpoints (turn metrics, scenes, claims); tunables and `settings.changed` events.
- `specifications/database-schema.md` — `claims` (stance enum, `fidelity`, `deliberate_false`, source fact/belief, `conveyance_source`), `clue_discoveries.route`/`claim_id`, `beliefs` types/status, `observations.raw`, `scenes.local_tick`/`merged_from`, new `pending_clarifications` and `turn_metrics`, payload-versioning stance, four new schema invariants.
- `specifications/frostbridge-demo.md` — `conveys[]` on Renn's lie and Mira's partial reveal; expected belief rows for the whisper; live/offscreen split-party timing; §41a player-assertion fixtures; §41b budget expectations.
- `testing/knowledge-leakage.md` — §19 `conveys[]` authorization, §20 proposition leakage rate, §21 human channel, §22 observation rendering.
- `testing/testing-strategy.md` — new unit targets, eval metrics, §23a latency tests, §23b playtest loop, commands, release gate.
- `testing/vertical-slice.md` — belief assertions, offscreen scene handling, Claim provenance, `turn_metrics`, budget and harness in the release gate.

## Not changed

Core doctrine, invariants 1–15, the data-authority model, the Frostbridge content, Core
Adventure numbers, the deferred-scope list, and the API/debug boundary are as in v0.1.

## Open items the spike must answer

1. Can the configured `fast_structured` model produce valid `conveys[]` reliably? If not,
   simplify the schema per `specifications/ai-contracts.md` §21 before Milestone 05.
2. What are the measured tokens/second per profile? Budgets in `specifications/turn-budget-and-latency.md`
   §3 are defaults to be confirmed or adjusted against them.
3. Does the serving stack batch concurrent requests? This decides whether the orchestrator's
   concurrency is worth anything on this hardware.
