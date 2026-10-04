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
    )
}


def parse_payload(event_type: str, payload: dict) -> EventPayload:
    """Validate a stored payload against its registered schema (current version only)."""
    try:
        cls = PAYLOAD_TYPES[event_type]
    except KeyError as exc:
        raise ValueError(f"unknown event type {event_type!r}") from exc
    return cls.model_validate(payload)
