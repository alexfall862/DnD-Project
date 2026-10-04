# Milestone 13 — v0.1 Stabilization

## Goal
Ship the first personally usable local release after architecture is proven.

## Read
`testing/vertical-slice.md`; `testing/testing-strategy.md` §25; `specifications/turn-budget-and-latency.md` §8; `testing/design-iteration.md` §7; `DECISIONS.md` (event payload versioning stance).

## Required gates
- all unit/integration/invariant/leakage tests pass;
- Frostbridge integration passes;
- deterministic mechanical replay passes;
- save/reload/stress passes;
- configured local model completes smoke scenario;
- debug trace explains complex turns;
- model-call counts/context sizes are acceptable;
- README/setup scripts are reproducible;
- recoverable AI failures do not corrupt state.

## Review
Error handling, performance instrumentation, prompt versions, migration stability, API/OpenAPI, UI debug ergonomics, provider routing, backup/export path.

## Explicitly out of scope
Voice, generated art, native mobile, real-time multiplayer, huge rules/content catalogs, marketplace, arbitrary executable plugins, deep continuous economy.

## Acceptance
A human can play multiple persistent sessions with independent AI companions/NPCs while world truth, mechanics, knowledge, memory, and history remain coherent and auditable.
