# Milestone 05 — AI Infrastructure

## Goal
Build provider-neutral, auditable model invocation and context compilation.

## Read
`architecture/03-ai-orchestration.md` §1, §3–§7, §30–§32, §35–§36, §39–§40, §43; `specifications/ai-contracts.md` §1–§2, §17–§18; `specifications/database-schema.md` §15; `specifications/turn-budget-and-latency.md` §2, §7; `HARDWARE-TARGET.md`; the Milestone 04b decision in `DECISIONS.md`.

## Implement
ModelProvider protocol, FakeModelProvider, LocalOpenAICompatibleProvider, model profile routing, role registry, prompt versioning, ModelRun, ContextSnapshot, ContextItem, DecisionTrace, ContextCompiler, structured-output validation.

## Invariants
Every model call has one declared role and independently compiled authorized context. Provider-side conversation memory is never authoritative. Unauthorized ContextItems abort in development.

## Tests
Fake provider deterministic calls, structured validation failure, authorization failure, context source audit, local provider smoke test.

## Out of scope
Full AI gameplay/worldgen.

## Acceptance
A model can receive an audited Elara context containing exactly what Elara should know, with no global-world leakage.

## Status
**Done — 2026-10-03.** Acceptance holds: Elara's compiled context contains her beliefs, her
relationship rows, her names for people (Lady Veyra), her core and retrieved memories, her
own sheet and her inventory's public side — and none of the mystery truth, Alex's name for
Veyra, Tomas's beliefs, hidden item lore, or a name for Renn she has not learned. Every
ContextItem is `allowed`/`public`; a forged item owned by another actor aborts the call and
is recorded as `denied` on the stored snapshot. (`tests/integration/test_context_compiler.py`)

- Migration `0009_ai_observability`: `context_snapshots`, `context_items` (owner +
  authorization per item), `model_runs` (prompt id/version/hash, model requested vs echoed,
  raw + structured output, validation, tokens, latency), `decision_traces`, `turn_metrics`.
- `app/ai/providers.py`: `ModelProvider` protocol; `A9Provider` (unique `run_id` first line
  defeats A9 sessions, `json_object` mode, no client tools, model-echo verification, 503
  Retry-After and 409 wait-not-substitute, concurrency semaphore = 2, SSE streaming);
  `FakeModelProvider` (role-keyed fixtures, queues, responders, injectable latency).
- `app/ai/roles.py`: 14 role specs (profile, prompt, allowed/forbidden context sections,
  Pydantic output model, output budget, temperature, authority). `conveys[]` items carry
  `contradicts_ref`; the engine derives deliberate falsehood (04b finding).
- `app/ai/prompts/` + `prompts.py`: versioned prompt files with YAML headers, hashed per
  ModelRun; system text = `# role:` line + common rules + role body + a **compact** schema
  skeleton (the full JSON schema cost ~4k prompt tokens; the skeleton ~330).
- `app/ai/routing.py`: role → profile → model with campaign overrides.
- `app/ai/context.py`: `ContextCompiler` — actor-scoped sources only (perspective service,
  memory retrieval), per-item owner + authorization audit, role section filter, profile
  token budget with volatile-first trimming, stable-prefix-first rendering (identity,
  behaviour, known names, sheet, core memories, goals, relationships … scene, observations,
  situation) so A9's prefix cache hits, `ref_map` of `b_`/`f_` short ids the model may cite.
  Added to the repository-boundary invariant (never imports objective code).
- `app/ai/runner.py`: `ModelRunner.run` (one audited call, lenient JSON + conveys
  normalisation + Pydantic validation, one bounded repair that knows when output was
  truncated) and `.stream` for prose roles; DecisionTrace for actor roles.
- Real-model smoke (`tests/eval/test_runner_a9.py`): Elara answers the whisper in one call,
  valid JSON, 15 s, 1,381 prompt tokens, refs inside her context, model echo verified.

Notes / deviations:
- Actor-role output budgets raised 260 → 400 tokens: GLM's first smoke run was cut off at
  260 on both attempts. `ai-contracts.md` §21 table should read 400 for ai_player/npc_actor.
- Goals/emotions are read from `actors.behavior_profile` until the goals/emotions tables
  arrive in 06b.
