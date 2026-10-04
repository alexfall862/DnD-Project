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

## Status
**Done — 2026-10-03.** Acceptance holds: Alex, Elara, Tomas and Mira play a narrated tavern
turn with different private knowledge, inside the call budget, and the scene-end checkpoint
leaves Elara with a memory of the whisper and Tomas with none
(`tests/integration/test_narration_and_memory.py`). Full suite green. Dev DB at 0011.

- Narrator (`app/services/narration.py`): a `NarrativeBundle` is built from the focus actor's
  own Observations for this turn (rendered with that actor's names), the dialogue they heard
  verbatim, the mechanics they can see, a perspective-safe scene line and the campaign's
  `narration_style`; the narrator is a **prose** role now (streamed verbatim as
  `narration_delta`; `ms_to_first_narration_token` recorded). Failure or a skipped narrator
  falls back to the plain structured result. Narration is never written anywhere but the
  response and its ModelRun.
- SSE order per api-contracts §9a: `accepted` → per-action `mechanics` → `speaker` (each
  validated AI line the focus actor could hear) → summary `mechanics` → `narration_delta`* →
  `complete`.
- Spotlight governor (`app/engine/spotlight.py`): per-scene ledger reset on every human input;
  `max_visible_ai_turns` (3), `max_ai_to_ai_exchanges` (1), `max_unsolicited_initiatives` (2)
  from `campaign.settings.spotlight`. Over-budget reactions are **compressed**: no call, no
  transcript line, a one-line count handed to the narrator ("2 other(s) present react
  quietly"). One bounded AI-to-AI second wave when an AI line addresses another AI actor.
  Combat override: initiative turns are not capped.
- Canon Extractor + allowlist validator (`app/engine/canon.py`): classes furnishing /
  condition / appearance / extra / availability; items, topology, history/secrets/motives,
  mechanics fields, absent entities and duplicates are rejected by code with a logged reason.
  Accepted details are stored `latent` on `location.properties.features[]` or
  `entity.metadata.latent_descriptors[]` with a `canon.detail_added` event; a later `do`
  input that names one promotes it (`canon.detail_established`).
- Memory processing (`app/services/memory_processing.py`): checkpoints at combat end and rest
  (in-turn, background budget) and at `SessionOrchestrator.end_scene`; one Memory Processor
  call per AI actor with new observations since its last checkpoint (window ids `o_xxxx`);
  every memory must cite that actor's own observations (lineage enforced by MemoryService,
  the window is the fallback lineage); belief/emotion proposals bounded as in 06b;
  `memory.checkpoint` events, deferral queued on the scene.
- Journal Writer for human actors at checkpoints → `journal_entries` (migration 0011) with
  the event sequence range; encyclopedia is a deterministic, rebuildable projection of
  identity knowledge + beliefs grouped by belief type. `GET /characters/{id}/journal`,
  `GET /characters/{id}/encyclopedia[?category=]`, `GET .../encyclopedia/{entity_id}`
  (focus-actor rule; knowing an id grants nothing).
- Degradation ladder complete: 1 drop canon extractor, 2 defer memory processing, 3 one visible
  reaction, 4 combat fallback policy, 5 short narrator prompt ("resolve in two sentences"),
  6 skip narrator; `budget_breached` reported consistently.
- Intent Interpreter: the model's `requires_clarification` is advisory (logged); GLM flagged
  an unambiguous "ask Mira quietly" on A9. Model target refs are matched leniently
  (`"Mira"`, `"Captain Renn"` → candidate refs).

Notes / deviations:
- `NarratorOut` is no longer used: decoration comes only from the separate Canon Extractor
  pass (ai-contracts §9 "optional incidental_detail_candidates" is superseded by §10).
- Medium-significance reactions still get no "internal state only" call.
- Background extras (allowlist "extra") are stored as location features, not as background
  NPC seeds; actors are never created by extraction.
- `SPOTLIGHT_VISIBLE_REACTIONS` and `NARRATOR_ENABLED` settings exist so earlier-milestone
  tests stay narrator-free; both default on.
