"""SQLAlchemy ORM models (projections + ledger).

Grouped per docs/specifications/database-schema.md §23. Import every module here so
`Base.metadata` is complete for Alembic and tests.
"""

from app.persistence.models.actor import (
    Actor,
    ActorController,
    Faction,
    FactionMembership,
    Party,
    PartyMembership,
)
from app.persistence.models.base import Base
from app.persistence.models.campaign import Campaign, Timeline, WorldClock
from app.persistence.models.entity import Entity, Location, LocationEdge
from app.persistence.models.event import (
    Event,
    EventEntity,
    ScheduledEvent,
    TranscriptMessage,
    TranscriptRecipient,
)
from app.persistence.models.mechanics import (
    ConditionInstanceRow,
    Document,
    Item,
    ItemHistory,
    ResourceStateRow,
)
from app.persistence.models.rules import (
    Action,
    ActionStep,
    Intent,
    MechanicalDefinition,
    PendingClarification,
    ReactionEligibleActor,
    ReactionWindowRecord,
    ResolutionTraceRecord,
    Roll,
    RuleModule,
    RulesetRecord,
    RulingPrecedent,
)
from app.persistence.models.scene import Scene, SceneParticipant

__all__ = [
    "Action",
    "ActionStep",
    "ConditionInstanceRow",
    "Document",
    "Intent",
    "Item",
    "ItemHistory",
    "MechanicalDefinition",
    "PendingClarification",
    "ReactionEligibleActor",
    "ReactionWindowRecord",
    "ResolutionTraceRecord",
    "ResourceStateRow",
    "Roll",
    "RuleModule",
    "RulesetRecord",
    "RulingPrecedent",
    "Actor",
    "ActorController",
    "Base",
    "Campaign",
    "Entity",
    "Event",
    "EventEntity",
    "Faction",
    "FactionMembership",
    "Location",
    "LocationEdge",
    "Party",
    "PartyMembership",
    "ScheduledEvent",
    "Scene",
    "SceneParticipant",
    "Timeline",
    "TranscriptMessage",
    "TranscriptRecipient",
    "WorldClock",
]
