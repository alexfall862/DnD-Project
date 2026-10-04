# Milestone 09 — Campaign Generation

## Goal
Generate new structured campaigns through staged World Author calls.

## Read
`architecture/04-campaign-generation.md` (all); `architecture/03-ai-orchestration.md` §27–§28; `specifications/ai-contracts.md` §13; `specifications/api-contracts.md` §6; `specifications/database-schema.md` §13, §17; `testing/testing-strategy.md` §17.

## Implement
CampaignBrief; GenerationRun/GenerationStage; premise, metaphysics, macro geography, cultures, politics, factions, history, current conflicts, secrets, starting region/settlement/NPCs/opportunities/party/opening scene; latent/established canon; stage regeneration/dependency invalidation; contradiction/rules validation.

## Invariants
Established canon cannot be contradicted. Mystery truth precedes clues. Distant content stays shallow. Generated mechanics use registered primitives.

## Tests
Deterministic FakeModel generation, stage reroll, dependency invalidation, contradiction rejection, mystery/clue validation, generated mechanics validation.

## Acceptance
A non-Frostbridge campaign can be generated and entered as a playable opening scene.
