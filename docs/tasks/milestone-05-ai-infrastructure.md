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
