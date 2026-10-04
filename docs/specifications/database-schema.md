# PostgreSQL & Domain Schema v0.2

## 1. Principles

PostgreSQL is authoritative persistent state.

- UUID primary keys (`gen_random_uuid()`).
- Database timestamps use `TIMESTAMPTZ`.
- Fictional time uses monotonic `BIGINT game_tick` engine-seconds from a campaign epoch.
- JSONB is for extensibility, not for replacing relational modeling.
- Events are append-only in ordinary play.
- Current state is materialized as projections for fast reads.
- Established canon cannot silently change.
- Actor knowledge is separate from objective truth.
- Model runs and contexts are auditable.
- In-world destruction/death generally changes lifecycle state rather than deleting rows.

Extensions:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
```

## 2. Fictional time

Each timeline has one WorldClock. `game_tick` represents canonical elapsed seconds. `calendar_definition` translates ticks into fictional dates, supporting non-Gregorian calendars, alternate worlds, and time travel.

## 3. Campaign/timeline tables

### campaigns

- `id UUID PK`
- `name TEXT NOT NULL`
- `description TEXT NULL`
- `status TEXT NOT NULL` (`draft|generating|ready|active|archived`)
- `creation_mode TEXT NOT NULL` (`surprise|guided|imported|manual`)
- `campaign_mode TEXT NOT NULL` (`authored|sandbox|emergent`)
- `active_timeline_id UUID NULL`
- `ruleset_key TEXT NOT NULL`
- `ruleset_version TEXT NOT NULL`
- `engine_version TEXT NOT NULL`
- `settings JSONB NOT NULL DEFAULT '{}'`
- `generation_brief JSONB NOT NULL DEFAULT '{}'`
- `world_version BIGINT NOT NULL DEFAULT 0`
- `created_at/updated_at TIMESTAMPTZ`

Indexes: status.

### timelines

- `id UUID PK`
- `campaign_id UUID FK campaigns`
- `name TEXT`
- `parent_timeline_id UUID NULL FK timelines`
- `branch_event_id UUID NULL`
- `status TEXT DEFAULT 'active'`
- `next_event_sequence BIGINT DEFAULT 1`
- `created_at`

Branch event must belong to parent timeline when present.

### world_clocks

- `timeline_id UUID PK FK timelines`
- `current_tick BIGINT DEFAULT 0`
- `calendar_definition JSONB`
- `time_policy TEXT DEFAULT 'action_driven'` (`action_driven|realtime_scaled|hybrid`)
- optional real-time anchor/game tick anchor/scale
- `updated_at`

## 4. Generic entities and locations

### entities

- `id UUID PK`
- `campaign_id UUID FK campaigns`
- `entity_type TEXT`
- `canonical_name TEXT NULL`
- `lifecycle_state TEXT DEFAULT 'active'`
- `importance_tier TEXT DEFAULT 'background'`
- `created_event_id UUID NULL`
- `established_event_id UUID NULL`
- `metadata JSONB`
- created/updated timestamps

Common types: actor, item, location, vehicle, structure, document, artifact, other.

Common lifecycle states: active, inactive, dead, destroyed, missing, transformed, unknown.

### locations

- `id UUID PK`
- `entity_id UUID UNIQUE FK entities`
- `parent_location_id UUID NULL FK locations`
- `location_type TEXT`
- `detail_level TEXT DEFAULT 'outline'` (`outline|latent|referenced|materialized|established`)
- `properties JSONB`
- `simulation_state JSONB`

### location_edges

- `id UUID PK`
- `campaign_id UUID`
- `from_location_id/to_location_id UUID FK locations`
- `relationship_type TEXT`
- `travel_seconds BIGINT NULL`
- `movement_cost NUMERIC NULL`
- `requirements JSONB`
- `properties JSONB`
- `created_event_id UUID NULL`

Relationships can include connected, inside, north_of, south_of, above, below, visible_from, hidden_connection.

## 5. Actors, controllers, factions, parties

### actors

- `id UUID PK`
- `entity_id UUID UNIQUE FK entities`
- `actor_type TEXT` (`pc|npc|creature|construct|other`)
- `importance_tier TEXT` (`background|standard|important|full`)
- `current_location_id UUID NULL FK locations`
- `current_scene_id UUID NULL`
- `mechanical_profile JSONB`
- `behavior_profile JSONB`
- `tactical_competence TEXT DEFAULT 'trained'`
- `alive BOOLEAN DEFAULT TRUE`
- `active BOOLEAN DEFAULT TRUE`
- `updated_event_id UUID NULL`

### actor_ai_profiles

- `actor_id UUID PK FK actors`
- `autonomy_profile JSONB`
- `decision_preferences JSONB`
- `tactical_preferences JSONB`
- `preferred_model_profile TEXT NULL`
- `updated_at`

### actor_controllers

- `id UUID PK`
- `actor_id UUID FK actors`
- `controller_type TEXT` (`human|ai|scripted|dormant`)
- `user_key TEXT NULL`
- `valid_from_event_id UUID`
- `valid_until_event_id UUID NULL`
- `created_at`

Partial unique index ensures only one active controller row per actor.

### factions

- `id UUID PK`, `campaign_id UUID`
- `name`, `description`
- `ideology/resources/capabilities/territory JSONB`
- `simulation_priority NUMERIC DEFAULT .5`
- `active BOOLEAN`
- `created_event_id`

### faction_memberships

- faction/actor IDs, role, status, joined/left events.

### parties

- `id`, `campaign_id`, `name`
- `shared_resources/shared_reputation JSONB`
- `created_event_id`

### party_memberships

- party/actor IDs, role, joined/left events.

## 6. Scenes

### scenes

- `id UUID PK`
- campaign/timeline/location IDs
- `scene_type TEXT` (`social|exploration|combat|travel|downtime|other`)
- `status TEXT DEFAULT 'active'`
- start/end event IDs and ticks
- `version BIGINT DEFAULT 0`
- `local_tick BIGINT` (last resolved tick; CHECK `local_tick <= world clock` enforced via trigger/service, see `time-accounting.md` §3)
- `merged_from UUID[] NULL`
- `state JSONB`

### scene_participants

- scene/actor IDs
- `zone_key TEXT NULL`
- `position_state JSONB`
- joined/left events

Partial unique active membership index per scene/actor.

## 7. Event ledger

### events

- `id UUID PK`
- `campaign_id`, `timeline_id`
- `sequence_number BIGINT`
- `event_type TEXT`
- `payload_version INT DEFAULT 1`
- `game_tick BIGINT`
- optional scene/location/cause event
- `created_by_type TEXT`, `created_by_id UUID NULL`
- `payload JSONB`
- `world_version_after BIGINT`
- `created_at`

Unique `(timeline_id, sequence_number)`.

Events are never rewritten in ordinary play.

**Payload versioning stance (v0.1):** `payload_version` is recorded from the first migration, but no upcasters are written before v0.1 ships; development campaigns are disposable and `make reset-db` is the migration path. Replay tests run against fixtures seeded at the current version. Upcasters become mandatory the moment a campaign is declared non-disposable (recorded in `DECISIONS.md`).

### event_entities

Join table mapping events to entities with a role (`actor`, `target`, `item`, `observer`, etc.). This avoids scanning JSON for common history queries.

## 8. Transcript and scheduled events

### transcript_messages

- campaign/timeline/scene IDs
- optional `speaker_actor_id`
- `channel TEXT` (`narration|say|whisper|private|internal|ooc|system`)
- `raw_text TEXT`
- `game_tick BIGINT`
- `source TEXT` (`human|ai|engine`)
- `created_at`

### transcript_recipients

Intended recipients; overhearing is represented through observations rather than this table.

### scheduled_events

- campaign/timeline IDs
- `scheduled_tick BIGINT`
- event type/payload
- status (`pending|processing|processed|cancelled|failed`)
- created/processed event references

Index by timeline/status/scheduled tick.

## 9. Mechanical state

### resource_states

Unique `(entity_id, resource_key)` with current/max values, extensible state, and last-changed event.

### condition_instances

Target entity, condition key, optional source entity, source event, start/expiry ticks, status, parameters.

### items

- `id UUID PK`, `entity_id UUID UNIQUE`
- optional template key
- type/description
- `mechanical_snapshot JSONB`
- `condition_state JSONB`
- owner, possessor, container, location IDs
- `hidden_properties JSONB`
- `public_properties JSONB`
- provenance and created event

Application enforces coherent placement and distinct ownership/possession semantics.

### item_history

Item, event, change type, payload.

### documents

`item_id PK`, immutable `original_text`, content hash, author, creation tick, language, optional cipher.

### rolls

Campaign/timeline/event/actor IDs, expression, seed, raw result, modifier state, final result, purpose, visibility (`public|actor_only|hidden|debug`), created timestamp.

### pending_clarifications

Campaign/scene/actor, `clarification_id`, original input, question, candidate entity IDs, `reason` (`AMBIGUOUS|ASSERTION_REFUSED`), status (`open|answered|cancelled`), created/resolved timestamps. At most one open row per actor.

## 10. Intent/action resolution

### intents

Campaign/timeline/scene/actor/source message, intent type, natural-language text, structured intent, status, based-on world and scene versions, timestamp.

### actions

Intent/actor/action type, status (`proposed|validated|resolving|succeeded|failed|partial|interrupted|cancelled`), requirements/costs/effects JSONB, start/resolution events.

### action_steps

Ordered atomic steps with payload/status/resolved event.

### reaction_windows / reaction_eligible_actors

Track trigger step, rules/status/open-close events and eligible actors/reasons.

### resolution_traces

Per action: rules consulted, requirements, modifiers, roll IDs, effects proposed/applied/rejected, summary.

## 11. Objective truth and subjective perspective

### facts

- campaign ID
- optional subject entity
- predicate
- optional object entity/value
- `canon_status` (`latent|established|superseded`)
- `truth_status` (`true|false|unresolved`)
- validity ticks
- created/established events
- optional supersedes fact
- provenance

Established rows are immutable through ordinary services.

### claims

Speaker, statement event, subject/predicate/object/value, `speaker_stance` (`asserts_true|asserts_false|uncertain|question|hypothetical`), `fidelity` (`full|partial|distorted`), `deliberate_false BOOLEAN` (speaker-private; never returned by perspective queries), `source_fact_id NULL`, `source_belief_id NULL` (what the speaker was relaying, if anything), `conveyance_source` (`structured|extracted|player_text|document|fixture`), confidence. See `communication-and-knowledge.md`.

### observations

Actor + source event + sensory channel + `raw JSONB` (template-generated structure per `observation-authoring.md` §2) + optional `interpreted_text` (deterministic rule templates only) + confidence + game tick + visibility metadata. `heard_claim` observations reference `claim_id`. No model-written text is stored here.

### beliefs

Actor, optional linked fact/claim or free proposition, belief type (`known|believed|suspected|rumor|opinion|assumption|inference|false_memory|stated|doubted`), confidence, source type/actor, acquired/superseded events, status (`active|superseded|contested`), salience, metadata. Confidence and type are assigned by `belief-update-rules.md`; a `belief_processor` adjustment records the ModelRun.

At least one of fact, claim, or proposition is required.

### entity_identity_knowledge

Actor/entity, known name, confidence, optional recognized-as identity, learned event, status. Multiple aliases per entity allowed.

## 12. Memory, relationships, psychology

### memories

Actor, subjective summary, emotional interpretation, salience, emotional weight, specificity, accessibility, core flag, status (`detailed|compressed|fuzzy|inaccessible|altered`), parent memory, created/last-recalled ticks, embedding + model metadata, generic metadata.

Vector index should be created only after embedding dimensions are stable.

### memory_sources

Memory-to-event lineage with source role.

### relationships

Unique source actor → target entity row with trust, affection, respect, fear, resentment, obligation, familiarity, qualitative state, last-changed event.

Suggested signed dimensions -100..100; familiarity 0..100.

### relationship_deltas

Relationship, event, dimension, delta, reason. Every relationship change requires event-linked delta provenance.

### emotion_states

Actor, emotion key, intensity, source event, start/expiry ticks, decay rule, resolution event.

### goals

Campaign, owner type (`actor|faction|party`), owner ID, parent goal, description/type/priority/status/visibility/progress/deadline, created/resolved events.

### goal_targets

Goal/entity/target-role join.

### plans

Goal, status, current step, JSON steps, created/updated events.

## 13. Mysteries and clues

### mysteries

Campaign, question, status (`latent|active|solved|failed|abandoned`), `solution_locked BOOLEAN`, stakeholders/consequences, created/activated/resolved events.

### mystery_truth_facts

Join mystery to objective truth facts. When solution is locked, linked truth cannot be replaced without explicit debug retcon.

### clues

Mystery, supported fact, optional physical entity, reliability, discovery conditions, destructible/forgeable flags, state, created/destroyed events.

### clue_discoveries

Clue + actor + discovery event + `route` (`physical|document|testimony|inference|mechanic`) + optional `claim_id` + `fidelity`. Testimony discoveries point at the Claim that conveyed the supported fact.

## 14. Rules metadata

### rulesets

Key/name/version, engine schema version, manifest JSONB, content hash, installed timestamp. Unique key/version.

### rule_modules

Ruleset, module key/type/version, precedence, definition JSONB, content hash.

### mechanical_definitions

Ruleset and optional campaign, definition key/type, source kind/ref, version/status, JSON definition, content hash, power metadata, created/established events. Used especially for generated/campaign-specific content.

### ruling_precedents

Campaign, summary, mechanical definition, scope, usage count, created/last-used events, optional embedding metadata.

## 15. AI observability

### model_runs

Campaign/timeline, provider/model/profile, role, optional actor, prompt ID/version, ContextSnapshot, parameters, raw/structured output, validation result, status, latency/tokens, start/end timestamps.

### context_snapshots

Campaign/timeline, requesting role, optional actor, purpose, authorization scope, rendered context, estimated tokens, timestamp.

### context_items

Snapshot, source type/id, reason, retrieval score, authorization result, metadata. In development, any non-allowed item aborts the call.

### decision_traces

ModelRun/actor, eligible goals, relevant beliefs/memories/relationships/mechanics, selected intent, concise decision summary. No unrestricted hidden chain-of-thought.

### turn_metrics

One row per `turn_id`: wall/first-output/first-narration milliseconds, synchronous and background call counts, `calls_by_role JSONB`, token totals, `max_context_tokens`, `degradation_steps JSONB`, `budget_breached`, `claim_extractor_invoked`, `belief_processor_scheduled`. Schema in `turn-budget-and-latency.md` §7. Non-authoritative; excluded from state hashing.

## 16. Journal and encyclopedia projections

### journal_entries

Campaign/timeline/actor, entry type/title/body, event sequence range, game tick, optional source ModelRun, created timestamp.

### encyclopedia_entries

Campaign/timeline/actor/entity, category/display name, summary, structured knowledge, last-updated event. Rebuildable perspective projection.

## 17. Generation and jobs

### generation_runs / generation_stages

Track campaign generation run status, requested scope/profile, stage key/order/status/input/output/model run/error. Stages are independently rerunnable before play.

### background_jobs

Campaign/timeline, job type, optional subject, priority, payload, status, attempt counts, `not_before`, claim metadata, last error, timestamps. Worker uses `FOR UPDATE SKIP LOCKED`.

## 18. Version allocation

Every authoritative mutation transaction:

1. locks campaign row;
2. reads world version;
3. appends event(s);
4. updates projections;
5. increments world version;
6. records final version on event(s);
7. increments affected scene version;
8. commits atomically.

This supports stale-model-proposal detection.

## 19. Event sequence allocation

Timeline maintains `next_event_sequence`. A mutation transaction atomically reserves the required range before inserting events, preventing duplicate ordering under concurrency.

## 20. Retcon and deletion policy

Retcons create explicit compensating/superseding events/facts; historical events remain inspectable. For major development changes, branching is preferred.

Normal gameplay never hard-deletes actors, entities, items, facts, memories, events, documents, or relationships. Hard deletion is limited to unstarted generated material, test fixtures, explicit campaign deletion, or maintenance.

## 21. Data-access architecture

Conceptually separate `ObjectiveWorldRepository`, `PerspectiveRepository`, and `DebugRepository`. AI actor context code may never directly access objective-world repositories; it goes through PerspectiveService.

## 22. Core schema invariants

Tests must prove:

- every authoritative projection change references an Event;
- event ordering is unique/deterministic per timeline;
- established facts cannot silently change;
- locked mystery truth cannot silently change;
- actor perspective queries cannot expose unauthorized objective facts;
- controller changes preserve actor identity/state;
- item ownership and possession remain distinct;
- document original text is immutable;
- memory compression retains lineage;
- relationship changes retain event provenance;
- generated mechanics snapshot definitions;
- context snapshots preserve exact supplied sources;
- every `conveys` reference in a stored Claim was in the speaker's perspective at statement time;
- `deliberate_false` is never returned by perspective repositories;
- `scenes.local_tick` never exceeds the world clock;
- branches diverge without mutating parents.

## 23. Recommended Alembic grouping

1. `0001_campaign_timeline_clock`
2. `0002_entity_location`
3. `0003_actor_faction_party`
4. `0004_scene_event_transcript`
5. `0005_rules_actions_rolls`
6. `0006_resources_conditions_items`
7. `0007_knowledge`
8. `0008_memory_relationship_goals`
9. `0009_mysteries`
10. `0010_rules_metadata`
11. `0011_ai_observability`
12. `0012_generation_jobs`
13. `0013_journal_encyclopedia`

## 24. Schema acceptance scenario

One integration test should create a campaign/timeline/clock, Frostbridge actors/locations, objective murder fact known only to Renn, a private Alex→Elara whisper not available to Tomas, an Elara belief, a hidden-property dagger possessed by Alex without that property in his perspective, scheduled evidence destruction, relationship delta, memory + source links, and an Elara ContextSnapshot with no unauthorized facts; then reopen a fresh DB session and verify all state persists.
