# Communication → Knowledge Contract v0.2

## 1. Why this document exists

The knowledge model (Fact / Claim / Observation / Belief) only works if every piece of
communication that reaches an actor is turned into structured information the engine can
reason about. Prose alone is not enough: when Elara tells Tomas "we found a ledger in the
warehouse", the engine must be able to answer *which information Tomas now holds, from whom,
and with what confidence* without re-reading a transcript.

This document defines that path. It is a blocking dependency for Milestone 03 (deterministic
parts), Milestone 06b (AI actor outputs) and Milestone 07 (clue discovery by testimony).

> **Every utterance that reaches another actor produces zero or more Claims. Every Claim
> carries structured information content. Beliefs derive from Claims and Observations through
> the rules in `belief-update-rules.md`, never from prose directly.**

## 2. Information content of an utterance

An utterance (speech, whisper, letter, radio message, telepathic send, gesture) has:

- `speaker_actor_id`
- `channel` and recipient/audibility resolution (from the sensory rules)
- `spoken_text` (verbatim, archived in `transcript_messages`)
- `conveys[]` — the structured information content, defined below

### `conveys[]` item schema

```yaml
- kind: belief_ref | fact_ref | proposition
  ref_id: <belief id or fact id>          # required for belief_ref / fact_ref
  proposition:                              # required for proposition; optional otherwise
    subject_entity_id: <optional>
    predicate: <text, short>
    object_entity_id: <optional>
    value: <optional scalar/text>
  stance: asserts_true | asserts_false | uncertain | question | hypothetical
  fidelity: full | partial | distorted
  deliberate_false: bool                    # private to the speaker's record; never shown to recipients
  about_speaker_self: bool                  # e.g. "I was at the docks last night"
```

- `belief_ref` — the speaker is relaying something they believe. The engine knows the belief's
  own confidence and provenance, so the recipient's new belief can inherit a provenance chain.
- `fact_ref` — permitted only when the speaker's perspective actually contains that fact
  (an actor who knows a fact may reference it directly; this is how Renn can *lie about*
  something he knows).
- `proposition` — free content with no existing record. This is normal for player text,
  new rumors, speculation and lies with no underlying belief.

### Validation (authorization)

For AI-produced utterances every `belief_ref` must resolve to a belief **held by the speaker**
and every `fact_ref` must be **in the speaker's authorized perspective**. A reference to
anything else is a leakage incident (see `testing/knowledge-leakage.md` §19): the proposal is
rejected, no Claim is stored, and in development the test fails. This is the structural
guarantee that an AI actor cannot "accidentally" tell the party something it does not know.

**Corroboration (added after the 04b spike).** Authorization proves a reference is *allowed*; it
does not prove the words *said* it. Small models attach allowed-but-unspoken facts to
`conveys[]` a few percent of the time, which would otherwise store a Claim conveying a secret
the speaker never voiced. Therefore, for every `belief_ref`/`fact_ref` with `stance` other than
`question`: the referenced record's key terms (entity names, predicate head words) must overlap
`spoken_text` (cheap lexical check, no model call); items that fail are dropped and logged with
the ModelRun, and telemetry reports the drop rate. `kind` is advisory — the engine determines
belief vs. fact from the id.

Free `proposition` items cannot be authorization-checked semantically. Development mode logs
them; the evaluation suite measures how often an actor's propositions coincide with secrets it
should not know (the "proposition leakage rate").

## 3. Producing `conveys[]`

### AI actors (AI Player, NPC Actor, World Simulator dialogue)

Structured output **must** include `conveys[]` for any `spoken_text`. The role prompt asks the
model to list what information the speech communicates, referencing the belief/fact ids it was
given in context. A `spoken_text` with an empty `conveys[]` is accepted only when the engine's
cheap heuristic (no entity names, no predicate-bearing verbs, under ~12 words) agrees it is
phatic ("Fine." / "After you.").

If `spoken_text` is non-trivial and `conveys[]` is empty or looks incomplete (text mentions
known entity names absent from refs), the engine runs the **Claim Extractor** (§5) once.
The model is never asked twice.

### Human player text

The Intent Interpreter output gains a `conveys[]` field for `say` / `whisper` channels.
Human utterances are mostly `proposition` items; the interpreter also links to the human
actor's existing beliefs when the text clearly restates one.

Speaking is evidence of the speaker's own state. For a human-controlled actor, an
`asserts_true` proposition that is `about_speaker_self` or expresses a suspicion creates or
updates a belief **for the speaking actor** (type `stated`, confidence by stance: assert 0.8,
uncertain 0.55). This is how "I think Mira did it" becomes `Alex suspects Mira` in Alex's own
store, which Elara's new belief can then reference. OOC text never does this.

### Documents

A Document's `conveys[]` is authored once at creation (seed, World Author or player writing)
and is immutable with the text. Reading a document is an Observation whose Claims come from
that stored list. Rereading never re-extracts.

### Deterministic speech

Engine-generated speech (scripted NPC lines, system announcements in-fiction) ships with its
`conveys[]` in the ruleset/fixture data.

## 4. From Claim to recipient Belief

For each recipient that legitimately receives the utterance (sensory rules + language
comprehension), the engine:

1. stores one `Claim` row per `conveys` item with `speaker_actor_id`, `statement_event_id`,
   the proposition (resolved from refs), `speaker_stance`, and — privately — `deliberate_false`;
2. creates an Observation for the recipient of type `heard_claim` referencing the Claim;
3. applies `belief-update-rules.md` to produce or revise the recipient's Belief;
4. if the Claim's underlying fact is a `clues.supported_fact_id`, records a `clue_discoveries`
   row with `route = testimony` and `claim_id` (§6).

Recipients never receive `deliberate_false`, `fidelity` or the speaker's belief confidence.
They receive the Claim and whatever their own insight mechanics reveal.

Language: a recipient without comprehension gets an Observation `speech_in_unknown_language`
and **no Claims**.

## 5. Claim Extractor role (fallback)

**Prompt ID:** `claim_extractor` v1 — **Profile:** `fast_structured`

Input: the utterance text, the speaker's known entity aliases, the entity candidates present in
the scene (perspective-safe for the *speaker*), and nothing else.

Output: `conveys[]` as above, with `proposition` items only (it cannot see belief ids).

Rules: extract assertions actually made; do not infer implications; mark questions and
hypotheticals; never resolve a reference to an entity not in the candidate list.

Budget: at most one call per utterance, only for utterances that reach at least one other actor
and whose `conveys[]` failed the completeness heuristic. Expected frequency after prompt tuning:
under 10% of utterances. The telemetry (`turn-budget-and-latency.md`) reports it.

## 6. Clue discovery by testimony

A clue may be physical (ledger), documentary (letter), or social (Mira's account). Social
clues are discovered when a Claim conveying the clue's `supported_fact_id` — fully or partially
— reaches a party actor. `clue_discoveries.route` records `testimony` and the `claim_id`, so the
debug UI can show *who learned what from whom*.

Partial fidelity (Mira: "He was here. They argued. I didn't hear about what.") records the
discovery with `fidelity = partial`; the fact's full content is **not** entered into the
recipient's belief — only the partial proposition is.

## 7. Knowledge propagation summary

```
utterance text
   └─ conveys[] (AI structured output | Intent Interpreter | Claim Extractor | document record)
        └─ authorization check (refs ⊆ speaker perspective)
             └─ Claim rows (one per item), speaker-private deception flags
                  └─ per-recipient Observation(heard_claim) after audibility + language
                       └─ belief-update-rules → Belief (with provenance chain)
                            └─ clue_discoveries(route=testimony) when applicable
```

No step reads prose. Prose is archived for the narrator, the human and the memory processor.

## 8. Frostbridge examples

| Utterance | Speaker | `conveys` | Result |
|---|---|---|---|
| "Weeks ago." (last spoke to Oric) | Renn | `fact_ref: renn_met_oric_night_X`, `asserts_false`, `deliberate_false=true` | Claim stored; Tomas belief *Renn last spoke to Oric weeks ago* at told-confidence from trust(Renn); Renn's private flag stays private |
| "He was here that night. They argued." | Mira | `fact_ref: renn_met_oric`, `fidelity: partial` | Claim; clue `mira_account` discovered route=testimony fidelity=partial |
| "I think Mira had something to do with it." (whisper) | Alex | `proposition: Mira involved in Oric disappearance`, `uncertain` | Alex self-belief `suspected 0.55`; Elara belief `Alex suspects Mira` known 1.0 **and** `Mira involved` suspected at told-confidence; Tomas: nothing |
| "We found Oric's ledger. The dock numbers don't match." | Elara | `belief_ref: elara_knows_ledger`, `belief_ref: elara_ledger_shows_dock_discrepancy` | Tomas beliefs with provenance chain Elara→ledger document |

## 9. Tests

- Every AI utterance in the Frostbridge FakeModel path ships `conveys[]`; the authorization
  check rejects a fixture where Elara's output references a fact only Renn holds.
- Mira's partial testimony discovers the clue at partial fidelity and does not give Alex the
  fact's full content.
- Renn's lie creates a Claim and a Tomas belief but no Fact and no belief for Renn.
- Alex's whisper produces the exact belief set in §8 for Alex, Elara and nobody else.
- A Document reread produces identical Claims and zero model calls.
- Claim Extractor is invoked at most once per utterance and only on the fallback path.
