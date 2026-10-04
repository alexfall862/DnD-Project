# Milestone 06c — Narration, Governor & Memory Processing

## Goal
Human-facing narration that follows resolution, bounded AI-to-AI activity, and the memory
pipeline that gives actors durable subjective recall.

## Read
`architecture/03-ai-orchestration.md` §13–§15, §21–§24, §29; `specifications/ai-contracts.md` §9–§11, §15;
`specifications/canon-extraction-allowlist.md`; `specifications/observation-authoring.md` §5–§6;
`specifications/human-visibility.md` §6; `specifications/turn-budget-and-latency.md` §4–§6.

## Implement
Narrator role (streamed) with NarrativeBundle from the focus actor's rendered observations,
NPC/AI-PC dialogue rendered as distinct speakers, Spotlight Governor with configurable budgets
and combat overrides, background compression of incidental AI-to-AI exchanges, Canon Extractor
with allowlist validator, Memory Processor at checkpoints (scene end, significant event,
rest), Journal Writer, encyclopedia projection, degradation ladder completed.

## Invariants
Narration cannot mutate state or reveal excluded facts; narration text is never an
Observation source. Extractor output is validated structurally against the allowlist.
Memory derives from the actor's observations and heard dialogue only.

## Tests
Narrator fidelity against resolved events (fixtures with tempting contradictions); spotlight
limits in a crowded scene; disallowed extractor candidate rejected / allowed one stored
`latent`; Elara memory of the whisper exists, Tomas has none; journal reflects Alex's
misconception; degradation ladder steps logged under an artificial time budget.

## Out of scope
World simulation, worldgen, UI.

## Acceptance
Milestone 06 acceptance from v0.1: Human + Elara + Tomas + NPC conduct a coherent narrated
scene with different private knowledge, within the call budget, with memories recorded.
