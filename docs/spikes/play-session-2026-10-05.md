# Browser play session and its A9 replays — 2026-10-05

A human played the Frostbridge gate scene in the browser (Milestone 10 client). The session's
own lines are replayed on A9 (GLM-4.5-Air) by `tests/eval/test_session_replay_a9.py` through the
full HTTP API, in manual dice mode, answering every called-for check with "roll". The fixes
are recorded in `DECISIONS.md`, "Play-session fixes (10c)".

## What the session showed (from its 50 model calls)

| Symptom | Cause |
|---|---|
| The merchant forgot the deal; Tomas "agreed" on his behalf; nothing moved | The merchant and guards were scripted extras with no model call; the narrator invented everything they said |
| Only "improvise" rolls | The interpreter invented action types ("propose_participation"); each became an improvised d20, and talk never reached anyone as speech |
| `json: Expecting ','` on one-paragraph inputs | The interpreter's 320-token output cap; GLM needs 400–600 tokens for those inputs |
| No record of the failed calls | The failed turn's rollback erased its model runs |
| Status vanished when changing views | The in-flight turn lived inside the Play view |
| `ACTION_NEEDS_CLARIFICATION:` with no question | The clarification arrived in a shape the client did not read |
| OOC "noted" | OOC never reached the model |
| Wrong targets throughout | The candidate list never reached the interpreter or actors (a context authorization bug) |

## Replays on A9

| | Replay 1 | Replay 2 | Replay 3 |
|---|---|---|---|
| Failed turns | 0 | 1 (stale scene after travel) | 0 |
| Long inputs | handled | handled | handled |
| OOC answers | from Alex's perspective | yes | yes, recalls the deal |
| Called-for checks | Ability ("Check"), Persuasion (bribe) ×2, Persuasion, Intimidation | Deception, bribe, Deception | Deception, bribe ×2, Persuasion, Intimidation |
| The merchant | stayed scripted; the party had walked away ("merchant sign") | promoted on the second engagement | promoted on the second engagement; answers as himself from then on |
| His memories | none | from the scene | his spoiling spices, the odd seal, the bribed guard, where he is headed |
| Hidden truth held by the party | none | none | none |

Fixes between replays:

- **After replay 1:**
  - Targets come from the model's own ref words before the player's sentence.
  - A place is never picked by one shared word.
  - A spoken `utterance` is kept separate from the description.
  - "Where are we?" is a look action.
  - Checks always name a skill.
  - The narrator may voice only unnamed bystanders.
- **After replay 2:**
  - One utterance per turn.
  - Each step acts in the actor's current scene.
  - An improvised action by an absent actor is invalid, not a crash.

Replay 3 timings: the median turn took 34 s; the slowest took 129 s (the interpreter repaired
its output once); a resumed roll took 25–47 s.

## Still open

- GLM sometimes omits `utterance`, so a described line ("We'd like to tail…") is spoken whole.
- The narrator still quotes bystanders before they are promoted. That is allowed, and flagged
  in dev notes when the words were never spoken.
- Claim extraction and second interpreter calls are the main latency costs.
