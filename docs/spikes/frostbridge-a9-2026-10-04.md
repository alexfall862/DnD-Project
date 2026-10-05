# Frostbridge slice and World Simulator on A9 (GLM-4.5-Air) — 2026-10-04

The deterministic Frostbridge vertical slice was replayed through the real orchestrator. The
player script is the slice test's, and every role ran on the real model: interpreter, AI
companions, NPCs, rules adjudicator, narrator, extractors. The World Simulator ran over the
Frostbridge clocks. Eval: `tests/eval/test_frostbridge_a9.py` (`make eval-local`). Story beats
are recorded, not asserted; the safety invariants are asserted.

## Outcome

- **The safety invariants held in both runs.** No speaker conveyed a fact it does not hold, no
  leakage incident was recorded, the party never held the hidden truth (Renn killed Oric), and
  the objective truth was untouched.
- **World Simulator:** one call (5.3 s, 961 + 65 tokens) proposed `plan_advance` for the due
  shipment. The proposal was validated and applied, the shipment departed on schedule, and the
  run is on the ledger. No change needed.
- **The first slice run found four problems; three were fixed before the second run.**

## Run 1, and what changed

| Finding | Effect | Fix |
|---|---|---|
| The narrator received only the player's words, never the outcome | "You pick up the dagger" for an invalid pick-up; the content of a ledger never read | `narration_outcomes`: each attempt reaches the narrator as succeeded, FAILED or did NOT happen, and the prompt makes those lines binding |
| GLM picked "Warehouse District" for "the shuttered warehouse with the merchant sign" | The party searched the street; the ledger, dagger and satchel were never found | `closer_to_words`: the player's own words outrank a loose model target |
| "Read the notice" got a ref that matched nothing, so it fell to the Rules Adjudicator | The adjudicator's ruling broke its schema and was rejected | The same word match resolves it to the notice; a rejected ruling is narrated as "no effect" |
| Renn's lie was not flagged `deliberate_false` | The deception is not marked for the debug view or for memory | Backlog |

The eval's whispers were also wrong: `/whisper …` was sent as text, so the target had to be
inferred. They now use the API's channel and target ids, as the browser and harness do.
`narration_style` presets (`terse`, `standard`, `rich`) were also added; the browser's setting
would have crashed the narration bundle.

## Run 2 (after the fixes)

| Beat | Run 1 | Run 2 |
|---|---|---|
| Gate notice read (document, deterministic) | ruling rejected | read, Alex learns Oric is missing |
| Party travels to Oric's warehouse | went to the district | correct warehouse |
| Office search finds the ledger | nothing found (street) | found |
| Main floor search finds the satchel (dock clay) | nothing found | found, the party sees the clay |
| Dagger pick-up | invalid, narrated as success | failed, narrated as failing |
| Combat with two thieves | not run (eval bug) | 2 rounds; the thieves flee |
| Ledger read | no action | no action (target matched nothing; fixed after this run) |
| Mira reveals the argument when whispered to | no | no: she answers aloud, revealing nothing |
| Renn lies about meeting Oric | lied, unflagged | deflects ("Captain's busy with town matters") |

Turn wall times were 19–76 s; the median turn was ≈ 30 s.

| Role | Calls | Median | Max |
|---|---|---|---|
| intent_interpreter | 21 | 7.7 s | 35.6 s |
| narrator | 19 | 5.4 s | 7.8 s |
| npc_actor | 9 | 16.2 s | 29.5 s |
| rules_adjudicator | 7 | 6.2 s | 10.9 s |
| ai_player | 3 | 11.8 s | 16.3 s |
| canon_extractor | 5 | 9.7 s | 20.0 s |
| claim_extractor | 3 | 9.1 s | 9.3 s |

The longest turns made 5–6 synchronous calls: speech that drew two NPC reactions plus the
extractors.

After run 2, the word match also accepts one shared word when the model's ref matched nothing
and no other candidate ties. That fixes "the ledger" for "Oric's private ledger".

## Runs 3–5 (Milestone 10 follow-ups)

| Beat | Run 3 | Run 4 | Run 5 |
|---|---|---|---|
| Mira, whispered to, tells of the argument with Renn | yes | yes | no (evaded; Renn present) |
| The party travels together | Alex only | Alex only | yes |
| Tomas answers when asked by name | no | no (not present) | yes |
| Ledger read and discrepancies learned | no | yes | yes |
| Dock clay seen | no | yes | yes |
| Combat | Alex walked away (word match) | ended in 2 rounds | ended in 2 rounds |
| "Tell Tomas…" makes no canon rulings | yes | yes | yes |
| Safety invariants | held | held* | held |

\* Run 4 flagged one claim. It was the ledger's own text, attributed to its author, Oric, by
the document service; the eval now skips document claims.

Run 3 found the one-word match picking a place for an attack. Run 4 found travel leaving the
companions behind. Both are fixed (`DECISIONS.md`, "Milestone 10 follow-ups (10b)").

In run 5 the median turn took 27 s (run 2: about 30 s). The slowest speech turns still take
70–85 s. The remaining cost is claim extraction: one call of about 10 s for each spoken line
whose claims look incomplete, run one after another (six calls in run 5). Running them
concurrently, or moving them off the critical path, is the next latency lever. Renn told no
clear lie in runs 3–5; the engine-side deception flag is covered by its integration test.

## Still open

- **Mira under GLM** now knows when a whisper is private. She told of the argument in two of
  three runs; with Renn in the room, evasion is in character.
- **Claim extraction** is the main latency cost on speech turns (see above).
- **Narration drift:** one narration placed the satchel at the guard house. The canon extractor
  and allowlist catch new entities, not misplaced known ones.
- **The interpreter sometimes takes a request to a companion as the player's own action.**
  "Tomas, would you look at the guard house records?" became an improvised action by Alex.
