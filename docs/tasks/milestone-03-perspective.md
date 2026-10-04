# Milestone 03 — Perspective & Knowledge Isolation

## Goal
Implement objective truth and independent actor perspectives before AI companions are trusted.

## Read
`architecture/01-world-memory.md` §5–§9, §18; `specifications/database-schema.md` §11, §21; `specifications/communication-and-knowledge.md` §4, §6–§7 (deterministic parts); `specifications/belief-update-rules.md` §2–§6; `specifications/observation-authoring.md` §2–§3; `specifications/human-visibility.md` §2–§4; `testing/knowledge-leakage.md`.

## Implement
Fact, Claim, Observation, Belief, EntityIdentityKnowledge, audibility, visibility, language comprehension, speech pipeline, whispering, perspective-safe scene/entity queries, PerspectiveService.

## Invariants
Facts do not automatically become knowledge. Speech creates Claims, not Facts. Party membership does not synchronize knowledge. Actor context code never reads objective-world repositories directly.

## Tests
Private whisper, split party, secret identity, hidden item property, unknown language, invisible actor, mystery truth, direct UUID probing.

## Note on `conveys[]`
The Intent Interpreter that derives `conveys[]` from human text does not exist until
Milestone 06a. In this milestone the speech pipeline accepts `conveys[]` supplied
structurally by the caller (tests and fixtures use `conveyance_source = fixture`; the
deterministic `/play` path may accept it as `player_text`). The whisper gate is therefore
tested with hand-written `conveys[]`, not natural language.

## Out of scope
Semantic memory, AI model calls, natural-language `conveys[]` extraction.

## Acceptance
Alex can privately tell Elara something; Elara can retrieve it; Tomas is technically unable to retrieve it through APIs, PerspectiveService, or context candidates.

## Status
**Done — 2026-10-03. The whisper gate passes:** Alex whispers to Elara; Elara's belief store
gains exactly the rows in `communication-and-knowledge.md` §8 (`Alex asserted P` known 1.0,
`Mira involved` suspected 0.585 with the seeded trust/familiarity); Alex gains `stated 0.55`;
Tomas and Mira have no Observation, no heard Claim, no belief, and nothing in their context
candidates — through `PerspectiveService`, the normal API (403 for non-focus actors), and
after Tomas walks out and back in. (`tests/leakage/test_knowledge_leakage.py`)

- Schema: migration `0007_knowledge_relationships` — `facts` (with `key`, `sensitivity`),
  `claims` (speaker-private `deliberate_false`/`fidelity`/`source_*`), `observations`,
  `beliefs` (+ `proposition_key`), `entity_identity_knowledge`, `relationships`,
  `relationship_deltas` (pulled forward from 0008 because testimony confidence needs trust).
- `app/engine/beliefs.py`: belief-update rules §3–§7 as pure functions (worked Frostbridge
  values in `tests/rules/test_beliefs.py`).
- `app/persistence/repositories/`: `PerspectiveRepository` (actor-scoped; never selects
  `truth_status`, `canon_status`, `deliberate_false`, `fidelity`, `source_*`,
  `hidden_properties`) vs `ObjectiveWorldRepository`. `tests/invariants/test_repository_boundary.py`
  scans the perspective code for forbidden imports/columns.
- `app/services/knowledge.py`: facts (`known_by` seeds the holders' `known` beliefs), identity
  knowledge, relationships with event-linked deltas, the single `store_belief` path applying
  §5 reconciliation (supersede / contested / weaker alternative / observation beats testimony).
- `app/services/speech.py`: `conveys[]` authorization against the speaker's perspective
  (violations → `proposal.rejected_leakage` event + `LeakageError`, no Claim), Claims,
  speaker `spoke` observation, human speaker self-belief, per-recipient audibility (say /
  whisper targets / `hear:whispers` capability within engaged-or-close), language gate
  (`speech_in_unknown_language`), `heard_claim` observations, meta-belief + testimony belief.
  Ledger payloads carry no text; verbatim text lives in `transcript_messages`.
- `app/services/observations.py`: template-generated `Observation.raw` per observer
  (observer-visible vs participant-only fields, `known_as` per identity knowledge, hidden
  actors unseen by non-detectors), pure `render()`; wired into `ActionService._commit`.
- `app/services/perspective.py` + `app/api/v1/perspective.py`: `scene`, `inventory`,
  `beliefs` for the human focus actor only; `entity_view` gives nothing for a bare id;
  `context_candidates` is the Milestone 05 input. `app/api/v1/debug.py`: facts, actor
  perspective, perspectives/compare, claims, events — gated by `DEBUG_MODE`. Error envelope
  + `X-Request-ID` (`app/api/errors.py`).

Notes / deviations:
- `conveys[]` is supplied structurally (`conveyance_source` fixture/structured/player_text);
  the Intent Interpreter (06a) and Claim Extractor (06b) will feed the same `utter()`.
- Detection of hidden actors (`scene.state.detected`) is recorded but nothing sets it yet;
  Awareness-vs-Stealth detection lands with social/exploration actions in 06a.
- Clue discovery by testimony (c&k §6) waits for `clues` (Milestone 07).
