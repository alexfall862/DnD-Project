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
