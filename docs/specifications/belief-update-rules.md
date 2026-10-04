# Belief Update Rules v0.2

## 1. Purpose

Belief changes must be deterministic by default so they are testable, cheap and auditable.
A model is consulted only in the narrow cases listed in §7. Everything here is a tunable
default; the values live in ruleset/campaign configuration, not in engine code.

> **Observation and testimony produce beliefs by rule. The model is asked only when a rule
> says the situation is interpretive.**

## 2. Belief record recap

Belief: `actor_id`, proposition (fact ref | claim ref | free proposition), `belief_type`
(`known | believed | suspected | rumor | opinion | assumption | inference | false_memory |
stated | doubted`), `confidence` 0–1, `source_type`, `source_actor_id`, `acquired_event_id`,
`status` (`active | superseded | contested`).

Beliefs are never deleted; superseded ones stay with `superseded_event_id`.

## 3. Direct observation

| Source | Type | Confidence |
|---|---|---|
| Witnessed with a clear primary sense (deterministic observation, `confidence ≥ 0.9`) | `known` | observation confidence (≈1.0) |
| Partial/degraded observation (dark, distant, obstructed; `0.4–0.9`) | `believed` | observation confidence |
| Deterministic mechanical outcome visible to the actor (own HP change, visible roll) | `known` | 1.0 |
| Read in a Document | `believed` | `0.85 × document_trust` (default document_trust 1.0; forged/unsigned 0.7) |
| Inferred by the engine from mechanics (e.g. successful Investigation reveals a pre-existing clue) | `known` | 1.0 for the revealed proposition only |

## 4. Testimony

For a recipient R receiving a Claim from speaker S:

```
base          = 0.35
trust_term    = 0.0035 × trust(R→S)          # trust ∈ [-100, 100] → [-0.35, +0.35]
familiarity   = 0.0005 × familiarity(R→S)    # ∈ [0, +0.05]
plausibility  = +0.10 if consistent with an active belief of R
                -0.20 if it contradicts an active belief of R with higher confidence
                 0    otherwise
stance_cap    = 0.95 for asserts_true/false
                0.60 for uncertain
                0.30 for hypothetical
confidence    = clamp(base + trust_term + familiarity + plausibility, 0.05, stance_cap)
```

Belief type: `believed` if confidence ≥ 0.6; `suspected` if 0.3–0.6; `rumor` if < 0.3 **or**
the speaker's own claim provenance is already `rumor`/secondhand.

No relationship row (stranger): `trust` treated as 0, so a stranger's assertion lands at
≈0.35 (`suspected`). Expected worked values for Frostbridge seeds:

- Tomas ← Renn (no relationship yet; Tomas's general belief "accusations need evidence" is
  not about Renn): 0.35 → `suspected`. Tomas's prior "most guards are ordinary people" gives
  +0.10 if the engine marks it consistent → 0.45.
- Elara ← Alex (trust seeded ~60 in fixture): 0.35 + 0.21 = 0.56, stance `uncertain` cap
  0.60 → `suspected 0.56`.

Speaker's own meta-belief: R always also gains `known 1.0` that *S asserted P* (the Claim
itself is a fact about the world). This is what lets Elara later say "Alex told me he
suspected Mira" regardless of whether she believes it.

Self-report (`about_speaker_self`): +0.10 plausibility unless contradicted by R's observation.

## 5. Contradiction and supersession

When a new belief candidate B' conflicts with an active belief B of the same actor about the
same proposition (negation, or same predicate with a different object/value):

- if `conf(B') ≥ conf(B) + 0.20` → B becomes `superseded`, B' active;
- if `|conf(B') − conf(B)| < 0.20` → both remain active with `status = contested`;
  the context compiler renders contested beliefs explicitly ("you have heard both X and Y");
- otherwise B' is stored at its computed confidence as a weaker alternative (`status = active`,
  it simply ranks lower).

Direct observation (`known` from a primary sense) always supersedes testimony about the same
proposition regardless of margin.

## 6. Deception and insight mechanics

- A successful insight/awareness contest against a knowingly false Claim does **not** reveal
  truth. It applies `confidence × 0.5` to the resulting belief and sets `belief_type = doubted`,
  plus a `known 1.0` belief that *S seemed evasive / was hiding something*.
- A failed contest applies nothing: the lie lands at normal testimony confidence.
- A rule or ability that explicitly grants truth detection may instead block the belief and
  create `known: S lied about P`.

## 7. When a model is consulted (Belief Processor)

A `belief_processor` call is scheduled (not inline, unless the belief gates the current
decision) only when **all** of the following hold:

1. the recipient is an AI-controlled actor of importance `important` or `full`, or an AI PC;
2. the Claim is goal-relevant (touches an entity in one of the actor's active goals) or
   contradicts an active belief with confidence ≥ 0.6;
3. the deterministic result above would land within 0.15 of a type boundary, **or** there are
   two or more contested beliefs on the proposition.

The model receives the deterministic result as the default and may return a proposal adjusting
confidence by at most ±0.25 and/or adding an `inference` belief. It cannot create `known`.
Expected frequency: a small minority of Claims; telemetry reports it.

## 8. Downtime inference

During rest/downtime processing, an AI actor with ≥ 3 active beliefs sharing an entity may
receive one bounded Belief Processor call to propose `inference` beliefs. Output confidence
is capped at 0.7 and provenance records the input belief ids.

## 9. Human-controlled actors

Human PCs use the same rules so that control transfer (Invariant 11) carries a coherent belief
store, and so journal/encyclopedia projections are grounded. The human player is free to act
against their character's belief store; the store is descriptive, not restrictive.

## 10. Tests

- Table in §3/§4 reproduced as parametrised unit tests with the Frostbridge seed values.
- Contradiction cases: supersede, contested, weaker alternative, observation-beats-testimony.
- Insight contest halves confidence and adds the "evasive" belief; truth is never revealed.
- Belief Processor gating: construct cases that fall inside and outside the §7 conditions and
  assert the number of scheduled model calls.
- Every belief created in the Frostbridge scripted path has a provenance chain back to an
  Observation or Claim event; none references an objective Fact the actor was not authorized
  to see.
