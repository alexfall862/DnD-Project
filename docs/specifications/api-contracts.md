# REST API Contracts v0.2

## 1. Philosophy

Base path: `/api/v1`.

Normal endpoints are actor-perspective-safe by default. The backend does not send omniscient data and rely on the frontend to hide it. Debug endpoints are separate and require debug mode.

Requests/responses are JSON, IDs are UUID strings, real timestamps are ISO-8601 UTC, fictional time is `game_tick`, pagination uses opaque cursors, and FastAPI/Pydantic should generate a usable OpenAPI contract for frontend TypeScript generation.

## 2. Standard errors

```json
{
  "error": {
    "code": "ACTION_INVALID",
    "message": "The target is no longer available.",
    "details": {},
    "request_id": "uuid"
  }
}
```

Common codes: NOT_FOUND, VALIDATION_ERROR, CAMPAIGN_NOT_PLAYABLE, ACTION_INVALID, ACTION_NEEDS_CLARIFICATION, RULE_RESOLUTION_FAILED, STALE_STATE, UNAUTHORIZED_PERSPECTIVE, MODEL_UNAVAILABLE, MODEL_OUTPUT_INVALID, WORLDGEN_FAILED, DEBUG_MODE_REQUIRED, CONFLICT.

## 3. Pagination

Use `?limit=50&cursor=<opaque>` and return `{items, next_cursor}`.

## 4. Health

`GET /health` returns application/database status and engine version. It must not fail merely because the LLM provider is offline.

Optional `GET /health/providers` reports provider reachability.

## 5. Campaigns

### GET `/campaigns`

Returns campaign summaries: id/name/status/mode/ruleset/updated time.

### POST `/campaigns`

Creates draft campaign plus root Timeline and WorldClock.

Request includes name, creation mode, campaign mode, ruleset key/version, settings.

### GET `/campaigns/{id}`

Returns non-secret campaign metadata, current world time display, active timeline, settings.

### PATCH `/campaigns/{id}`

Normal mode can change name/description, narration/UI preferences, simulation preferences, model-routing choices, and the tunables listed in `testing/design-iteration.md` §5 (`player_canon_policy`, `spectator_mode`, spotlight budgets, reaction thresholds, conversation time bands, latency budgets). None rewrite established world truth. Each change is recorded as a `settings.changed` event.

## 6. Campaign brief and generation

### PUT `/campaigns/{id}/brief`

Stores structured genre/tone/technology/supernatural/simulation/party preferences.

### POST `/campaigns/{id}/generation-runs`

Starts a tracked generation run (`202`) with scope/model profile.

### GET `/generation-runs/{run_id}`

Returns stage statuses.

### POST `/generation-runs/{run_id}/stages/{stage}/regenerate`

Pre-play only; optionally accepts guidance and returns dependent invalidated stages.

### GET `/campaigns/{id}/generation-preview`

Shows user-requested pre-play world preview. Surprise-mode secrets remain hidden unless explicitly requested under debug.

### POST `/campaigns/{id}/start`

Validates world, ruleset, player actor, and opening scene; locks relevant initial canon and sets active status.

## 7. Characters

### POST `/campaigns/{id}/characters`

Manual character creation. Returns actor/entity IDs and validation/missing steps.

### POST `/campaigns/{id}/characters/generate`

AI-assisted creation from concept/preferences. Generated mechanics still pass character-creation validation.

### GET `/characters/{actor_id}`

Perspective-safe character detail. AI companion private thoughts/goals are not exposed just because the caller knows the actor ID.

### GET `/characters/{actor_id}/sheet`

Returns attributes, skills, resources, derived stats, abilities, visible conditions.

### PATCH `/characters/{actor_id}/sheet`

Normal mode allows legal pre-play edits or advancement. Illegal changes return validation errors. Debug override is separate.

### GET `/characters/{actor_id}/inventory`

Returns actor-known item properties only. Hidden item mechanics remain absent until discovered.

## 8. Scene

### GET `/campaigns/{id}/scene`

Returns current scene from the requesting player actor's perspective: location, world time, visible/known participants, visible state, known scene details. Hidden/invisible/unknown actors remain absent.

Optional actor query may be supported for debug/multiplayer preparation but normal authorization still applies.

## 9. Primary gameplay endpoint

### POST `/campaigns/{id}/play`

Request:

```json
{
  "actor_id": "uuid",
  "channel": "auto",
  "text": "I ask the innkeeper whether Renn was here last night.",
  "client_state": {
    "known_world_version": 152,
    "known_scene_version": 31
  }
}
```

Channels: auto, do, say, whisper, private, ooc.

Response can include:

- `turn_id`
- `narration`
- structured speaker messages
- visible rolls
- mechanical notices
- authoritative player/party-visible state changes
- current world/scene versions
- `needs_player_input`
- `metrics` (`sync_model_calls`, `wall_ms_total`, `ms_to_first_narration_token`, `degradation_steps[]`) — see `turn-budget-and-latency.md` §7
- optional debug trace ID

The frontend treats narration/messages as presentation and visible rolls/state changes/versions as authoritative. It never parses prose to infer mechanics.

### 9a. Streaming

`POST /campaigns/{id}/play` with `Accept: text/event-stream` streams the turn as SSE events in
this order: `accepted {turn_id}` → `mechanics {visible_rolls, state_changes, versions}` →
`speaker {actor, text}` (zero or more, as each AI line is validated) → `narration_delta {text}`
(zero or more) → `complete {metrics, needs_player_input}` or `error {code}`. `mechanics` is
always emitted before any `narration_delta` so the client can show what happened within the
first-output budget. The non-streaming response is the same content assembled.

### 9b. Focus actor and spectator

`actor_id` must be a human-controlled actor; it is the **focus actor** for the turn
(`human-visibility.md` §2). Scene/inventory/journal/encyclopedia endpoints take the same
`actor_id` and evaluate against that actor's perspective. When `settings.spectator_mode` is
not `off`, the response/stream may include `ooc_offscreen[]` entries for offscreen scenes;
they are labelled OOC and carry no authoritative state for the focus actor.

## 10. Clarification

When material ambiguity blocks resolution, return `409 ACTION_NEEDS_CLARIFICATION` with concise question, candidate visible entities, original input and a `clarification_id`. No partial action commits. The pending clarification is stored (`pending_clarifications`) so the next `/play` request may answer it by `clarification_id` instead of restating the action; an unrelated next input cancels it. Refused player assertions (`player-authored-canon.md` §3) use the same mechanism with `reason = ASSERTION_REFUSED`.

## 11. Explicit whisper and OOC

Play requests may include `target_actor_ids` for explicit whisper; explicit targets override inference.

OOC input changes configuration or requests out-of-world behavior and does not become an in-world event.

## 12. Visible rolls

Visible roll objects expose expression, raw dice, modifier, total, purpose, outcome. Hidden rolls are omitted in production but may be surfaced in debug with a hidden-in-production marker.

## 13. Party

`GET /campaigns/{id}/party` returns members, controller types, visible health/status, and shared resources. It does not reveal hidden numeric relationship state or private AI goals.

## 14. Journal

`GET /characters/{actor_id}/journal` returns perspective-specific entries and may contain character misconceptions.

## 15. Encyclopedia

`GET /characters/{actor_id}/encyclopedia` with optional category plus detail endpoint by entity ID. Known facts and suspicions remain distinguishable. Knowing an entity ID never grants hidden objective facts.

## 16. Rules

`GET /campaigns/{id}/rules` returns ruleset/module/house-rule metadata.

`GET /campaigns/{id}/rules/{definition_key}` returns player-appropriate rule definition; hidden item mechanics are not exposed through generic lookup unless authorized.

## 17. Timelines

`GET /campaigns/{id}/timelines` returns branches the user is allowed to see. Branch creation/switching is initially debug-only.

## 18. Debug boundary

All debug endpoints live under `/api/v1/debug` and require `DEBUG_MODE=true`; otherwise `403 DEBUG_MODE_REQUIRED`.

Debug may be omniscient and must use separate service/repository paths from normal APIs.

### Debug endpoints

- `GET /debug/campaigns/{id}/state`
- `GET /debug/campaigns/{id}/events`
- `GET /debug/campaigns/{id}/facts`
- `GET /debug/actors/{id}/perspective`
- `GET /debug/campaigns/{id}/perspectives/compare`
- `GET /debug/model-runs`
- `GET /debug/model-runs/{id}`
- `GET /debug/context/{id}`
- `GET /debug/actions/{id}/resolution`
- `GET /debug/jobs`
- `GET /debug/campaigns/{id}/turn-metrics`
- `GET /debug/campaigns/{id}/scenes` (live and offscreen scenes with `local_tick`)
- `GET /debug/claims?event_id=` (Claims with private deception flags and `conveys` provenance)
- `POST /debug/campaigns/{id}/time/advance`
- `POST /debug/actors/{id}/controller`
- `PATCH /debug/characters/{id}/sheet`
- `POST /debug/campaigns/{id}/branches`
- `POST /debug/campaigns/{id}/active-timeline`
- `POST /debug/campaigns/{id}/retcons`

## 19. Perspective comparison

A debug comparison endpoint should display objective state side-by-side with each selected actor's known names/beliefs/observations. This is expected to become one of the most useful debugging tools.

## 20. Model/context debug detail

ModelRun detail exposes role, model/provider/profile, prompt version, ContextSnapshot reference, parameters, raw/structured output, validation result, timing/tokens.

ContextSnapshot detail exposes rendered context plus each source item, retrieval reason/score, and authorization result.

## 21. Debug time/control/retcon

Time advance accepts engine seconds and a `process_simulation` flag.

Controller switch changes only control history.

Sheet override creates an explicit debug event.

Branch creation specifies source event and name. Switching active timeline changes campaign projection to that branch.

Retcon creates an explicit `world.retcon_applied`/superseding event rather than mutating history in place.

## 22. Provider configuration

`GET /settings/providers` reports logical profile routing and provider availability without credentials.

`PATCH /settings/providers` can update logical profile routing. Credentials remain environment-managed.

## 23. Optimistic concurrency

Mutation requests, especially `/play`, submit known world/scene versions. If stale state cannot safely revalidate, return `409 STALE_STATE` with current versions.

Even in single-user v0.1 this protects concurrent AI decisions and prepares for multiplayer.

## 24. Idempotency and request IDs

Retry-prone mutation endpoints should accept `Idempotency-Key`, especially `/play`, generation start, and debug time advance.

All responses include `X-Request-ID`; supplied IDs are preserved and correlate logs/events/model runs/debug traces.

## 25. Turn correlation

A `turn_id` links player transcript input, Intent, Actions, Events, Rolls, AI ModelRuns, ContextSnapshots, narration, and memory jobs. A dedicated turns table is optional; metadata correlation is sufficient for v0.1.

## 26. Normal endpoint boundary

Normal endpoints may expose only what the human-controlled character knows/can inspect, public rules, visible party status, own sheet, and perspective journal/encyclopedia.

They must not expose objective secrets, private AI thoughts, undiscovered clues, hidden item properties, latent canon, mystery answers, offscreen NPC actions, hidden rolls, or raw omniscient events.

## 27. OpenAPI

Every major request/response is an explicit Pydantic schema; avoid anonymous dict responses. OpenAPI is the frontend type-generation and manual-debug contract.

## 28. Implementation order

1. health
2. campaign CRUD
3. character create/read
4. current scene
5. deterministic play
6. perspective-safe inventory
7. journal/encyclopedia
8. debug events/state
9. debug perspective/context
10. generation APIs
11. provider inspection
12. branch/retcon operations

The first `/play` can accept structured deterministic actions before natural-language orchestration is complete.

## 29. API acceptance scenario

A client can create/seed Frostbridge, create human PC, start campaign, inspect scene, ask Mira about Renn, privately whisper Elara, verify through debug that Tomas did not receive it, perform a programmatic check, find the dagger without seeing its hidden property, advance three days to destroy evidence, reload the campaign, and continue play without direct database access.
