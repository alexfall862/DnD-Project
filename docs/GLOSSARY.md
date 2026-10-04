# Glossary v0.2

Short definitions of terms used across the bundle. When two documents seem to disagree, this
file and `PROMPT.md` invariants are the tie-breaker; record any real conflict per PROMPT.md
"Before modifying architecture".

**Actor** — any individual agent (human PC, AI PC, NPC, creature). One mechanical
representation; `controller` is runtime state (`human | ai | scripted | dormant`).

**Assertion (player)** — a statement by the human that something is true about their
character or the world; classified and handled by `specifications/player-authored-canon.md`. Not a Claim.

**Belief** — one actor's held proposition with type, confidence, provenance. Derived by
`specifications/belief-update-rules.md`. Never objective truth.

**Belief Processor** — bounded model role that may adjust a deterministic belief result in
narrow cases (`specifications/belief-update-rules.md` §7).

**Canon, latent / established** — generated material not yet observed (revisable) vs.
observed/communicated/consequential (immutable without explicit retcon or branch).

**Canon Extractor** — post-narration role that may persist *decoration only*
(`specifications/canon-extraction-allowlist.md`).

**Catch-up** — bounded advancement of an offscreen scene to the world clock
(`specifications/time-accounting.md` §4).

**Claim** — a record that an actor asserted a proposition (with the speaker's private
stance/deception flags). Speech → Claim, never speech → Fact.

**Claim Extractor** — fallback role producing `conveys[]` from utterance text when the
speaking model's structured output lacks it (`specifications/communication-and-knowledge.md` §5).

**Clue** — a route by which a Fact may be learned; physical, documentary or social. Discovered
via `clue_discoveries` with a `route`.

**Context Compiler** — builds one least-privilege context package per model call;
authorization precedes semantic retrieval.

**ContextSnapshot / ContextItem** — audit record of exactly what a model received and why
each item was allowed.

**Controller** — who drives an actor right now. Switching it preserves all actor state.

**`conveys[]`** — structured information content of an utterance or document
(`specifications/communication-and-knowledge.md` §2).

**Core memory** — pinned, retrieval-favoured memory of major personal history.

**Degradation ladder** — ordered list of optional work the orchestrator drops to meet the turn
budget (`specifications/turn-budget-and-latency.md` §5).

**Event** — append-only authoritative record of a state change; projections mutate only in the
same transaction as their Event.

**Fact** — objective truth in the world DB, with canon status (`latent | established |
superseded`) and truth status.

**Fallback policy** — an AI actor's pre-recorded combat behaviour used instead of a fresh call
when the situation is unchanged.

**Focus actor** — the human-controlled actor whose perspective the client renders
(`specifications/human-visibility.md` §2). UI state, not world state.

**Intent** — what an actor wants to do, structured. Resolved by the engine into Actions.

**Live scene / offscreen scene** — the scene containing the focus actor vs. any other active
scene (`specifications/human-visibility.md` §3).

**Memory** — an actor's subjective, auditable retained interpretation; lineage to source
events; may be false.

**Mystery** — first-class entity with locked objective truth generated before clues.

**Observation** — what one actor perceived of one event; template-generated structure
(`specifications/observation-authoring.md`), never model-written.

**Perspective** — the set of information an actor is entitled to; enforced by
`PerspectiveService` as an authorization boundary.

**Player-agent layer / character layer** — what an AI PC's *player* knows (sheet, legal
actions) vs. what the *character* knows in-fiction.

**Projection** — current-state table derived from events for fast reads.

**Proposal** — any model output that could change state; validated, then committed by the
engine or rejected.

**Scheduled event** — engine-created future event with prerequisites revalidated on firing.

**Spectator mode** — OOC-only display of offscreen scenes; grants no knowledge
(`specifications/human-visibility.md` §5).

**Spotlight Governor** — budgets limiting visible AI-to-AI activity per player turn.

**Timeline** — an event sequence; branches reference a parent event, never edit history.

**Turn** — one player input and everything it triggers synchronously; correlated by `turn_id`
and measured in `turn_metrics`.

**World Author** — model role proposing structured world content; may know mystery truth.

**World clock / local tick** — the single authoritative fictional time vs. a scene's last
resolved tick (`specifications/time-accounting.md` §3).
