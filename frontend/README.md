# Lantern Tables: the browser client (Milestone 10)

A React + TypeScript single-page app over the same HTTP API the terminal harness uses. It
works on desktop and phones, and has a per-browser **Dev** switch for developer visibility.

## Run it

```bash
make db-up && make migrate && make api     # API on :8000
make web-install                           # once: npm packages + Playwright Chromium
make web                                   # UI dev server on :5173, proxying /api to :8000
```

Open http://localhost:5173. On a phone, open `http://<this machine's LAN or tailnet IP>:5173`.
Both servers bind to all interfaces.

To serve the UI from the API's own port, run `make web-build`. FastAPI then serves
`frontend/dist` on :8000 next to `/api`.

## Layout

| Width | Layout |
|---|---|
| ≥ 1180 px | Nav rail with party, then the play feed, then a character panel |
| 720–1180 px | Icon rail, then the feed (the character panel lives in Character) |
| < 720 px | Feed with the composer above a bottom tab bar; Encyclopedia, World, Settings and Debug sit under More |

## What the player sees

Everything outside dev view comes from normal, perspective-safe endpoints:

- The play feed shows each turn as the player's line, then mechanics (actions, visible rolls,
  state changes), then speaker-labelled speech, then streamed narration.
- Speakers are named as the focus character knows them, so a stranger stays "a man you have not met".
- The composer has Auto, Do, Say, Whisper, Private and OOC channels.
  - Whisper takes one or several listeners, or the whole party in one tap.
  - Say can name who it is for: everyone present hears, and they answer first.
  - Clarification questions appear inline with their candidates.
- **Dice.** When the game calls for a check, the turn pauses on a card showing the skill, the
  number to reach, your bonus, and what success, failure and a retry would mean. You pick a
  die style, click Roll and watch it land, or Reconsider. Settings can switch to Auto-roll.
  The engine rolls the dice either way, never the storyteller.
- **OOC** asks the table: rules, or what your character knows or sees, answered from your
  character's perspective. Nothing happens in the world.
- While a turn runs, a status line shows what it is doing and for how long, whatever view you
  are on.
- Character shows the sheet and inventory. Party shows who is with you; someone elsewhere is only "away".
- Journal, Encyclopedia ("what you know or suspect") and World (scene and beliefs) are per-character.
- Settings holds the theme (this device) and narration style, companion reactions and spectator mode (the campaign).

The play history is kept on the server (`GET /characters/{id}/feed`), so a reload or another
device shows the same feed. localStorage holds only per-device preferences: theme and the DEV
switch.

## Dev view

The **DEV** switch appears only when the server runs with `DEBUG_MODE=true`. It is remembered
per browser and can be flipped mid-play. With it on:

- a turn in flight shows a live timeline: when the request was sent and accepted, each
  stage, and every model call as it starts, waits on A9 (busy, not loaded, queued), retries
  and finishes, with "what was sent" for each;
- every roll has an "engine dice" chip whose certificate replays the stored seed through the
  engine and shows the same dice;
- failed turns keep their trace;
- each turn shows its latency and model-call count, plus a **Trace** (actions, resolution,
  rolls including hidden ones, events, model calls with their full context);
- a **Debug** view adds turn metrics, the event ledger, objective facts, a perspective
  comparison, model calls, jobs, and controls to advance time or end a scene.

Developer material is always shown in violet, so it is never mistaken for something your
character knows. The UI never parses narration for state.

## Tests

```bash
make web-test   # typecheck + Vitest (stream parser, routing, turn cards, dev/normal split)
make e2e        # Playwright: desktop + phone + the full Frostbridge scenario
```

`make e2e` starts `backend/tests/e2e_server.py` itself. That is the real API on the
`ttrpg_test` database, with the model replaced by scripted fake replies. It runs the Red Lantern
scene on :8001 and the vertical-slice script on :8002, each with its own Vite server.
`node scripts/screenshots.mjs` saves desktop and phone screenshots of a played turn.
