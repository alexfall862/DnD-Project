# Time Accounting & Scene Reconciliation v0.2

## 1. Purpose

`DECISIONS.md` states that conversation advances time at an estimated level and that unequal
scene time must be reconciled before reunion. This document gives both a concrete v0.1
mechanism, deliberately simple, with the extension path named.

> **One world clock. The live scene drives it. Offscreen scenes catch up in bounded steps.
> Reconciliation is a fast-forward, never a rewind.**

## 2. Time costs of actions

Every resolved action carries a `time_cost_seconds` from the ruleset (`../architecture/02-rules-engine.md`
§27). Defaults for Core Adventure: trivial interaction 10 s; combat round 6 s; movement between
zones 10–60 s per band; room search 5 min; travel from `location_edges.travel_seconds`.

### Conversation

Dialogue has no mechanical time cost in the rules, so the engine estimates:

- each **exchange** (one player utterance plus the visible responses it triggers) costs a
  band chosen by the Intent Interpreter: `brief (15 s) | normal (45 s) | long (3 min) |
  extended (10 min)`; default `normal` when the interpreter is skipped;
- a scene-level cap: conversation alone cannot advance a scene by more than 60 min without a
  deliberate `downtime`/`wait` action; beyond the cap each exchange costs 0 and the narrator is
  told time is "late".

Estimates are events (`time.advanced`, cause = the utterance event) like any other advance.

## 3. World clock vs. scene clocks

`world_clocks.current_tick` is the single authoritative time. Each scene records
`scenes.local_tick` = the world tick at which that scene's last resolved action ended.

- The **live scene** (containing the focus actor — `human-visibility.md` §2) advances the
  world clock directly: `current_tick += time_cost`.
- An **offscreen scene** has `local_tick ≤ current_tick`. It is advanced by the catch-up
  procedure (§4) and may never exceed `current_tick`.

Scheduled events fire against `current_tick`. An offscreen scene that is behind simply
observes scheduled events that already fired when its catch-up reaches them.

## 4. Catch-up (offscreen scene advancement)

Triggered when the live scene advances the world clock past an offscreen scene's `local_tick`
by more than `catchup_granularity` (default 10 min), or at scene end, or at reunion:

1. compute `delta = current_tick − local_tick`;
2. run deterministic systems for the scene's participants over `delta` (resources, conditions,
   travel in progress, schedules);
3. if any participant has an active plan step that completes within `delta`, or a scheduled
   scene trigger fires, make **one** bounded World Simulator / AI Player call with
   `event_budget = max(1, delta / 30 min)` capped at 3, asking for the actor's actions during
   the interval (structured intentions, no narration);
4. resolve those intentions through full mechanics in sequence, stamping each event with the
   estimated tick inside the interval;
5. set `local_tick = current_tick`.

Catch-up is **budgeted**: at most one model call per offscreen scene per catch-up, and at most
`max_offscreen_catchups_per_turn` (default 2) per live turn. If budget is exhausted the scene
stays behind and catches up on the next trigger.

## 5. Reunion

When actors from two scenes come to share a location, the engine:

1. runs catch-up on the lagging scene to `current_tick`;
2. merges participants into one scene (new scene row, `scene.merged_from[]`);
3. creates **no** Observations or Claims — knowledge still only moves by communication
   (`communication-and-knowledge.md`).

Because an offscreen scene can never be ahead of the world clock, reconciliation is always a
fast-forward and the "the other group spent six hours and we spent one" problem reduces to:
the group with the live scene defines how much time passed; the offscreen group fills it.

## 6. Waiting and downtime

`wait`/`rest`/`downtime` actions advance the world clock by the requested amount, then run
scheduled events, catch-ups and the world-simulation tick (`../architecture/03-ai-orchestration.md` §25).
Interrupts: a scheduled event flagged `interrupting` for a participant ends the wait early and
the narrator is told what interrupted it.

## 7. Extension path (not v0.1)

Independent per-scene clocks that may run ahead of the world clock (true parallel play) would
require the world clock to become `max(local_ticks)` and scheduled events to fire per scene.
The schema anticipates this (`scenes.local_tick` exists) but v0.1 forbids `local_tick >
current_tick` with a database check.

## 8. Tests

- Conversation band estimates produce `time.advanced` events with cause provenance; the 60-min
  conversation cap holds.
- Split party: live scene advances 90 min; offscreen scene catches up with ≤ 1 model call and
  its events carry ticks inside the interval.
- Reunion merges scenes, equalizes ticks, creates zero Observations.
- A Day +3 scheduled event fires during a live advance and is observable by an offscreen
  scene only when its catch-up reaches that tick.
- Database check rejects `local_tick > current_tick`.
