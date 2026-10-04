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
