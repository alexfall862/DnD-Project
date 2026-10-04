# Milestone 04b — Model Capability Spike

## Goal
Measure, before building AI infrastructure, whether the configured local model(s) can produce
the structured outputs the architecture assumes, at latencies the budgets assume.

## Read
`specifications/ai-contracts.md` §5 (AI Player), §6 (NPC Actor), §9 (Narrator);
`specifications/communication-and-knowledge.md` §2–3; `specifications/turn-budget-and-latency.md`;
`HARDWARE-TARGET.md`.

## Context
This is a throwaway experiment, not product code. Its output is numbers in `HARDWARE-TARGET.md`
and a go / adjust decision recorded in `DECISIONS.md`. No database, no orchestrator.

## Implement
- `scripts/spike/` with hand-written context packages for: Elara deciding how to respond to
  Alex's whisper (AI Player), Mira being asked about Renn with guards present (NPC Actor),
  Renn lying about Oric (NPC Actor with `deliberate_false`), narrator for the tavern entrance,
  intent parsing of five compound/ambiguous inputs.
- JSON schemas for each output, including `conveys[]`.
- A runner that calls the local endpoint N=50 times per case with the intended profile,
  records: schema-valid rate (raw, and after a single bounded repair), `conveys[]` completeness
  against a hand-labelled answer key, latency p50/p95, tokens, and a quick in-character
  judgement (manual, 10 samples).
- Try structured-output modes the server supports (json_schema / grammar / prompt-only).

## Invariants
Context packages contain only what the role may see (write them by hand against the leakage
matrix). No model output is persisted anywhere but the spike report.

## Tests
None blocking. The report is the deliverable: `docs/spikes/model-capability-YYYY-MM-DD.md`.

## Out of scope
Prompt polishing beyond two iterations per case; cloud providers.

## Acceptance
`HARDWARE-TARGET.md` is filled in with measured numbers. A decision is recorded choosing one of:
(a) proceed as planned; (b) proceed with a simplified `conveys[]`/output schema (documented in
`../specifications/ai-contracts.md`); (c) change the model/serving stack; (d) allow a cloud profile for specific
roles. Milestone 05 does not start until this decision exists.

## Status
**Done — 2026-10-03** (run as a parallel track during Milestone 01, per `DECISIONS.md`).
- Code: `scripts/spike/` (runner, schemas, nine hand-written context packages with answer keys).
- Report: `docs/spikes/model-capability-2026-10-03.md`; numbers in `HARDWARE-TARGET.md`.
- Decision: **(b) proceed with adjustments**, recorded in `DECISIONS.md` with eight findings
  (schema unchanged; `kind` advisory; lexical corroboration of refs; engine-side ambiguity;
  per-role output budgets; one A9 project; embedding endpoint still needed).
- Open: identity of `local-coder`/`local-general`; embedding model before Milestone 04.
