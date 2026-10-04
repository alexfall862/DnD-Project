# Persistent AI TTRPG Engine — World, State & Memory Architecture v0.2

## 1. System definition

The application is a persistent tabletop roleplaying simulation engine in which humans and AI-controlled actors interact through a shared rules/world engine.

> **LLMs perceive, interpret, propose, roleplay, improvise, and narrate. The engine authorizes, resolves, randomizes, records, and remembers.**

The system maintains three categories of information:

1. **Objective world state** — what is actually true.
2. **Subjective actor state** — what a particular actor knows, believes, remembers, suspects, wants, and perceives.
3. **Narrative representation** — how resolved objective/subjective events are presented to players.

These must never be conflated.

## 2. Core architectural rules

- Objective reality is authoritative and stored in the application database.
- Perspective is a security boundary, not a prompt convention.
- LLMs propose; the engine commits.
- Important state has provenance.
- Campaign history is event-sourced.
- Memory is persisted and retrieved; it is not an indefinitely growing model conversation.
- Narration never implicitly mutates state.
- Established canon does not silently change.
- Mystery truths are objective and lock before play can invalidate them.

## 3. Primary domain concepts

### Campaign

Top-level container holding ruleset, active timeline, creation mode, campaign mode, genre modules, tone/simulation/narration settings, model configuration, engine version, and ruleset version.

Campaign modes begin as `authored`, `sandbox`, and `emergent`, but should ultimately be represented by underlying configuration values such as narrative pressure, world autonomy, and simulation depth.

### Timeline

Every campaign has at least one timeline. A timeline may branch from an event in another timeline. Events themselves are not edited to create branches.

This supports save forks, debug experimentation, retcons by branch, and eventual player-facing alternate timelines.

### Entity

Every meaningful persistent fictional object has a stable internal identity. Names are mutable properties, never identifiers.

Potential entities include actors, items, locations, vehicles, structures, documents, artifacts, and other persistent objects.

### Actor

Human PCs, AI PCs, NPCs, creatures, constructs, and other individual agents use the same conceptual Actor representation.

Actors have a separate `controller` state (`human`, `ai`, `scripted`, `dormant`). Changing who controls a character does not replace the character or alter its memories, goals, inventory, mechanics, or relationships.

NPCs support importance tiers (`background`, `standard`, `important`, `full`) and can be promoted when they become relevant. Promotion generates missing detail while preserving everything already established.

### Faction

Factions are distinct from Actors. They can have ideology, resources, territory, goals, plans, leaders, relationships, and simulation state without pretending an organization is literally an individual person.

### Party

A party is a persistent group with membership history, shared resources/assets, group reputation, and potentially shared contracts or property. Multiple parties may coexist.

## 4. Actor behavior and agency

Characters use both prose and structured behavioral traits. A behavior profile can include summary, traits, ideals, fears, values, taboos, quirks, tactical preferences, and dimensions such as risk tolerance, aggression, empathy, curiosity, loyalty, impulsiveness, patience, honesty, sociability, and ambition.

These numeric tendencies guide context and decision-making; they are not deterministic rules such as “loyalty > 75 means never betray.”

### Goals and plans

Goals are persistent entities with owner, priority, status, secrecy, targets, progress, and deadlines. Goals can succeed, fail, be abandoned, be superseded, or conflict with other goals.

Plans are stepwise intended methods of pursuing goals. Villain/faction plans can be interrupted by players and progressed through world simulation.

### AI autonomy

AI-controlled PCs are independent players, not DM puppets. Per-domain autonomy can be configured as `blocked`, `suggest_only`, `ask`, or `autonomous` for areas such as conversation, exploration, combat, spending, item transfer, advancement, party departure, romance, and major irreversible action.

AI PCs may disagree, refuse, pursue private goals, make mistakes, start fights, spend resources, romance, betray, leave the party, and continue existing after departure.

## 5. Objective facts, claims, and beliefs

### Fact

A Fact represents objective world truth. Example: `Duke Varek murdered Lord Calen`.

Facts may be `latent`, `established`, or `superseded` and may be true, false, or unresolved depending on the proposition type.

### Claim

A Claim is something an actor said or otherwise asserted. Speech does not become truth merely because it is spoken.

An actor can say “The king is dead” while the king remains objectively alive.

### Belief

A Belief belongs to one actor and can represent `known`, `believed`, `suspected`, `rumor`, `opinion`, `assumption`, `inference`, or `false_memory` states with confidence and provenance.

The world may simultaneously contain:

- objective truth: Varek killed Calen;
- Alex's belief: smugglers killed Calen (0.80);
- Elara's suspicion: Varek may have killed Calen (0.45);
- Varek's knowledge: I killed Calen (1.00).

Knowledge provenance should identify how information was learned: witnessed, overheard, told, read, inferred, magically revealed, assumed, or remembered.

How a Claim becomes a Belief — and with what confidence — is deterministic by default. The rules are in `../specifications/belief-update-rules.md`; the path from an utterance to structured Claims is in `../specifications/communication-and-knowledge.md`. Neither step reads prose.

## 6. Perspective as access control

A model call for an AI actor must never start from global world state. Context construction receives requesting role, actor identity, campaign/timeline, and purpose, then retrieves only authorized data.

An AI PC can access its own observations, beliefs, memories, relationships, goals, mechanics, visible scene, and public/known rules. It cannot access objective secrets, another actor's private thoughts, hidden entities, mystery solutions, or unidentified item properties.

This must be enforced in backend service/repository boundaries. Prompt instructions are defense in depth only.

## 7. Player-agent versus character layer

AI-controlled PCs have two conceptual knowledge layers.

The **player-agent layer** may know the character sheet, legal actions, ability costs, item mechanics already available to the player agent, and rules necessary to competently play.

The **character layer** contains only in-world observations, beliefs, memories, relationships, goals, emotions, and world knowledge.

This allows a model to understand “this ability costs 2 Focus” without revealing DM secrets to the fictional character.

NPC combat can use the same separation: a tactical controller knows legal options while the roleplay persona knows only character knowledge.

## 8. Observation system

Every observer receives an independent Observation generated from authoritative events and deterministic sensory rules whenever possible.

Example: if Alex is in Room A, Elara is in Room B, and a closed door blocks ordinary sound, Elara does not receive Alex's conversation. An LLM is not needed to decide this.

Sensory channels are generic and extensible: vision, hearing, smell, touch, telepathy, radio, infrared, magic sense, and others.

Receiving a signal and understanding it are separate. An actor may hear Elvish speech without understanding its semantic content.

Observation content is generated by template from the event, per observer, with names substituted from the observer's identity knowledge; it is rendered to text only when needed and never written by a model. See `../specifications/observation-authoring.md`.

## 9. Perspective-dependent identity

Internally an entity has one stable ID, but different characters may know it by different names or incorrectly believe identities are separate.

Example:

- Alex knows `entity_123` as “the Masked Woman.”
- Elara knows the same entity as “Lady Veyra.”
- Alex may later discover those identities are the same.

This supports aliases, disguises, secret identities, mistaken identity, shapeshifters, espionage, and location aliasing.

## 10. Memory architecture

Memory is the bedrock of long campaigns and must be auditable.

The system uses several complementary layers:

1. **State memory** — what is true now.
2. **Event memory** — immutable chronological history.
3. **Entity memory** — durable records of people, places, objects, organizations.
4. **Relationship memory** — directional relationship state plus event-linked deltas.
5. **Perspective memory** — actor-specific beliefs, knowledge, suspicions, rumors.
6. **Narrative memory** — scene/session summaries.
7. **Semantic memory** — embeddings over useful actor memories, observations, documents, and summaries.

Vector search is useful but never the primary source of truth.

### Memory records

A memory can store subjective summary, emotional interpretation, salience, emotional weight, specificity, accessibility, core-memory flag, source events, created time, last recalled time, and lineage.

### Auditable forgetting

Forgetting does not delete source truth. Memory may evolve:

`event → observation → detailed memory → compressed memory → fuzzy recollection`

Each derived memory retains lineage to its predecessor/source events. Debug mode can inspect the entire chain.

### False memories

An actor's remembered interpretation may differ from objective history. Example: objective event says Alex pursued an attacker after believing Elara had escaped; Elara's subjective memory may become “Alex abandoned me when I needed him.” This is allowed and must not overwrite objective events.

### Core memories

Major personal history (betrayal, oath, death, marriage, formative victory, trauma) can be pinned as core memory and strongly favored during context construction.

## 11. Relationship architecture

Relationships are directional. Elara can trust Alex more than Alex trusts Elara.

Suggested dimensions include trust, affection, respect, fear, resentment, obligation, and familiarity plus qualitative history.

Every relationship change has event-linked provenance. “Elara likes Alex more” is not an unexplained free mutation; it must reference the event(s) that caused the change.

## 12. Emotion state

Temporary emotions such as fear, anger, grief, embarrassment, joy, jealousy, or hope can be explicit transient state with intensity, source event, start time, decay rule, and resolution.

Emotions influence actor decision contexts without being treated as objective personality changes.

## 13. Locations and topology

Locations nest flexibly: world → continent → region → settlement → district → building → room → zone. The same abstraction works for galaxy → system → planet → city, a megadungeon, a ship, a dream realm, or alternate plane.

Topology is explicit through relationships such as connected_to, north_of, inside, above, visible_from, hidden_connection, travel_time, movement_cost, and access requirements.

## 14. Theater-of-the-mind space

Combat and exploration use one location/zone system rather than a separate grid engine by default.

Useful distance relationships include engaged, close, near, far, and distant plus cover, elevation, blocked, reachable, adjacent, and line-of-sight.

The engine owns spatial truth; narration describes it.

## 15. Items and persistent objects

Important items are unique persistent entities with template/type, name, mechanics snapshot, owner, possessor, container, location, condition, provenance, history, hidden properties, and known properties.

Ownership and possession are separate. A stolen crown may be possessed by Alex while still legally belonging to the king.

The same persistent-entity approach can apply to houses, ships, books, artifacts, vehicles, pets, businesses, and other meaningful objects.

### Documents

Letters, books, contracts, clues, and journals persist with immutable original text once created. They may be summarized later, but rereading the same document must not regenerate different text.

## 16. Resources and conditions

Resources generalize HP, mana, stress, sanity, oxygen, fuel, ammunition, hunger, political capital, and similar quantities. Conditions generalize poisoned, frightened, blessed, wanted, bleeding, and other temporary or persistent effects.

Campaign/ruleset modules can enable different complexity levels.

## 17. Event sourcing and projections

Important world history is append-only. Events include timeline, fictional time, type, actors/entities, location, cause, payload, visibility, creator, and associated rolls.

Current state is stored as efficient projections but every authoritative projection mutation is tied to one or more events committed in the same transaction.

This makes branching, replay, causality, debugging, journals, and retcon analysis tractable.

## 18. Narrative authority classification

Language produced by models must be classified by authority type. Important categories include:

- flavor;
- actor speech;
- actor belief;
- actor intention;
- proposed fact;
- canonical creation;
- mechanical proposal;
- world-state mutation.

Example: “Everyone knows the Queen is a witch” spoken by an NPC is a claim/rumor, not `queen.is_witch = true`.

## 19. Intent and consequence contracts

Every freeform action becomes structured intent. Example:

> Elara: “I grab the idol before Alex can stop me.”

becomes an intent with actor, action type, target, urgency, opposition possibility, and assumptions. The engine checks reachability, reactions, initiative, traps, resources, autonomy, and rules before resolving.

**LLM proposes intent. Engine resolves consequence.**

## 20. Secrets and mysteries

Secrets are objective facts with restricted knowledge and may have stakeholders, exposure risk, consequences, and discovery paths.

Important mysteries are first-class entities. Generation sequence is:

`truth → participants → motive/cause → timeline → evidence → witnesses → clue routes → red herrings → discovery conditions`

Once a mystery becomes active, its objective answer locks. The engine/AI may vary how clues are encountered but cannot switch culprits because a different answer seems more dramatic.

## 21. Latent and established canon

Generated world material has at least two important canon states.

**Latent canon** exists in generated structure but has not been observed or caused player-facing consequences. It may be revised when necessary.

**Established canon** has been observed, explicitly communicated, referenced, or caused gameplay consequences. It may not silently change.

World detail can progress through `outline → latent → referenced → materialized → established`.

If the player asks a scholar for the capital of a vaguely generated empire, the World Author can materialize the capital immediately; communicated information becomes established.

## 22. World time

The campaign has a real fictional clock/calendar. Actions consume time; time drives weather, schedules, hunger/fatigue, healing, effect duration, travel, deadlines, faction plans, businesses, seasons, and other enabled systems.

Default policy is action-driven time. Conversation advances time by estimated bands with a per-scene cap (`../specifications/time-accounting.md` §2). Optional real-time-scaled/hybrid play can exist later.

## 23. World simulation

The world can advance offscreen without continuously running every NPC as an autonomous agent.

Use simulation levels of detail:

- far-away world: aggregate values;
- regions/factions: plan progression and clocks;
- nearby named actors: goals, schedules, significant decisions;
- active scene: full entity-level resolution.

Deterministic/rule-based simulation runs first. LLM calls are reserved for meaningful ambiguous decisions.

All simulation runs have explicit time interval, candidate subjects, event budget, and loop/call limits.

## 24. AI actors outside the party

A former companion remains an Actor after leaving. Travel, goals, important encounters, injuries, faction membership, possessions, and relationships continue to evolve at appropriate simulation detail.

A former party member can later return as ally, rival, mayor, enemy, or changed character without being recreated.

## 25. Spotlight governor

AI actors can proactively act, but the player should not spend the session watching models talk to each other.

The session layer maintains budgets such as maximum consecutive visible AI turns, AI-to-AI exchange limits, unsolicited initiative limits, narrative significance threshold, and background-action compression.

Meaningful AI interactions can be rendered; incidental ones are summarized or simulated silently.

## 26. Player input channels

The human sees the world through exactly one **focus actor** at a time; offscreen scenes are not shown and focus switches transfer no knowledge (`../specifications/human-visibility.md`). Player statements that assert facts about the character or world are classified and handled by campaign policy (`../specifications/player-authored-canon.md`).

The UI supports natural-language inference plus explicit channels:

- Do
- Say
- Whisper
- Private/Think
- OOC

Explicit channel selection overrides inference. Direct speech is audible to eligible listeners according to scene/sensory rules; whispers and private instructions remain scoped.

## 27. Multi-action input and interruptions

A user message can decompose into ordered atomic steps. Example:

“I grab the book, yell for Elara, and jump through the window.”

becomes take(book), shout(Elara), move(window), traverse(window). Other actors may react between steps. The engine does not assume every clause succeeds because the user wrote them in one sentence.

## 28. Split scenes and asynchronous compatibility

Architecture should allow multiple active scenes when the party splits. Each scene has participants, local state, and local progression while sharing the campaign's world time carefully.

When groups spend unequal time, temporal reconciliation is required before reunion. v0.1 uses a single world clock driven by the live scene, with offscreen scenes catching up in bounded steps so reconciliation is always a fast-forward (`../specifications/time-accounting.md`).

The architecture should not prevent future live or play-by-post multiplayer even though v0.1 is single-user.

## 29. Debug / human-GM mode

Debug mode may expose:

- objective truth;
- actor beliefs and knowledge;
- prompts/context packages;
- retrieved memories;
- hidden rolls;
- rules resolution;
- faction state;
- event queue;
- latent versus established canon;
- mystery answers;
- proposed/rejected actions;
- token usage and latency.

Debug controls may edit state, inject events, possess NPCs, take over AI PCs, correct memory, advance time, force rolls, reveal hidden state, branch, or retcon explicitly.

Normal production play should not expose omniscient correction controls.

## 30. Initial technology target

- Next.js / React UI
- FastAPI backend
- PostgreSQL + pgvector
- SQLAlchemy / Alembic
- provider-neutral AI interface
- local OpenAI-compatible inference by default
- database-backed worker for background jobs
- browser delivery over local Ubuntu server / Tailscale

## 31. First vertical slice

The first playable proof should create a small original fantasy campaign with one human PC and two AI PCs, enter a generated town, interact with persistent NPCs, create asymmetric knowledge through a private conversation, find a unique item, resolve a freeform check, run a small theater-of-the-mind combat, split and reunite the party, advance several days, process a world event, save/restart, and verify that everyone still knows exactly what they should and nothing they should not.

That scenario is represented concretely by the Frostbridge fixture.
