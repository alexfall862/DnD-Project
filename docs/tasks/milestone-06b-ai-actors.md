# Milestone 06b — AI Players & NPCs

## Goal
Independent AI-controlled PCs and NPCs that act through proposals, speak with structured
information content, and keep deception private.

## Read
`architecture/01-world-memory.md` §4, §7, §11–§12; `architecture/03-ai-orchestration.md` §8, §12,
§16–§20, §34; `specifications/ai-contracts.md` §5–§7, §12; `specifications/communication-and-knowledge.md`;
`specifications/belief-update-rules.md`; `specifications/observation-authoring.md` §3;
`specifications/database-schema.md` §11–§12.

## Implement
BehaviorProfile, AutonomyProfile and enforcement gates, goals/plans, relationships + deltas,
emotion states, AI Player role, NPC Actor role, NPC Tactical Controller (minimal) with fallback
policies, `conveys[]` production and authorization check, Claim Extractor fallback, Belief
Processor gating, reaction eligibility + significance scoring, concurrent decision snapshots
and stale-proposal revalidation, private intentions.

## Invariants
AI returns intentions, never outcomes. Every `belief_ref`/`fact_ref` in `conveys[]` is in the
speaker's perspective or the proposal is rejected. Deception flags never reach recipients.
Autonomy gates are enforced in code. Relationship changes carry event-linked deltas.

## Tests
AI independent choice vs. fixture; NPC evasion/lie with Claim-not-Fact; `conveys[]`
authorization rejection; Claim Extractor invoked only on fallback; belief outcomes for the
Frostbridge whisper per `../specifications/communication-and-knowledge.md` §8; autonomy pause; two actors
targeting one dagger with revalidation; fallback policy used when situation unchanged.

## Out of scope
Narration prose, spotlight governor, canon extraction, world simulation.

## Acceptance
Human + Elara + Tomas + Mira + Renn conduct the Frostbridge tavern scene with FakeModel: each
actor's belief store after the scene matches the expected table exactly.
