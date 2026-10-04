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
