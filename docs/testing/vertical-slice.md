# Vertical Slice Acceptance Scenario v0.2

## Goal

Prove the architecture works end-to-end before adding broad feature scope.

## Preconditions

- PostgreSQL migrations current.
- Core Adventure rules installed and validated.
- Frostbridge fixture seeded.
- FakeModelProvider supports deterministic path.
- Local model can optionally be used for smoke testing.

## Scripted path

### 1. Load Frostbridge

Verify campaign/timeline/world clock/opening scene and Alex/Elara/Tomas party.

### 2. Enter Red Lantern

Scene transition creates events/projections/observations; narrator receives only authorized local context.

### 3. Ask Mira about Oric/Renn

Mira uses her actual knowledge plus fear context and gives an evasive/partial answer. Speech becomes a Claim/event, not objective world truth.

### 4. Private whisper

Alex tells Elara a suspicion about Mira/Renn. Verify Tomas and Mira cannot retrieve content unless a legitimate hearing mechanic applies. Verify the exact belief rows for Alex and Elara per `../specifications/communication-and-knowledge.md` §8.

### 5. Companion disagreement

Tomas may defend official process; Elara may express skepticism. Their responses derive from their own goals/beliefs/relationships and remain spotlight-limited.

### 6. Split party

Alex + Elara go to Oric's Warehouse. Tomas goes to Guard House.

Maintain separate scenes/observations. The warehouse scene is live; the Guard House scene is offscreen and catches up per `../specifications/time-accounting.md` §4. The human client (focus actor Alex) receives nothing from the Guard House scene.

### 7. Warehouse discovery

Alex/Elara can find merchant ledger and Veyra's Chipped Dagger. Dagger's hidden spirit property remains absent from their knowledge/UI.

### 8. Guard House discovery

Tomas discovers missing log anomaly. Alex/Elara do not know it yet.

### 9. Warehouse combat

Run two-thief theater-of-the-mind encounter:

- initiative;
- movement bands;
- attacks/damage;
- AI companion turns;
- reaction;
- surrender/flee possibility;
- one environmental improvisation (shelf/table/lantern/window/crates).

All rolls programmatic and reproducible.

### 10. Persistent environment

If something was burned/moved/broken, verify it remains changed after encounter/scene transitions.

### 11. Rejoin party

Before anyone talks, assert knowledge remains asymmetric.

### 12. Exchange discoveries

Characters communicate ledger/log information. Verify recipient-specific observations/beliefs/memories update through actual communication.

### 13. Question Renn

Renn knowingly lies. Store private deception metadata and public Claim separately, with `conveys[]` provenance. Different PCs may interpret the same statement differently per `../specifications/belief-update-rules.md` §4–§6.

### 14. Advance four fictional days

Process Day +2 caravan, Day +3 evidence destruction, River Compact plan progression, and quarry clock. Revalidate prerequisites if player actions changed state.

### 15. Memory checkpoint

Elara should have at least one meaningful subjective memory related to Alex's trust/private conversation; Tomas must not share it.

### 16. Shutdown/restart

Terminate application process, reopen connections/server, reload campaign.

### 17. Persistence assertions

Verify:

- locations/scene state;
- Health/resources/conditions;
- item possession/history;
- hidden item mechanics still hidden;
- facts/claims/beliefs;
- actor identity knowledge;
- relationships/deltas;
- goals/plans;
- memories/source lineage;
- mystery/clue states;
- scheduled-event processing/world clock;
- model/context audit records;
- `turn_metrics` for every turn, with p95 time-to-first-narration within the hard cap when run against the real model.

### 18. Continue naturally

Submit another player input after reload. Campaign continues without reconstructing a giant historical conversation.

## Debug acceptance

For at least one complex turn, debug UI/API must answer:

- what player intended;
- which entities resolved;
- which rules were consulted;
- what dice rolled;
- what state changed;
- which events committed;
- who observed what;
- which beliefs/memories changed;
- what exact ContextSnapshot each AI received;
- what AI intent was proposed/rejected;
- why narrator output had the information it did.

## Release gate

Vertical slice is not complete unless invariant/leakage suites (including `conveys[]` authorization), deterministic replay, save/reload, and local-model smoke test all pass with bounded context size and within the `../specifications/turn-budget-and-latency.md` budgets, and the CLI harness can play the path end to end.
