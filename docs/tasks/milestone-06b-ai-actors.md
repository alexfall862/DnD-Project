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

## Status
**Done — 2026-10-03.** Acceptance holds: with FakeModel fixtures, Alex, Elara, Tomas, Mira and
Renn play the tavern scene (Mira's partial account, the whisper, Tomas defending the guard,
Renn's lie) and every actor's belief store afterwards matches the expected table exactly
(`tests/integration/test_ai_actors.py::test_tavern_scene_belief_stores_match_the_expected_table`).
Full suite: 257 passed, 2 skipped. Dev DB migrated to 0010.

- Migration `0010_actor_psychology`: `actor_ai_profiles` (autonomy, decision/tactical
  preferences), `emotion_states`, `goals`, `goal_targets`, `plans`; models in
  `app/persistence/models/psychology.py`. Events: `goal.created/updated`, `emotion.changed`,
  `relationship.changed`, `belief.formed`, `belief.adjusted`, `proposal.invalidated`,
  `autonomy.paused`.
- `app/engine/autonomy.py`: per-domain levels (`blocked|suggest_only|ask|autonomous`), action →
  domain classification, `gate()`; enforced in code after generation.
- `app/engine/reactions.py`: eligibility + significance (direct target, asked, danger, goal
  relevance, relationship, new information, novelty, emotion, importance, scene importance) →
  `high` (model call) / `medium` (silent, noted) / `low`.
- `app/engine/tactics.py`: `FallbackPolicy` (stored per combatant on the scene),
  `situation_unchanged`, deterministic `choose_action` (attack if reachable → close in → step
  along the route → cover → wait; flee below the health threshold) and a behaviour-driven
  `ReactionChooser` for combat reaction windows (defend / opportunity attack / protect).
- `app/services/psychology.py`: goals, emotions, AI profiles, `apply_relationship_delta`
  (always a `relationship.changed` event + `relationship_deltas` row, caused by the triggering
  event when there is one).
- `app/services/ai_actors.py` (`AIActorService`): reaction selection bounded by the spotlight
  budget; decisions for several actors compiled from one scene snapshot and generated
  concurrently (`ModelRunner.run_many`; DB work stays sequential); applied one at a time with
  revalidation (`proposal.invalidated` + nearest-hostile fallback when a target is gone or an
  item was taken); `conveys[]` → ref map → authorisation (an unknown short ref or a ref outside
  the speaker's perspective rejects the whole proposal and records `proposal.rejected_leakage`)
  → lexical corroboration against the spoken text **or the question being answered** →
  phatic/completeness heuristic → Claim Extractor at most once → `SpeechService.utter`;
  `deliberate_false` derived from `contradicts_ref` / `speech_act.lie|knowingly_false`;
  intentions through autonomy gates (`ask` → `autonomy.paused` + `scene.state.autonomy_pending`)
  and the rules engine (`source="ai"`, private intentions flagged, never shown unless observed);
  belief/emotion/goal/relationship proposals as event-linked projections (no `known`,
  confidence ≤ 0.9); Belief Processor gating per belief-update-rules §7 (inline for an actor
  deciding this turn, otherwise queued on the scene); AI combat turns in initiative order with
  policy reuse whenever the situation is unchanged.
- Orchestrator steps 11–13: social turns run reactions after the player's actions; combat
  turns advance the initiative past the player once their major action is spent and let AI
  combatants act until it is a human's turn again. Human-visible output: AI speech the focus
  actor could hear; everything else reaches the human only through their own observations.
- Context compiler: goals from the `goals` table (behaviour-profile strings as fallback, refs
  `g1..`), `emotions_own` section; heard claims render entity names, never ids.
- Fixture: behaviour dimensions, goals (with targets) and autonomy profiles for the Frostbridge
  cast.
- Settings: `SPOTLIGHT_VISIBLE_REACTIONS` (default 2; 06a orchestrator tests run with 0).

Notes / deviations:
- `relationship_proposals`, typed `goal_updates`, `fallback_policy` and
  `speech_act.knowingly_false` were added to the AI Player / NPC Actor output contracts
  (`ai-contracts.md` §5–§6 should list them). Relationship deltas are bounded to ±10 per
  proposal.
- Medium-significance reactions do not get a call in 06b (they are logged as silent); the
  "internal state only" variant waits for a cheaper profile.
- The `npc_tactical` model role is unused: the deterministic controller covers Core Adventure's
  action set. The role stays registered for rulesets with richer tactics.
- Fallback policies are reused whenever the situation is unchanged, not only under the
  degradation ladder (orchestration §19 wants fewer calls after ordinary initiative changes);
  ladder step 4 additionally forces policy reuse when the situation did change.
- A failed action (costs paid, dispatch raised) now emits `action.resolved` with
  `status=failed` like every other outcome; previously it had no ledger event, which the AI
  combat path exposed.
- Private AI actions are observed by whoever could see them (observation rules); there is no
  separate "private" visibility channel beyond the `private` flag on the action params.
