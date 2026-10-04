# Turn Budget, Latency & Telemetry v0.2

## 1. Purpose

The architecture can be entirely correct and still produce an un-fun game if a player turn
takes a minute. This document sets explicit budgets, a degradation ladder, the telemetry that
proves whether budgets are met, and a hardware target the routing profiles must be sized
against. It applies from the first orchestrator commit (Milestone 06a), not at polish time.

> **A turn has a time budget and a call budget before it has a prompt.**

## 2. Hardware target (fill in before Milestone 04b)

Routing profiles are abstract on purpose, but the plan needs a concrete floor. The single
canonical record of the inference host and measured profile numbers is `../HARDWARE-TARGET.md`;
this section no longer duplicates its YAML. Keep that file current.

Planning assumptions until measured: one GPU; model swaps cost seconds and are avoided within
a turn; "concurrent" inference calls to the same local model **serialize** (or batch, if the
server supports it). The orchestration DAG remains correct either way; only wall time changes.
If `fast_structured` and `balanced_reasoning` are different models that cannot be co-resident,
the orchestrator groups calls by profile within a turn to minimise swaps.

## 3. Budgets (defaults; campaign-configurable)

| Measure | Target | Hard cap |
|---|---|---|
| Time to first visible output (acknowledgement/mechanics) | ≤ 2 s | 5 s |
| Time to first narration token, simple turn (no AI reactions) | ≤ 12 s | 20 s |
| Time to first narration token, complex turn (AI reactions, adjudication) | ≤ 25 s | 40 s |
| Combat round (human + 2 AI PCs + 2 NPCs) wall time | ≤ 40 s | 75 s |
| Synchronous model calls per player turn | ≤ 4 | 6 |
| Background model calls queued per player turn | ≤ 3 | 6 |
| Compiled context per call | ≤ 4k tokens (`fast_structured`), ≤ 8k (others) | profile ctx − output budget |
| Context growth over a 50-turn session | flat (±20 %) | — |

Combat caps count all AI-controlled combatants together; fallback policies (§5) exist to keep
rounds under budget.

**Revised 2026-10-03** for the measured hardware (GLM-4.5-Air at ≈ 22.5 tok/s, concurrent calls
serialize; `DECISIONS.md` "Latency budgets revised"). The original targets (6 / 15 / 20 s)
assumed a faster model. The first-output target is unchanged because mechanics are streamed
before narration. Acceptance in §8 and Milestone 11/13 gates use these numbers.

## 4. Call plan for one player turn

Target sequence for a typical social turn:

1. deterministic preprocessing, intent syntax (0 calls);
2. Intent Interpreter — only when text is not an explicit structured action (1 call, fast);
3. mechanics (0 calls); Rules Adjudicator only when no rule covers the action (0–1, balanced);
4. reactions: eligibility + significance scoring is deterministic; **at most two** visible
   AI reaction calls per turn by default (`spotlight_visible_reactions` tunable, 1–2). The two
   run **concurrently** from the same scene snapshot: measured, two parallel calls cost ≈ 1.5x
   one call (≈ 16 s for two 260-token reactions vs ≈ 24 s sequential). Effective hardware
   concurrency is 2 (`HARDWARE-TARGET.md` re-probe); more reactions queue. Other eligible
   reactions update silently with no call, lowest significance dropped first;
5. Narrator (1 call, creative, **streamed**);
6. background: Claim Extractor fallback (0–1), memory processing (0–1 at checkpoints),
   canon extractor (0–1, only when narration contained unstructured flavor), embeddings.

Typical: 2–3 synchronous calls. Worst ordinary case: 5. Anything above the hard cap aborts the
remaining optional calls and logs a budget breach.

## 5. Degradation ladder

When the elapsed-time budget is at risk the orchestrator degrades in this order, logging each
step on the turn record:

1. drop Canon Extractor for this turn;
2. defer memory processing to the next checkpoint;
3. reduce visible AI reactions from 2 to 1 (lowest significance dropped; its state update
   is done silently with no call);
4. in combat, use the actor's recorded **fallback policy** instead of a fresh AI Player call
   when the situation is unchanged (same target alive and reachable, HP above threshold);
5. use a shorter narrator prompt ("resolve in two sentences");
6. skip the narrator and render the plain structured result (PROMPT.md error philosophy).

Nothing on the ladder ever invents or skips authoritative state.

## 6. Streaming

`/play` supports server-sent events (see `api-contracts.md` §9a). The orchestrator emits:
`accepted` → `mechanics` (visible rolls, authoritative state deltas, versions) →
`speaker` (AI PC/NPC lines as they are validated) → `narration_delta` (token stream) →
`complete` (turn metrics). The frontend renders mechanics before narration so the player sees
*what happened* within the first-output budget even when narration is slow.

## 7. Telemetry schema

Table `turn_metrics` (one row per `turn_id`):

- `campaign_id`, `timeline_id`, `turn_id`
- `wall_ms_total`, `ms_to_first_output`, `ms_to_first_narration_token`
- `sync_model_calls`, `background_model_calls`, `calls_by_role JSONB`
- `prompt_tokens_total`, `completion_tokens_total`, `max_context_tokens`
- `degradation_steps JSONB`, `budget_breached BOOLEAN`
- `claim_extractor_invoked`, `belief_processor_scheduled` (ints)
- `created_at`

`GET /debug/campaigns/{id}/turn-metrics?limit=` returns recent rows; the Debug UI shows a
sparkline of wall time and calls per turn. `make eval-local` reports p50/p95 per scenario.

## 8. Acceptance (added to Milestone 11 and 13 gates)

- Frostbridge scripted path with the configured local model: p95 time-to-first-narration ≤ hard
  cap on every turn; p50 ≤ target on social turns.
- Combat fixture (§30 Frostbridge): p50 round time ≤ 20 s.
- Context size on turn 50 of the stress campaign within ±20 % of turn 5.
- Zero turns exceed the synchronous call hard cap without a logged degradation.
