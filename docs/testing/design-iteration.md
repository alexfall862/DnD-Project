# Design Iteration & Playtest Loop v0.2

## 1. Why

Every other test in this bundle checks correctness. None checks whether Elara is enjoyable to
travel with, whether Tomas talks too much, or whether the narrator's pacing is right. Those
are the properties that decide if the project gets played. This loop makes them observable
and tunable without code changes, starting at the first playable harness (Milestone 06d).

> **Correctness is proven by tests. Fun is proven by a play journal and a rubric, on a
> cadence, with tunables that do not require a deploy.**

## 2. Cadence

- After each milestone from 06d onward: one **playtest session** of 30–45 real minutes against
  the configured local model (not FakeModel), using Frostbridge until worldgen is trustworthy.
- Fill the rubric (§3) and the journal (§4) during/after the session.
- Open at most **three** tuning changes from each session (§5). More than three means the
  session found an architecture problem, which becomes a ticket instead.

## 3. Rubric (1–5 each, per session)

| Dimension | 1 | 5 |
|---|---|---|
| Companion consistency | contradicts own goals/beliefs within the session | recognisably the same person throughout |
| Companion agency | pure follower / pure contrarian | disagrees, initiates, and yields for reasons |
| Talkativeness | AI dialogue crowds out the human, or companions are mute | human sets the pace; companions speak when it matters |
| Memory in play | forgets what was said earlier this session | references earlier events/private talks unprompted and correctly |
| NPC credibility | NPCs are information dispensers | NPCs evade, lie, bargain according to their own stakes |
| Rulings | adjudications feel arbitrary or always "yes" | difficulties track the fiction; failure has texture |
| Narration | over-long, florid, or contradicts mechanics | matches configured style; mechanics are legible |
| Pace | waits break immersion | waits feel like a DM thinking |
| Surprise | nothing happened the player didn't cause | the world did something coherent on its own |
| Knowledge feel | player senses leakage or inexplicable ignorance | asymmetry feels natural and discoverable |

Record also: turns played, p50/p95 time-to-first-narration (from `turn_metrics`), model
calls per turn, and any budget breaches.

## 4. Play journal

A short markdown entry per session in `docs/playtests/YYYY-MM-DD.md`:

- what the player tried to do, in order;
- three moments that worked;
- three moments that broke immersion, each tagged `prompt | tunable | mechanic | architecture`;
- one thing to try next session.

Entries are the raw material for prompt and tunable changes and for the eval fixtures
(`testing-strategy.md` §6): a broken moment that can be reproduced becomes an eval case.

## 5. Tunables (no deploy required)

Exposed through `PATCH /campaigns/{id}` settings and the Debug UI:

- behaviour dimensions per actor (risk, aggression, empathy, …) and autonomy profile;
- spotlight budgets (consecutive AI turns, AI-to-AI exchanges, unsolicited initiatives);
- reaction significance thresholds (silent / internal / visible);
- conversation time bands and the conversation cap (`../specifications/time-accounting.md`);
- narration style profile (verbosity, dialogue style, mechanics visibility);
- clarification readiness;
- `player_canon_policy`, `spectator_mode`;
- model profile routing per role.

Changes are logged as `settings.changed` events so a later playtest can be compared against
the settings it ran under.

## 6. Prompt changes

Prompts are versioned (`../specifications/ai-contracts.md` §18). A playtest-driven prompt change bumps the
version, adds or updates an eval fixture that would have caught the problem, and is run through
`make eval-local` before and after. Prompt changes never substitute for an authorization fix
(PROMPT.md leakage rule).

## 7. Exit criteria for v0.1 (added to Milestone 13)

Three consecutive playtest sessions with every rubric dimension ≥ 3 and no `architecture`
-tagged breaks.
