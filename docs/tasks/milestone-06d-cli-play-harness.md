# Milestone 06d — CLI Play Harness

## Goal
Make the engine playable at a terminal before any browser work, so the architecture can be
felt, the real model can be smoke-tested, and the design-iteration loop can begin.

## Read
`specifications/api-contracts.md` §9–§12; `specifications/human-visibility.md` §2;
`specifications/turn-budget-and-latency.md` §6–7; `testing/design-iteration.md`.

## Implement
- `scripts/play.py` (or `make play`): loads/creates a campaign, prints the opening scene from
  the focus actor's perspective, accepts input with channel prefixes (`/do`, `/say`, `/whisper
  <name>`, `/think`, `/ooc`, bare text = auto), streams mechanics then narration, shows
  speaker-labelled AI lines, and prints per-turn metrics (calls, wall ms) on a status line.
- `/debug` subcommands that call the debug API: `events`, `perspective <actor>`,
  `compare`, `context <model_run>`, `beliefs <actor>`, `metrics`.
- Uses the HTTP API only (no direct service imports) so it exercises the same boundary the
  frontend will.
- Works with FakeModelProvider (deterministic demo script replay) and the real local model.

## Invariants
The harness never parses narration for state; it displays only what the API returns. Normal
commands use normal endpoints; `/debug` uses `/api/v1/debug` and refuses when debug mode is off.

## Tests
A scripted session (FakeModel) that walks the Frostbridge deterministic path through the
harness and asserts the printed mechanics match the API responses.

## Out of scope
Any UI polish; multiplayer; anything the API does not already provide.

## Acceptance
A developer can play a 20-turn Frostbridge session against the real local model from the
terminal, see every turn's call count and latency, and run the first playtest rubric.

## Status
**Done — 2026-10-03.** Acceptance holds: `make play ARGS="--new"` seeds the Red Lantern through
the debug API and plays it at the terminal over HTTP; a scripted FakeModel session walks the
tavern through the harness and the printed mechanics match the API responses
(`tests/integration/test_play_harness.py`).

- `backend/app/cli/play.py` (`Harness`): HTTP-only client (httpx). `--new` seeds via
  `POST /api/v1/debug/seed-demo`; `--campaign <id>` resumes (actors listed via
  `GET /debug/campaigns/{id}/actors`; the focus actor must be human-controlled). Input: bare
  text = auto channel; `/do /say /think /ooc` prefixes pass through to the API; `/whisper
  <name> <text>` resolves the target from the actor list and sends `target_actor_ids`;
  `/scene /inventory /beliefs /journal /encyclopedia` call the perspective endpoints; `/end`
  ends the scene (debug; runs the memory checkpoint and journal); `/debug events |
  perspective <name> | compare | context <model_run> | beliefs <name> | metrics | runs`;
  `--script <file>` replays commands.
- Streaming: `accepted` → per-action `mechanics` (⚙), `speaker` lines labelled by name,
  summary `mechanics` (🎲 rolls, Δ state changes), `narration_delta` streamed token by token
  on the terminal (buffered once for non-terminal sinks), `complete` → one status line
  `[wall ms | calls sync+bg | first output | narration | role×count | degraded: …]`,
  `result` → mechanical notices, assertion outcomes, OOC notes; `error` → code + candidates
  (clarifications show their refs so the player can answer).
- Debug API additions: `POST /debug/seed-demo`, `GET /debug/campaigns/{id}/actors`,
  `GET /debug/campaigns/{id}/metrics`, `GET /debug/campaigns/{id}/model-runs[?turn_id]`,
  `GET /debug/model-runs/{id}/context` (rendered context, authorization scope, raw and
  structured output), `POST /debug/campaigns/{id}/scenes/{scene_id}/end`.
- The Red Lantern seed moved from the test fixture into `app/seeds/frostbridge_tavern.py`
  (`seed_tavern`, `SeededWorld`, `FROSTBRIDGE_BUILDS`, `BEHAVIOR`, `TAVERN_SPACE`); the
  pytest fixture, the rules tests and the debug endpoint all use it. Milestone 07 extends it
  to the full fixture.
- `scripts/play.py` is a launcher; `make play` and `make seed-demo` are wired.

Notes / deviations:
- The harness refuses to play an AI actor (the API would refuse too) and surfaces API errors
  verbatim; it never parses narration for state.
- `make seed-demo` currently calls the debug endpoint of a running API (needs DEBUG_MODE);
  the Milestone 07 version will be an offline seed command.

### First live sessions on A9 (2026-10-03, GLM-4.5-Air)

Three scripted sessions through `make play` against the real model. What they measured and
what they changed:

| turn | calls | wall | first output | first narration token |
|---|---|---|---|---|
| `/say Mira, has Oric Dane been in lately?` | intent, npc_actor, narrator | 36.2 s | 10.9 s | 33.4 s |
| `/whisper Elara I think the innkeeper knows more…` | intent, ai_player, narrator | 37.9 s | 12.7 s | 34.3 s |

The Intent Interpreter is the fixed cost (≈ 10 s: 1.2k prompt tokens + ~150 output); an
actor reaction ≈ 13–21 s depending on output length (GLM writes 200–380 tokens); the
narrator streams within ~4 s of its call. Social turns sit at the hard cap of the revised
budget (40 s) and the ladder's first step (drop canon extractor) fires every turn.

Defects found and fixed in the loop (each has a regression test):
- A9 streams a final usage-only chunk with `choices: []`; the stream parser crashed on it and
  the SSE connection dropped without `complete`/`result`. Parser guards it; the SSE generator
  now always ends with an `error` event on an internal failure; narrator failures never lose
  the turn.
- GLM wrote the whisper target's *actor id* (shown in the situation line) as a proposition's
  `subject_entity_id` → foreign-key violation on `claims`. Ids are sanitised (actor id →
  entity id; unknown ids → free text), targets are shown as refs, and `SpeechService` only
  stores references to entities that exist.
- An explicit `/whisper` was interpreted as a `world_minor` assertion plus a "conceal"
  action: two adjudicator calls, no whisper. Explicit speech is now always an utterance;
  assertions and non-speech intents are ignored for that turn.
- Mira cited the fact "Renn met Oric privately" under "Captain Renn's been in, though":
  name overlap passed corroboration. Assertions now need a predicate term in the text or in
  the question answered; denials keep the name-based rule.
- The claim extractor fired on almost every NPC line (any mentioned name unreferenced); it
  now fires only when most mentioned names go unreferenced.
- `requires_clarification` from the model is advisory; model target refs are matched by name
  tokens; heard claims and notices render the observer's names, never ids; first-turn
  resource materialisation is not reported as a state change; the combat ladder step is
  skipped outside combat.

Open (design-iteration backlog): intent cost (consider a shorter interpreter prompt and a
smaller profile once a second model is resident); GLM's `value: false` propositions for
negations; Elara answering a whisper aloud (prompt tuning: a whisper invites a whisper).
