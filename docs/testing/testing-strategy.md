# Testing, Replay & Evaluation Strategy v0.2

## 1. Why this project needs unusual testing

Ordinary application correctness is not enough. The most dangerous failures are architectural: actors learning hidden facts, narration mutating state, memory losing provenance, speech becoming truth, AI supplying randomness, concurrent decisions creating duplicate/impossible state, mystery solutions shifting, context growing without bound, or AI-to-AI loops sidelining the human.

Treat these as first-class release-blocking defects.

## 2. Test layers

Maintain six primary layers:

1. unit tests;
2. domain integration tests;
3. end-to-end gameplay tests;
4. knowledge-leakage tests;
5. deterministic replay tests;
6. long-run/stress evaluation.

Real-model evaluation is separate from deterministic CI.

## 3. Unit tests

Focus on deterministic components:

- safe expression evaluator;
- dice parser and seeded reproducibility;
- modifiers and derived stats;
- resources and conditions;
- trigger limits/cycle validation;
- action state transitions/decomposition;
- effect validation;
- ruleset loading/references;
- entity-resolution helpers;
- audibility/visibility/language comprehension;
- time/calendar conversion;
- event ordering/world-version allocation;
- belief-update rules (`../specifications/belief-update-rules.md` tables);
- observation templates and rendering purity;
- conversation time bands and the scene conversation cap;
- player-assertion classification × policy table;
- canon-extraction allowlist validator.

No model provider required.

## 4. Domain integration tests

Exercise several deterministic systems together, e.g. attack → roll → damage → condition → events; whisper → audibility → observation → belief; item transfer → possession → history; time advance → scheduled event → state; location change → visibility/perspective; document discovery → knowledge → encyclopedia.

Use real PostgreSQL behavior for important integration tests rather than replacing persistence with large mocks.

## 5. FakeModelProvider

Most AI orchestration CI tests use deterministic fixture responses. Example concept:

```python
fake.register(role="npc_actor", fixture="renn_denies_oric")
```

This enables exact assertions around model orchestration/state without stochastic language behavior.

## 6. Real-model evaluation suite

Optional/manual command such as `make eval-local` runs behavior suites against configured local models. Score/report rather than exact-string assert:

- intent accuracy;
- schema compliance;
- character consistency;
- NPC deception quality;
- narrator fidelity;
- memory usefulness;
- world-author consistency;
- illegal-action proposal rate;
- leakage rate (including proposition leakage, `knowledge-leakage.md` §20);
- `conveys[]` completeness against hand-labelled keys;
- Claim Extractor fallback rate;
- latency/tokens per role and per turn (p50/p95 against `../specifications/turn-budget-and-latency.md` §3).

## 7. Architectural invariant suite

Create `tests/invariants/` containing at least:

- all state mutations have events;
- established canon immutable;
- mystery truth locked;
- no LLM randomness;
- generated effects registered;
- relationship changes have provenance;
- controller changes preserve actor;
- document text immutable;
- memory lineage preserved;
- narrator cannot directly mutate world.

These should remain permanent regression tests.

## 8. Replay suite

Create `tests/replay/`.

### Mechanical replay

Same starting state + ruleset snapshot + recorded proposals + dice seeds must produce the same mechanical final state.

### Renarration

Same authoritative events can be passed to a different narrator/style; world state must remain unchanged.

### AI reevaluation

Optional debug mode can rerun actor decisions from the same starting snapshot, but the result should create a new timeline branch rather than rewrite history.

## 9. State hashing

For replay comparison, normalize/hash resources, conditions, locations, item ownership/possession, goals, relationships, facts, beliefs, clue state, and world clock. Ignore insertion timestamps, model latency, and non-authoritative debug metadata.

## 10. Concurrency tests

Example: Elara and Tomas both decide from Scene Version 20 to pick up the same dagger. Elara commits first, scene becomes 21; Tomas action must revalidate and fail/use fallback. It must never duplicate the item.

Test conflicting item transfers, target death before later initiative, simultaneous reactions, and stale model proposals.

## 11. Transaction failure tests

Force exceptions between event creation and projection updates (and vice versa). Whole transaction must roll back. No orphan event or unexplained projection mutation is allowed.

## 12. Trigger-loop tests

Construct mutually recursive trigger definitions such as on_damage → heal and on_heal → damage. Validator should reject or engine should halt at hard trigger-depth/effect-budget boundary.

## 13. Spotlight tests

Create a crowded scene with one human, several AI PCs, and NPCs. Trigger emotionally relevant conversation and verify visible AI exchanges obey configured limits, background chatter is compressed, and human regains control.

Also test that a high-priority goal can legitimately trigger proactive companion behavior while irrelevant impulses remain silent.

## 14. Memory tests

Create actors with 1,000+ memories. Verify relevant semantic/entity/goal memories are retrieved, core memories receive priority, unrelated recent items do not always dominate, and unauthorized memories never enter the candidate set.

Compression test: detailed memories remain preserved and linked when a summary memory is created; broad queries may prefer the summary while specific historical queries can still retrieve originals.

## 15. Long-run synthetic campaign

Initial target:

- 50 sessions;
- 10,000 events;
- 1,000 memories;
- 100 important actors;
- 1,000 minor actors;
- 10 factions;
- 5 mysteries.

Later target: 500 sessions / 100k+ events.

Measure context token size, perspective-query latency, memory-search latency, event-query latency, model calls per turn, and background backlog.

Quality assertions: old core events remain retrievable; irrelevant history stays out of context; mysteries remain locked; leakage remains zero; reload matches pre-shutdown state.

## 16. Ruleset tests

Each ruleset package ships fixtures. Core Adventure covers attribute/resource derivation, Defense, simple/opposed checks, margins, initiative, movement, attack/damage/cover, conditions, rest/healing, advancement, and generated effects.

Generated-mechanics validator tests should reject unknown effects/resources, circular triggers, invalid targets/durations, arbitrary code, missing definitions, and unbounded recursion. Intentionally overpowered but structurally valid content should produce a balance warning rather than automatic rejection.

## 17. Campaign generation tests

Use FakeModelProvider to return deterministic generation stages. Verify dependency invalidation/regeneration, reference validation, established-canon contradiction detection, mystery truth before clues, clue redundancy, deep starting-region materialization, and shallow distant content.

## 18. World simulation tests

Test scheduled caravan arrival, Renn evidence destruction, shipment plan advancement, NPC travel, quarry clock, and revalidation after player interference. If Renn is arrested before his scheduled action, he cannot execute it anyway.

## 19. Save/reload gate

Before shutdown create private beliefs, memories, relationships, unique item/hidden property, goal, condition, scheduled event, and partially solved mystery. Reopen app/database connections and verify exact persistence, then continue play successfully.

## 20. Frontend integration

Test campaign creation, character creation, campaign start, normal play turn, explicit whisper, sheet/inventory, journal/encyclopedia, and debug-trace expansion. UI must never infer state from narration.

## 21. API boundary tests

Normal endpoints remain perspective-safe even when callers know raw entity IDs. Knowing Renn's entity UUID does not grant `Renn killed Oric` through encyclopedia/entity endpoints.

## 22. Evaluation metrics

Track structured-output validity, intent accuracy, unauthorized-fact leakage, illegal-action proposal rate, narrator contradiction rate, actor-consistency rating, memory usefulness, world-author contradiction rate, latency, token counts, and model-call counts.

Known leakage target: zero tolerated cases.

## 23. Model comparison harness

Run the same evaluation fixtures against different local/provider models and produce role-specific reports so model routing can be empirically tuned.

## 23a. Latency and budget tests

Deterministic (FakeModel with injected delays): the degradation ladder engages in order under
an artificial budget; synchronous call hard cap is never exceeded without a logged
degradation; `mechanics` SSE event precedes any `narration_delta`; `turn_metrics` rows exist
for every turn.

Real model (`make eval-local`): Frostbridge scripted path and combat fixture report p50/p95
time-to-first-narration and calls per turn; Milestone 11/13 gates use these numbers.

## 23b. Playtest loop

Not automated. `testing/design-iteration.md` defines the rubric, cadence and journal that
feed eval fixtures and tunable changes from Milestone 06d onward.

## 24. Commands

Recommended Make targets:

- `make test`
- `make test-unit`
- `make test-integration`
- `make test-invariants`
- `make test-leakage`
- `make test-replay`
- `make test-rules`
- `make test-worldgen`
- `make test-stress`
- `make eval-local`
- `make test-latency`
- `make play` (CLI harness, `tasks/milestone-06d-cli-play-harness.md`)

## 25. Vertical-slice release gate

Do not broaden product scope until invariant tests, leakage tests (including `conveys[]` authorization), Frostbridge scripted integration, save/reload, mechanical replay, local-model smoke scenario within latency budget, debug-trace auditability, bounded-context assertions, and three consecutive playtest sessions meeting the design-iteration exit criteria all pass.

## 26. Testing doctrine

The project should continuously prove:

> Any actor may be wrong, deceived, ignorant, mistaken, forgetful, or privately informed while objective world truth remains coherent and auditable.

That property matters more than impressive prose.
