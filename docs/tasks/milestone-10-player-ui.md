# Milestone 10 — Player & Debug UI

## Goal
Make the vertical slice playable from the browser without direct API/database tooling.

## Read
`architecture/05-implementation-plan.md` §19–§20; `specifications/api-contracts.md` (all); `specifications/human-visibility.md` (all); `specifications/turn-budget-and-latency.md` §6–§7; `testing/testing-strategy.md` §20–§21; `testing/design-iteration.md` §5.

## Views
Play, Character, Party, Journal, Encyclopedia, World, Settings, Debug.

## Play UI
Narration feed, labeled NPC/AI-PC dialogue, visible rolls, mechanical notices, input channels Auto/Do/Say/Whisper/Private/OOC.

## Character/party UI
Attributes, skills, resources, abilities, conditions, equipment/inventory, visible companion status. Do not expose private relationship numbers/goals in normal mode.

## Debug UI
Events, objective facts, actor perspectives, comparison view, rolls, resolution traces, model runs, ContextSnapshots, memory, goals, clocks, mysteries, scheduled jobs.

## Invariants
Frontend never derives state by parsing narration. Normal APIs remain perspective-safe.

## Tests
Core browser flows and hidden-data absence.

## Acceptance
Complete Frostbridge scripted scenario is playable from UI, and a developer can expand a turn to trace its internal resolution.

## Status — done 2026-10-04

The Frostbridge scenario is playable from the browser on desktop and phone. A developer can
flip the DEV switch at any time and expand any turn into its full trace. Decisions are in
`DECISIONS.md`, "Player UI (10)".

- **Client** (`frontend/`): Vite + React + TypeScript SPA with Play, Character, Party,
  Journal, Encyclopedia, World, Settings and Debug views. Play streams mechanics, then
  speaker-labelled lines, then narration; it has Auto/Do/Say/Whisper/Private/OOC channels,
  inline clarification, and a three-, two- or one-column layout depending on width. FastAPI
  serves `frontend/dist`. Make targets: `web`, `web-install`, `web-build`, `web-test`, `e2e`.
- **API additions:** campaign list and detail, player settings (with a `settings.changed`
  event), the focus actor's sheet, the party as perceived, scene participant actor ids, and
  the debug turn trace.
- **Tests:**
  - `tests/integration/test_player_api.py` (6): focus actors only, sheet authorisation, the
    party when split, writable settings, the turn trace with its debug gate, and hidden-data
    absence across every normal endpoint the UI reads.
  - `frontend/src/test` (Vitest, 6): the SSE parser, routes, turn cards in normal and dev
    view, clarifications.
  - `frontend/e2e` (Playwright, 7): turn rendering, whispers, hidden-data absence and the dev
    toggle on desktop and phone, plus the full Frostbridge scenario through the UI.

Real-model runs of the slice and the World Simulator are recorded in
`docs/spikes/frostbridge-a9-2026-10-04.md`. Their fixes are narration outcomes and target
words. Follow-ups (10b), also done:
- the feed is server-side (`GET /characters/{id}/feed`);
- whispers are private in the reacting actor's context;
- engine-side deception flags;
- unmatched reads are invalid without a ruling;
- dialogue is never canon, with at most one assertion ruling per turn;
- the addressed character always reacts;
- word matching respects the action;
- companions travel by the player's words.

Backlog: claim-extraction latency on speech turns, and a location descriptor for unnamed places
(the strip says "Somewhere unfamiliar").
