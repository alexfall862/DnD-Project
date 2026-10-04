# Human Visibility & Multi-PC Control v0.2

## 1. Purpose

The perspective architecture governs what AI actors may receive. The same discipline has to
govern what the **human player** sees, otherwise the human becomes the leakage channel: they
read Tomas's scene, then play Alex as if he knew it. This document defines what the human
sees, when, and through which actor.

> **The human sees through a controlled actor, never through the world. Switching the actor
> they look through is an OOC act that transfers no in-fiction knowledge.**

## 2. Focus actor

At any moment the human client has exactly one **focus actor**: a human-controlled actor
whose perspective the narrator renders and whose scene is the active scene. `/play` requests
name the actor (`actor_id`); the campaign records `focus_actor_id` as UI state, not world
state.

The normal API (`api-contracts.md` §26) is evaluated against the focus actor's perspective
for scene, inventory, journal and encyclopedia. Nothing the human can read in normal mode
exceeds that actor's perspective.

## 3. Split party

When the party splits into scenes A (contains the focus actor) and B (AI-controlled only):

- Scene A is **live**: it is played turn by turn as usual.
- Scene B is an **offscreen scene**: it advances in bounded steps when scene A's clock advances
  (see `time-accounting.md`), using the simulation budget rules (`../architecture/03-ai-orchestration.md` §25),
  not the live turn loop. AI actors in B still act through full mechanics; their events,
  Claims and Observations are stored normally. Narration for B is **not generated** unless a
  rule in §5 applies; the engine stores structured results only.
- The human receives **nothing** from scene B. Reunion creates no synchronization. The human
  learns B's results the way Alex would: by being told, by seeing consequences, by reading.
- Debug mode shows both scenes side by side.

### Choosing to play the other scene

The human may OOC-switch focus to an AI PC in scene B (if the campaign's control settings
allow it — `actor_controllers` switches `ai → human` for that actor). This is a controller
change (Invariant 11): the human now plays Tomas with Tomas's beliefs rendered, and Alex
becomes `ai` or `dormant` in scene A. Knowledge still does not cross: when the human later
switches back to Alex, Alex's perspective is unchanged. The journal records a control change,
not a discovery.

## 4. Multiple human-controlled PCs

`DECISIONS.md` allows the human to control several PCs. Rules:

- One focus actor at a time for rendering; the others are `human`-controlled but
  **non-focus**. Their turns are taken by switching focus (OOC) or, in combat, by the
  initiative order prompting the human for each controlled actor in turn — the UI shows which
  actor is acting and renders that actor's perspective for that prompt.
- The **player-agent layer** (sheets, legal actions, resources) is visible for all
  human-controlled actors at once; the **character layer** (beliefs, memories, observations)
  is rendered only for the focus actor. This is the same split used for AI PCs
  (`../architecture/01-world-memory.md` §7).
- Two human-controlled PCs in the **same** scene: the scene view shows the union of what
  either observed, each item labelled with the observer. Dialogue between them is still an
  in-world utterance with Claims (`communication-and-knowledge.md`).
- Human-controlled PCs in **different** scenes: the non-focus scene is treated as offscreen
  (§3) until focused.

## 5. Spectator mode (OOC, default off)

`settings.spectator_mode: off | summary | full`. When on, the client may display an
**OOC panel** with structured results (`summary`) or generated narration (`full`) for
offscreen scenes containing AI PCs. The panel is clearly OOC-labelled, is never part of the
narrative feed, and **grants no knowledge**: the focus actor's perspective is unaffected and
the journal does not include it. Full mode spends narrator calls on offscreen scenes and
counts against the background budget.

This exists because some players enjoy watching their companions; it must never be the
default, because it undermines the split-party design.

## 6. Narration from the focus actor

The Narrator receives the focus actor's observations only. If the focus actor is unconscious,
blinded or absent, narration is correspondingly limited ("you come to on the warehouse floor;
the fight is over"). Sensory limitation applies to the human exactly as it applies to AI
actors.

## 7. Journal and encyclopedia

Both are per-actor projections already. The client shows the focus actor's. Switching focus
switches the journal. There is no party journal in v0.1; a party-level projection, if added
later, is the **intersection** of member knowledge that has been communicated, never the union.

## 8. Tests

- Split party: scene B produces events, Claims and beliefs; the normal API for the focus actor
  returns none of them; after reunion, still none until communicated.
- Focus switch Alex→Tomas→Alex leaves both actors' belief stores unchanged apart from the
  events of play.
- Spectator `full` shows narration in the OOC channel and produces zero Observations for
  the focus actor.
- Two human PCs in one scene: scene output labels observers; a whisper between them creates
  Claims visible only to the two.
- Unconscious focus actor: narration for the interval contains no events that actor could
  not perceive (verified against the actor's Observation rows).
