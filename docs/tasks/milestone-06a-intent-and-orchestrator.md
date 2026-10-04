# Milestone 06a — Intent, Orchestrator & Player Canon

## Goal
Turn human text into resolved deterministic turns through a central orchestrator, with
clarification, player-assertion policy, time estimation and turn telemetry — before any AI
actor exists.

## Read
`architecture/03-ai-orchestration.md` §2, §9–§11, §30–§36, §40; `architecture/05-implementation-plan.md` §14;
`specifications/ai-contracts.md` §3–§4; `specifications/communication-and-knowledge.md` §3 (human text);
`specifications/player-authored-canon.md`; `specifications/time-accounting.md` §2;
`specifications/turn-budget-and-latency.md`; `specifications/api-contracts.md` §9–§11, §9a, §23–§25.

## Implement
Intent Interpreter role (with `conveys[]` and `asserted_facts[]`), Entity Resolver Assistant,
deterministic entity resolution, `SessionOrchestrator.process_player_input` steps 1–10 and
14–19 with AI-actor steps stubbed, pending-clarification state, player-canon policy handling,
conversation time bands, `turn_metrics`, streaming `/play` (SSE), degradation ladder skeleton,
Rules Adjudicator role.

## Invariants
Orchestration lives in a service, not route handlers. A clarification commits nothing.
Player assertions become events or proposals per policy, never silent state. Every turn writes
`turn_metrics`.

## Tests
Compound action decomposition, ambiguity → 409 with no partial commit then resumption,
player assertion per class × policy, conversation time events, SSE phase ordering (mechanics
before narration), telemetry presence, adjudicator proposal validation and "no check needed".

## Out of scope
AI Player, NPC Actor, Narrator (plain structured result is shown), memory processing.

## Acceptance
A human can play Frostbridge's deterministic actions by natural language with a fake intent
model; every turn is traced, budgeted and streamed.

## Status
**Done — 2026-10-03.** Acceptance holds: with a fake intent model, Alex plays Frostbridge
by natural language ("I draw my knife, step up to the thief and tell Mira to run" becomes
an ordered move + attack + speech turn); every turn writes `turn_metrics`, is traced per
model call, and streams over SSE with mechanics before narration. Full suite: 238 passed,
2 skipped. Dev DB stays at migration 0009 (no new tables; `pending_clarifications` came in
0005).

- `app/ai/prompts/intent/` (`intent_interpreter_v1`, `entity_resolver_v1`) and
  `app/ai/prompts/dm/rules_adjudicator_v1`; role specs already existed in 05.
- `app/services/turns.py`: `Turn` (budget from settings, per-role call caps, phase timings,
  degradation `LADDER`: drop canon extractor → defer memory → one visible reaction → fallback
  policy in combat → short narrator → skip narrator) and `turn_metrics` persistence.
- `app/services/player_canon.py`: assertion class × campaign policy `TABLE` (personal /
  collaborative / strict): accept as event, refuse with reason, or route to the Rules
  Adjudicator as a proposal; contradictions of known facts are always refused.
- `app/services/orchestrator.py`: `SessionOrchestrator.process_player_input` — channel
  prefixes (`/say`, `/do`, `/ooc`, `/private`), optimistic concurrency (`StaleState` →
  409 `STALE_STATE`), one Intent Interpreter call, **engine-side entity resolution and
  ambiguity detection** (pronoun or descriptor with >1 hostile candidate raises
  `NeedsClarification` → 409 `ACTION_NEEDS_CLARIFICATION`; the open `pending_clarifications`
  row is the only thing written and nothing else commits), resumption by answering (ref,
  name, ordinal, or digit; an unrelated input cancels the open clarification), action
  execution through `ActionService`, conversation time bands and the per-scene talk cap,
  Rules Adjudicator rulings (check required / no check / rejected proposal), telemetry.
  Candidate refs (`a_thief`, `a_thief_2`) are derived from the actor's *perspective* names
  in a deterministic order; the stored clarification resolves by candidate id so a
  re-ordered scene cannot flip the answer.
- `app/api/v1/play.py`: JSON or `text/event-stream` on the `Accept` header; SSE events
  `phase`, `mechanics`, `notice`, then `result` / `error`.
- Bystanders in an encounter (`Encounter.participants` without a side) no longer keep a
  fight alive or count as hostile.

Notes / deviations:
- `Idempotency-Key` (api-contracts §24) is not honoured yet; `X-Request-ID` is echoed.
- Goals/emotions still come from `actors.behavior_profile` (tables arrive in 06b).
- No Narrator yet: `narration` is `None` and the client shows the structured result (06c).
- Entity Resolver Assistant is specced and prompted but never called: deterministic
  resolution plus clarification covered every test case, so the call is kept as a
  reserve for 06b/07 when real inputs show the gap.
