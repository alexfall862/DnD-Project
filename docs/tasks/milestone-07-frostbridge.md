# Milestone 07 — Frostbridge Demo

## Goal
Implement the deterministic Frostbridge vertical-slice fixture.

## Read
`specifications/frostbridge-demo.md` (all); `specifications/communication-and-knowledge.md` §8; `specifications/belief-update-rules.md` §4 worked values; `testing/vertical-slice.md`; `testing/knowledge-leakage.md` §2–§5, §12, §19.

## Implement
All content in `specifications/frostbridge-demo.md`: locations/topology, actors/controllers/party, facts/beliefs/relationships/goals/plans, locked mystery/clues, River Compact, quarry pressure, items/documents, scheduled events, opening scene, combat thieves.

## Required scenarios
Mira evasion; Renn deception; private whisper; companion disagreement; split-party investigation; dagger discovery; warehouse combat/improvisation; reunion knowledge exchange; time advance/evidence destruction.

## Invariants
Fixture truth is deterministic; mystery answer locked; hidden item property remains hidden; party knowledge remains per-actor.

## Tests
Script full deterministic path with FakeModelProvider and fixed RNG.

## Acceptance
Frostbridge integration test demonstrates every major v0.1 architecture concept except procedural campaign generation.

## Tickets (decomposition, 2026-10-03)

| # | Ticket | Likely files |
|---|---|---|
| 07-1 | Mysteries, clues, clue discoveries (schema §13) + `items.concealed`; migration 0012; `MysteryService` (create/activate/lock, clue create/discover/destroy, lock guard); testimony discovery hook in `SpeechService` (c&k §6) | `persistence/models/mystery.py`, `migrations/versions/0012_*`, `services/mystery.py`, `services/speech.py`, `domain/events.py` |
| 07-2 | Documents (immutable text + `conveys[]`), reading as Observation→Claims→Beliefs (belief-update §3); concealed items revealed by a successful `action.search` in the zone (event `item.revealed`, observations, physical/document clue discovery) | `services/documents.py`, `services/actions.py`, `services/observations.py`, `persistence/repositories/perspective.py` |
| 07-3 | Scene transitions: travel between connected locations (join an active scene, start one, or merge = reunion with `merged_from`, no Observations/Claims); `travel` intent for humans and AI intentions; live scene follows the clock, offscreen scenes lag; one bounded offscreen call at reunion | `services/scenes.py`, `services/orchestrator.py`, `services/ai_actors.py`, `services/vocab.py`, `services/candidates.py`, `services/world.py` |
| 07-4 | Deterministic scheduled events: schedule + fire-on-clock-advance with prerequisite revalidation (`fact.establish`, `clue.destroy`, `plan.advance`); factions, memberships, plans seeding API | `services/schedule.py`, `services/world.py`, `services/psychology.py` |
| 07-5 | Full Frostbridge seed (§2–§42): locations/topology, actors/party, facts/beliefs/relationships/goals/plans/core memories, locked mystery + clues, River Compact, quarry, items/documents, scheduled events, opening scene, thieves, fixed generated artifact; transactional verification (§40); offline `make seed-demo`; debug seed endpoint `fixture=` | `seeds/frostbridge.py`, `cli/seed.py`, `api/v1/debug.py`, `Makefile` |
| 07-6 | Deterministic vertical-slice test (§43, vertical-slice.md) with FakeModel + fixed RNG incl. restart/reload, leakage matrix, budget and debug-trace assertions; leakage §19 Elara/guard-log fixture; harness on the full fixture | `tests/integration/test_frostbridge_slice.py`, `tests/leakage/…`, `tests/integration/test_play_harness.py` |
| 07-7 | Docs: status, decisions (07/08 boundary: deterministic firing and reunion fast-forward land here; worker, World Simulator, plan reasoning and full catch-up stay in 08) | `docs/DECISIONS.md`, this file, `CLAUDE.md` |

## Status
**Done — 2026-10-04.** `tests/integration/test_frostbridge_slice.py` walks the deterministic
path of §43 with FakeModelProvider and a fixed RNG (master seed 7) and asserts the property each
step exists for; `test_frostbridge_seed.py` verifies the seed (§40) and the initial leakage
matrix (§42). Every concept of §44 is exercised except procedural generation.

What the slice proves, step by step:
1. **Gate notice** (Document): reading teaches Alex "Oric Dane" and that he is missing; Elara
   learns nothing (only the reader). Rereads are byte-identical (§35).
2. **Travel** gate → market → tavern in one action: the party joins Mira and Renn's scene; the
   clock advances once (180 s); the gate scene stays active and offscreen with its scripted
   guards; arriving creates no Claims.
3. **Mira** evades with the captain in the room, then answers a quiet question with a *partial*
   reveal: `clue_discoveries(mira_account, testimony, partial)` for Alex, Elara and Tomas; the
   belief rows are not linked to the fact; the party learns "Captain Renn" through her words.
4. **Whisper** (c&k §8 / belief-update §4 worked values): Elara `asserted known 1.0` and
   `involved suspected 0.585`; Alex `stated 0.55`; Tomas, Mira, Renn hold nothing and Tomas's
   context contains none of it.
5. **Disagreement**: Tomas defends the captain (Claim → Alex belief); Elara's push-back, when the
   bounded AI-to-AI wave fires, carries an event-linked relationship delta. ≤ 4 calls.
6. **Split**: Tomas decides to go to the Guard House (an AI intention `travel`); Alex and Elara
   travel to the warehouse. The warehouse is live and follows the clock; the tavern lags.
7. **Discoveries**: search reveals the ledger (document clue: found, not yet known), the satchel
   (physical clue: `satchel_has_dock_clay known 1.0` for both searchers) and the dagger; reading
   the ledger gives Alex `ledger_shows_discrepancies` with Oric's Claims as provenance; the
   dagger in Alex's inventory shows no spirit property anywhere in his or Elara's context.
7b. **Offscreen**: Tomas's scene caught up with exactly one AI call (move → records, search →
   records): he knows `guard_log_gap`; Alex and Elara do not; Tomas knows nothing of the ledger;
   Alex has no Observation from the Guard House.
8. **Combat**: two thieves, initiative, attacks and damage with seeded rolls, an engine-side
   clarification for "Attack him!", an improvised shelf topple through the Rules Adjudicator
   (`alter_feature`) that persists after the fight, fallback-policy turns, both thieves
   surrender, `encounter.ended`.
9. **Reunion**: travelling to the Guard House joins Tomas's scene, equalises `local_tick`, adds
   no Claims; knowledge is still asymmetric before anyone speaks.
10. **Exchange**: Alex tells Tomas about the ledger (told belief); Tomas tells them about the log
    gap (`fact_ref` from his context): Alex/Elara beliefs `told` with provenance to his Claim and
    `clue_discoveries(log_numbering, testimony, full)`.
11. **Renn lies**: "Weeks ago." → Claim `asserts_false`, `deliberate_false=True` (private);
    Tomas believes `not met privately` (suspected); the Fact is untouched; Renn keeps `known`.
15. **Scene end** runs the memory checkpoint: Elara remembers "Alex privately trusted me…";
    Tomas has no such memory; Alex gets a journal entry.
12. **Four days**: Day +2 caravan established and market state patched, Day +3 draft destroyed
    (clue and item) and the River Compact plan advanced to "destroy documentation"; Day +5 and
    Day +8 pending; `routes_remaining` still solvable (one log route left).
13–14. **Restart**: a fresh engine/session/orchestrator reloads items (hidden mechanics still
    hidden), clock, beliefs, clue states, plan, goals, memories, relationships, `turn_metrics`
    for every turn, model runs and context snapshots (no non-Renn snapshot contains the murder);
    one more turn plays.
Budget (§41b): every tavern turn ≤ 3 synchronous calls; the AI-to-AI exchange turn ≤ 4.

Also in this milestone:
- `make seed-demo` is offline (`python -m app.cli.seed [--fixture tavern] [--quiet]`); the
  debug endpoint takes `?fixture=`; the harness `--new` seeds the full world (`--fixture
  tavern` for the small scene).
- Leakage suite additions: §19 (Elara conveying the unfound guard-log gap is rejected with a
  `proposal.rejected_leakage` event), the seed-time matrix, Renn detained → Day +3 cancelled.
- Fixes found by the slice: NPC autonomy (surrender paused forever), flee without an exit,
  `encounter.ended` missing when the last foe surrenders on an AI turn, the Claim Extractor
  firing on every `fact_ref` reveal, own-entity rendering as "someone" in an actor's beliefs.

Deviations / backlog (see `DECISIONS.md`, "Frostbridge fixture (07)"): NPC speech has no
whisper channel (Mira's private answer is aloud); the §23 artifact is a fixed validated
definition (model call → 09); YAML seed directory not adopted; Day +5 shipment and quarry
escalation are scheduled but processed by 08; the real-model run of this path is `make
eval-local` territory and was not run in this milestone.
