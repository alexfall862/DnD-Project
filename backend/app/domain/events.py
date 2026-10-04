"""Event types and typed payloads for the world/event ledger (Milestone 01).

Every authoritative state change is one of these. Payloads are versioned (`payload_version`
on the row); no upcasters exist before v0.1, so a payload change means `make reset-db`.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class EventPayload(BaseModel):
    """Base for all payloads. Subclasses declare `event_type`."""

    model_config = ConfigDict(extra="forbid")
    event_type: ClassVar[str]
    payload_version: ClassVar[int] = 1


class CampaignCreated(EventPayload):
    event_type: ClassVar[str] = "campaign.created"
    name: str
    ruleset_key: str
    ruleset_version: str


class LocationCreated(EventPayload):
    event_type: ClassVar[str] = "location.created"
    location_id: uuid.UUID
    entity_id: uuid.UUID
    name: str
    location_type: str
    parent_location_id: uuid.UUID | None = None


class LocationsConnected(EventPayload):
    event_type: ClassVar[str] = "location.connected"
    edge_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    relationship_type: str
    travel_seconds: int | None = None
    bidirectional: bool = True


class ActorCreated(EventPayload):
    event_type: ClassVar[str] = "actor.created"
    actor_id: uuid.UUID
    entity_id: uuid.UUID
    name: str
    actor_type: str
    controller_type: str
    location_id: uuid.UUID | None = None


class ActorControllerChanged(EventPayload):
    event_type: ClassVar[str] = "actor.controller_changed"
    actor_id: uuid.UUID
    from_controller: str
    to_controller: str
    user_key: str | None = None


class ActorMoved(EventPayload):
    event_type: ClassVar[str] = "actor.moved"
    actor_id: uuid.UUID
    from_location_id: uuid.UUID | None
    to_location_id: uuid.UUID
    left_scene_id: uuid.UUID | None = None


class SceneStarted(EventPayload):
    event_type: ClassVar[str] = "scene.started"
    scene_id: uuid.UUID
    location_id: uuid.UUID | None
    scene_type: str
    participant_actor_ids: list[uuid.UUID] = Field(default_factory=list)


class SceneParticipantJoined(EventPayload):
    event_type: ClassVar[str] = "scene.participant_joined"
    scene_id: uuid.UUID
    actor_id: uuid.UUID


class SceneParticipantLeft(EventPayload):
    event_type: ClassVar[str] = "scene.participant_left"
    scene_id: uuid.UUID
    actor_id: uuid.UUID


class SceneEnded(EventPayload):
    event_type: ClassVar[str] = "scene.ended"
    scene_id: uuid.UUID


class TimeAdvanced(EventPayload):
    event_type: ClassVar[str] = "time.advanced"
    from_tick: int
    to_tick: int
    seconds: int
    reason: str


class MechanicEvent(EventPayload):
    """Base for engine-mechanics events emitted by the action resolver. Payloads carry the
    resolver's structured detail; extra keys are allowed because each mechanic has its own."""

    model_config = ConfigDict(extra="allow")
    actor: str  # actor UUID string


class ActionResolved(MechanicEvent):
    event_type: ClassVar[str] = "action.resolved"
    action: str
    target: str | None = None
    status: str
    time_cost_seconds: int = 0
    action_id: str | None = None


class AttackRolled(MechanicEvent):
    event_type: ClassVar[str] = "attack.rolled"
    target: str
    weapon: str
    total: int
    versus: int | None = None
    success: bool | None = None
    degree: str | None = None
    roll: dict[str, Any] = Field(default_factory=dict)


class DamageDealt(MechanicEvent):
    event_type: ClassVar[str] = "damage.dealt"
    target: str
    amount: int
    damage_type: str
    remaining: int


class ActorIncapacitated(MechanicEvent):
    event_type: ClassVar[str] = "actor.incapacitated"
    by: str | None = None


class ActorRepositioned(MechanicEvent):
    event_type: ClassVar[str] = "actor.repositioned"
    from_zone: str
    to_zone: str
    disengaged_from: list[str] = Field(default_factory=list)


class ActorEngaged(MechanicEvent):
    event_type: ClassVar[str] = "actor.engaged"
    target: str


class ActorDisengaged(MechanicEvent):
    event_type: ClassVar[str] = "actor.disengaged"
    unsafe: bool = False


class ActorTookCover(MechanicEvent):
    event_type: ClassVar[str] = "actor.took_cover"
    level: str


class ActorRested(MechanicEvent):
    event_type: ClassVar[str] = "actor.rested"
    kind: str


class CheckRolled(MechanicEvent):
    event_type: ClassVar[str] = "check.rolled"
    action: str
    check: str
    total: int
    versus: int | None = None
    success: bool | None = None
    degree: str | None = None


class ItemPickedUp(MechanicEvent):
    event_type: ClassVar[str] = "item.picked_up"
    item: str
    zone: str


class ItemDropped(MechanicEvent):
    event_type: ClassVar[str] = "item.dropped"
    item: str
    zone: str


class ActorFled(MechanicEvent):
    event_type: ClassVar[str] = "actor.fled"
    via: str


class ActorSurrendered(MechanicEvent):
    event_type: ClassVar[str] = "actor.surrendered"


class EncounterStarted(EventPayload):
    event_type: ClassVar[str] = "encounter.started"
    scene_id: uuid.UUID
    order: list[str]
    sides: dict[str, str]


class EncounterRoundEnded(EventPayload):
    event_type: ClassVar[str] = "encounter.round_ended"
    scene_id: uuid.UUID
    round: int


class EncounterEnded(EventPayload):
    event_type: ClassVar[str] = "encounter.ended"
    scene_id: uuid.UUID
    standing: list[str]
    rounds: int


class ItemCreated(EventPayload):
    event_type: ClassVar[str] = "item.created"
    item_id: uuid.UUID
    entity_id: uuid.UUID
    name: str
    template_key: str | None = None
    possessor_actor_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None


class SpeechUttered(EventPayload):
    """An utterance reached the scene. Verbatim text lives in transcript_messages; the payload
    carries structure only, so the ledger is not itself a leak channel."""

    event_type: ClassVar[str] = "speech.uttered"
    speaker_actor_id: uuid.UUID
    channel: str  # say | whisper
    language: str = "common"
    transcript_message_id: uuid.UUID | None = None
    target_actor_ids: list[uuid.UUID] = Field(default_factory=list)
    recipient_actor_ids: list[uuid.UUID] = Field(default_factory=list)  # who actually received it
    claim_count: int = 0


class FactCreated(EventPayload):
    event_type: ClassVar[str] = "fact.created"
    fact_id: uuid.UUID
    key: str | None = None
    canon_status: str
    sensitivity: str = "public"


class FactEstablished(EventPayload):
    event_type: ClassVar[str] = "fact.established"
    fact_id: uuid.UUID
    key: str | None = None
    reason: str = ""


class IdentityLearned(EventPayload):
    event_type: ClassVar[str] = "identity.learned"
    actor_id: uuid.UUID
    entity_id: uuid.UUID
    known_name: str
    recognized_as_entity_id: uuid.UUID | None = None


class RelationshipSeeded(EventPayload):
    event_type: ClassVar[str] = "relationship.seeded"
    source_actor_id: uuid.UUID
    target_entity_id: uuid.UUID
    values: dict[str, int] = Field(default_factory=dict)


class BeliefSeeded(EventPayload):
    event_type: ClassVar[str] = "belief.seeded"
    actor_id: uuid.UUID
    proposition_key: str
    belief_type: str
    confidence: float
    fact_id: uuid.UUID | None = None


class LeakageRejected(EventPayload):
    """A proposal referenced knowledge outside the speaker's perspective. Recorded for audit;
    nothing else about the proposal is persisted."""

    event_type: ClassVar[str] = "proposal.rejected_leakage"
    actor_id: uuid.UUID
    ref_kind: str
    ref_id: str
    reason: str


class GoalCreated(EventPayload):
    event_type: ClassVar[str] = "goal.created"
    goal_id: uuid.UUID
    owner_type: str
    owner_id: uuid.UUID
    description: str
    priority: int = 50
    visibility: str = "private"


class GoalUpdated(EventPayload):
    event_type: ClassVar[str] = "goal.updated"
    goal_id: uuid.UUID
    owner_id: uuid.UUID
    changes: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class EmotionChanged(EventPayload):
    event_type: ClassVar[str] = "emotion.changed"
    actor_id: uuid.UUID
    emotion_key: str
    intensity: float
    source: str = "proposal"  # proposal | rule | seed


class RelationshipChanged(EventPayload):
    """Every relationship change carries event-linked delta provenance (world-memory §11)."""

    event_type: ClassVar[str] = "relationship.changed"
    source_actor_id: uuid.UUID
    target_entity_id: uuid.UUID
    dimension: str
    delta: int
    reason: str = ""


class ProposalInvalidated(EventPayload):
    """An AI proposal was revalidated against current state and rejected (orchestration §18,
    §34): the target is gone, the item was taken, the scene version moved."""

    event_type: ClassVar[str] = "proposal.invalidated"
    actor_id: uuid.UUID
    action_key: str | None = None
    target: str | None = None
    reason: str = ""
    based_on_scene_version: int | None = None
    fallback_used: bool = False


class BeliefFormed(EventPayload):
    """A belief created from an AI actor's own proposal or inference (never `known`)."""

    event_type: ClassVar[str] = "belief.formed"
    actor_id: uuid.UUID
    proposition_key: str
    belief_type: str
    confidence: float
    model_run_id: uuid.UUID | None = None


class BeliefAdjusted(EventPayload):
    """Belief Processor adjustment within ±0.25 of the deterministic default."""

    event_type: ClassVar[str] = "belief.adjusted"
    actor_id: uuid.UUID
    belief_id: uuid.UUID
    confidence_before: float
    confidence_after: float
    model_run_id: uuid.UUID | None = None
    reason: str = ""


class AutonomyPaused(EventPayload):
    """An AI proposal fell under an autonomy domain configured `ask`/`suggest_only`/`blocked`;
    the engine paused or dropped it regardless of what the model wanted."""

    event_type: ClassVar[str] = "autonomy.paused"
    actor_id: uuid.UUID
    domain: str
    level: str
    action_key: str | None = None
    target: str | None = None


class CanonDetailAdded(EventPayload):
    """Post-narration decoration persisted as `latent` canon (canon-extraction-allowlist §2)."""

    event_type: ClassVar[str] = "canon.detail_added"
    classification: str
    description: str
    location_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    model_run_id: uuid.UUID | None = None


class CanonDetailEstablished(EventPayload):
    """A latent detail a later player action referenced (search the barrels)."""

    event_type: ClassVar[str] = "canon.detail_established"
    description: str
    location_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None


class JournalEntryWritten(EventPayload):
    event_type: ClassVar[str] = "journal.entry_written"
    actor_id: uuid.UUID
    entry_id: uuid.UUID
    entry_type: str = "session"
    model_run_id: uuid.UUID | None = None


class MemoryCheckpoint(EventPayload):
    """Memory processing ran (or was deferred) for an actor at a checkpoint."""

    event_type: ClassVar[str] = "memory.checkpoint"
    actor_id: uuid.UUID
    reason: str
    observations: int = 0
    memories_created: int = 0
    deferred: bool = False


class MemoryCreated(EventPayload):
    event_type: ClassVar[str] = "memory.created"
    memory_id: uuid.UUID
    actor_id: uuid.UUID
    is_core: bool = False
    source_event_ids: list[uuid.UUID] = Field(default_factory=list)


class MemoryCompressed(EventPayload):
    event_type: ClassVar[str] = "memory.compressed"
    memory_id: uuid.UUID
    actor_id: uuid.UUID
    compressed_ids: list[uuid.UUID] = Field(default_factory=list)


# -- Milestone 07: mysteries, clues, documents, scheduling, factions, scene transitions ----------


class MysteryCreated(EventPayload):
    event_type: ClassVar[str] = "mystery.created"
    mystery_id: uuid.UUID
    key: str | None = None
    question: str
    truth_fact_ids: list[uuid.UUID] = Field(default_factory=list)


class MysteryActivated(EventPayload):
    """Activation locks the objective answer (Invariant 10)."""

    event_type: ClassVar[str] = "mystery.activated"
    mystery_id: uuid.UUID
    solution_locked: bool = True


class ClueCreated(EventPayload):
    event_type: ClassVar[str] = "clue.created"
    clue_id: uuid.UUID
    mystery_id: uuid.UUID
    key: str | None = None
    supported_fact_id: uuid.UUID | None = None
    physical_entity_id: uuid.UUID | None = None
    clue_type: str


class ClueDiscovered(EventPayload):
    event_type: ClassVar[str] = "clue.discovered"
    clue_id: uuid.UUID
    actor_id: uuid.UUID
    route: str  # physical|document|testimony|inference|mechanic
    fidelity: str = "full"
    claim_id: uuid.UUID | None = None


class ClueDestroyed(EventPayload):
    event_type: ClassVar[str] = "clue.destroyed"
    clue_id: uuid.UUID
    reason: str = ""


class ItemRevealed(MechanicEvent):
    """A concealed item in the searched zone becomes visible (actor = the searcher)."""

    event_type: ClassVar[str] = "item.revealed"
    item: str
    zone: str
    name: str = ""


class ItemDestroyed(EventPayload):
    event_type: ClassVar[str] = "item.destroyed"
    item_id: uuid.UUID
    reason: str = ""


class DocumentRead(EventPayload):
    event_type: ClassVar[str] = "document.read"
    actor_id: uuid.UUID
    item_id: uuid.UUID
    claim_count: int = 0


class ScheduledEventCreated(EventPayload):
    event_type: ClassVar[str] = "scheduled_event.created"
    scheduled_event_id: uuid.UUID
    scheduled_tick: int
    scheduled_type: str


class ScheduledEventFired(EventPayload):
    event_type: ClassVar[str] = "scheduled_event.fired"
    scheduled_event_id: uuid.UUID
    scheduled_tick: int
    scheduled_type: str
    outcome: str  # processed|cancelled|skipped
    detail: dict[str, Any] = Field(default_factory=dict)


class FactionCreated(EventPayload):
    event_type: ClassVar[str] = "faction.created"
    faction_id: uuid.UUID
    name: str
    member_actor_ids: list[uuid.UUID] = Field(default_factory=list)


class PlanCreated(EventPayload):
    event_type: ClassVar[str] = "plan.created"
    plan_id: uuid.UUID
    goal_id: uuid.UUID
    steps: int


class PlanAdvanced(EventPayload):
    event_type: ClassVar[str] = "plan.advanced"
    plan_id: uuid.UUID
    from_step: int
    to_step: int
    reason: str = ""


class PartyCreated(EventPayload):
    event_type: ClassVar[str] = "party.created"
    party_id: uuid.UUID
    name: str
    member_actor_ids: list[uuid.UUID] = Field(default_factory=list)


class ScenesMerged(EventPayload):
    """Reunion (time-accounting §5): participants of `from_scene_id` join `into_scene_id`;
    no Observations or Claims are created."""

    event_type: ClassVar[str] = "scene.merged"
    from_scene_id: uuid.UUID
    into_scene_id: uuid.UUID
    actor_ids: list[uuid.UUID] = Field(default_factory=list)


class SceneCaughtUp(EventPayload):
    """An offscreen scene's local clock fast-forwarded to the world clock."""

    event_type: ClassVar[str] = "scene.caught_up"
    scene_id: uuid.UUID
    from_tick: int
    to_tick: int
    model_calls: int = 0


class EntityCreated(EventPayload):
    """A non-actor, non-location, non-item entity (culture, conflict, pressure, opportunity)."""

    event_type: ClassVar[str] = "entity.created"
    entity_id: uuid.UUID
    entity_type: str
    name: str


class FactionMemberJoined(EventPayload):
    event_type: ClassVar[str] = "faction.member_joined"
    faction_id: uuid.UUID
    actor_id: uuid.UUID
    role: str | None = None


class LocationMaterialized(EventPayload):
    """Progressive materialization (campaign-generation §27): latent → materialized."""

    event_type: ClassVar[str] = "location.materialized"
    location_id: uuid.UUID
    from_detail: str
    zones: int = 0


class CampaignStarted(EventPayload):
    event_type: ClassVar[str] = "campaign.started"
    generation_run_id: uuid.UUID | None = None
    opening_scene_id: uuid.UUID | None = None
    player_actor_id: uuid.UUID | None = None


class SimulationRunCompleted(EventPayload):
    """One bounded world-simulation run (world-memory §23): interval, candidates, budget."""

    event_type: ClassVar[str] = "simulation.run"
    from_tick: int
    to_tick: int
    event_budget: int
    candidates: list[str] = Field(default_factory=list)
    model_calls: int = 0
    applied: int = 0
    rejected: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)


class MechanicalDefinitionCreated(EventPayload):
    event_type: ClassVar[str] = "mechanical_definition.created"
    definition_id: uuid.UUID
    definition_key: str
    definition_type: str
    source_kind: str


PAYLOAD_TYPES: dict[str, type[EventPayload]] = {
    cls.event_type: cls
    for cls in (
        CampaignCreated,
        LocationCreated,
        LocationsConnected,
        ActorCreated,
        ActorControllerChanged,
        ActorMoved,
        SceneStarted,
        SceneParticipantJoined,
        SceneParticipantLeft,
        SceneEnded,
        TimeAdvanced,
        ActionResolved,
        AttackRolled,
        DamageDealt,
        ActorIncapacitated,
        ActorRepositioned,
        ActorEngaged,
        ActorDisengaged,
        ActorTookCover,
        ActorRested,
        CheckRolled,
        ItemPickedUp,
        ItemDropped,
        ActorFled,
        ActorSurrendered,
        EncounterStarted,
        EncounterRoundEnded,
        EncounterEnded,
        ItemCreated,
        SpeechUttered,
        FactCreated,
        FactEstablished,
        IdentityLearned,
        RelationshipSeeded,
        BeliefSeeded,
        LeakageRejected,
        MemoryCreated,
        MemoryCompressed,
        GoalCreated,
        GoalUpdated,
        EmotionChanged,
        RelationshipChanged,
        ProposalInvalidated,
        AutonomyPaused,
        BeliefFormed,
        BeliefAdjusted,
        CanonDetailAdded,
        CanonDetailEstablished,
        JournalEntryWritten,
        MemoryCheckpoint,
        MysteryCreated,
        MysteryActivated,
        ClueCreated,
        ClueDiscovered,
        ClueDestroyed,
        ItemRevealed,
        ItemDestroyed,
        DocumentRead,
        ScheduledEventCreated,
        ScheduledEventFired,
        FactionCreated,
        PlanCreated,
        PlanAdvanced,
        PartyCreated,
        ScenesMerged,
        SceneCaughtUp,
        MechanicalDefinitionCreated,
        SimulationRunCompleted,
        EntityCreated,
        FactionMemberJoined,
        LocationMaterialized,
        CampaignStarted,
    )
}


def parse_payload(event_type: str, payload: dict) -> EventPayload:
    """Validate a stored payload against its registered schema (current version only)."""
    try:
        cls = PAYLOAD_TYPES[event_type]
    except KeyError as exc:
        raise ValueError(f"unknown event type {event_type!r}") from exc
    return cls.model_validate(payload)
