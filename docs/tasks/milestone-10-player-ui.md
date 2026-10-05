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

### Play-session fixes (10c) — done 2026-10-05

A browser play session at the Frostbridge gate led to these fixes (`DECISIONS.md`, "Play-session
fixes (10c)"):

- live turn status, with a dev timeline of every model call and a link to what was sent;
- failed turns keep their trace;
- larger output caps, and the candidate list now reaches the interpreter and actors;
- a closed action list, and social actions rolled with real skills;
- no failed turns on unparseable output;
- living NPCs promoted on the second engagement, remembering the scene;
- the scene so far for the narrator and interpreter;
- OOC as a table assistant;
- click-to-roll dice with stakes, die styles, auto-roll and a dev certificate;
- whispers to several people or the party, and Say naming who it is for.

Tests:

| Area | Where |
|---|---|
| Backend | `test_dice.py` (3), `test_npc_promotion.py`, and new cases in `test_player_api.py`, `test_ai_actors.py`, `test_orchestrator.py` and the unit tests |
| Vitest | 10 |
| Playwright | 15: desktop, phone and Frostbridge, now including dice, live status and group whispers |

`tests/eval/test_session_replay_a9.py` replays the session's own lines on A9.

### Outcomes change the world (10d): done 2026-10-05

The second play session (campaign `879ea872`) showed the engine could not record what attempts
achieved. The design and decisions are in `DECISIONS.md`, "Outcomes change the world (10d)".

**Phase 1:**
- Moves to where you stand are no-ops, with the ways out listed. Entering, leaving and
  following mean travel.
- JSON is stripped from prose answers.
- The table assistant remembers its earlier answers and offers `TRY:` suggestion chips.
- The composer has a Check mode (`check_skill`).
- A whisper with nobody picked goes to the companions present.
- The Here strip (`GET /characters/{id}/here`).
- Arriving somewhere teaches its name.
- At most one promotion per turn, and reactions follow the order the player addressed people.
- The narrator never voices living characters or repeats earlier lines.
- Earlier narration is no longer fed back as fact.
- The composer draft survives switching views.

**Phase 2:**
- `situations` (migration 0018): obstacles, statuses, promises, clocks, alarms, prices, debts
  and followers.
- 34 consequence kinds (`app/domain/consequences.py`) applied by `ConsequenceService`, with
  events.
- Rulings carry `consequences` per branch and `addresses`.
- Social attempts get one ruling.
- NPCs and AI players propose consequences about themselves.
- Travel is stopped only by a recorded obstacle; the safety net prevents soft-blocks.
- The party travels together by default.

**Phase 3:**
- `resource.coin` (`initial_formula`, `tracked_as: count`) and a goods list (`goods.yaml`).
- Buy and sell (`app/services/trade.py`): list price adjusted by `set_price`, and nothing
  happens without the coin. Haggling sets the price.
- Self-introductions teach names, and the encyclopedia lists unnamed people met.

The GM director stays deferred.

Tests:

| Area | Where |
|---|---|
| Backend | `test_consequences.py` (13), `test_prose.py`, and new cases in `test_player_api.py` and `test_target_words.py` |
| Playwright | 4 new tests, on desktop and phone: Here, draft, Check mode, table-assistant suggestion |
| A9 | `tests/eval/test_outcomes_a9.py` |
