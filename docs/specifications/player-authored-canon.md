# Player-Authored Canon Policy v0.2

## 1. Purpose

Tabletop players routinely assert things: "I pull out the map my grandmother gave me",
"My character grew up here and knows the baker", "There's a loose stone in this wall, right?"
The engine needs a rule for which assertions become true, which become proposals, and which
are refused — otherwise the Intent Interpreter either invents state or blocks ordinary play.

> **Player assertions are classified, then handled by campaign policy. Accepted assertions
> are events with `created_by_type = player_assertion`, never silent state.**

## 2. Classification

The Intent Interpreter emits `asserted_facts[]` alongside intents:

```yaml
- proposition: {subject_entity_id?, predicate, object_entity_id?, value?}
  class: self_minor | self_major | world_minor | world_major | contradiction
  mechanical_weight: none | minor | significant
```

- `self_minor` — about the player's own character, no mechanical weight, no new named entity
  of importance: a keepsake, a habit, a hometown, a childhood memory.
- `self_major` — about the player's character but with mechanical weight or introducing a
  consequential relationship: a weapon they "always carried", a noble title, a mentor who is
  a named power.
- `world_minor` — environmental detail that could plausibly exist and is not canon either way:
  a loose stone, a back door to a tavern, a stable boy.
- `world_major` — anything that creates plot-relevant structure: a secret passage into the
  guard house, an NPC owing the party a favour, a known cure.
- `contradiction` — conflicts with established canon or the actor's perspective (the player
  asserts Renn is the killer; the player claims an item they do not possess).

## 3. Policy (`settings.player_canon_policy`)

| Class | `strict` | `personal` (default) | `collaborative` |
|---|---|---|---|
| self_minor | adjudicate | **accept** | accept |
| self_major | refuse | adjudicate | adjudicate (yes-and bias) |
| world_minor | refuse | adjudicate | **accept** |
| world_major | refuse | refuse | adjudicate (yes-and bias) |
| contradiction | refuse | refuse | refuse |

- **accept**: a `Fact` is created as `established` (it has been communicated) with
  `created_by_type = player_assertion`, plus any lightweight entity (an item with
  `mechanical_snapshot = {}`; a background NPC seed). The narrator is told it is true.
- **adjudicate**: routed to the Rules Adjudicator (mechanical weight) or World Author
  (world structure) as a proposal with the player's assertion as the request. The usual
  validation applies; `yes-and bias` is a prompt instruction to prefer acceptance with a
  complication over refusal. The player sees the result as narration or a one-line OOC note.
- **refuse**: no state change; the turn returns `ACTION_NEEDS_CLARIFICATION` with a short OOC
  note ("Alex doesn't have a map like that — want to look for one?") or narrates the absence.

Pre-play character creation is always `collaborative` for `self_*` classes, because that is
what character creation is for.

## 4. Limits even under accept

- No mechanical advantage: accepted items/traits have empty mechanics until adjudicated.
- No knowledge gain: an accepted backstory fact does not populate beliefs about *other*
  entities beyond `self_minor` scope ("I know the baker" creates a background NPC and a
  familiarity relationship, not the baker's secrets).
- Rate: at most `max_player_assertions_per_scene` (default 3) accepted automatically; further
  ones are adjudicated.
- Mystery truth, locked facts, and hidden properties are never affected (Invariant 10).

## 5. Interaction with AI PCs

AI actors have no assertion channel. Their "assertions" are intentions and `conveys[]`
(Claims); a Claim never creates a Fact. This asymmetry is deliberate: the human is a
co-author within policy; the models are not.

## 6. Tests

- Each class × policy cell behaves per the table using fixture assertions.
- Accepted `self_minor` creates Fact + event with `player_assertion` provenance and no belief
  for any other actor.
- `contradiction` with locked mystery truth is refused under every policy.
- Rate limit falls back to adjudication, not refusal.
