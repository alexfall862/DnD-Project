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
from app.persistence.models.ai import (
    ContextItem,
    ContextSnapshot,
    DecisionTrace,
    ModelRun,
    TurnMetrics,
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
from app.persistence.models.knowledge import (
    Belief,
    Claim,
    EntityIdentityKnowledge,
    Fact,
    Observation,
    Relationship,
    RelationshipDelta,
)
from app.persistence.models.mechanics import (
    ConditionInstanceRow,
    Document,
    Item,
    ItemHistory,
    ResourceStateRow,
)
from app.persistence.models.memory import Memory, MemorySource
from app.persistence.models.mystery import Clue, ClueDiscovery, Mystery, MysteryTruthFact
from app.persistence.models.projections import EncyclopediaEntry, JournalEntry
from app.persistence.models.psychology import (
    ActorAIProfile,
    EmotionState,
    Goal,
    GoalTarget,
    Plan,
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
    "EncyclopediaEntry",
    "JournalEntry",
    "ActorAIProfile",
    "EmotionState",
    "Goal",
    "GoalTarget",
    "Plan",
    "ContextItem",
    "ContextSnapshot",
    "DecisionTrace",
    "ModelRun",
    "TurnMetrics",
    "Memory",
    "MemorySource",
    "Mystery",
    "MysteryTruthFact",
    "Clue",
    "ClueDiscovery",
    "Belief",
    "Claim",
    "EntityIdentityKnowledge",
    "Fact",
    "Observation",
    "Relationship",
    "RelationshipDelta",
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
