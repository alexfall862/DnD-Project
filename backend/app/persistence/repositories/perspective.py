"""PerspectiveRepository — actor-scoped reads only.

Everything here answers "what does actor X hold / perceive / know by name?" and nothing else.
Objective rows are reachable only through the actor's own beliefs, observations and identity
knowledge, and only the columns that are the actor's to see are returned.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import (
    Actor,
    ActorAIProfile,
    ActorController,
    Belief,
    Claim,
    ConditionInstanceRow,
    EmotionState,
    Entity,
    EntityIdentityKnowledge,
    Goal,
    GoalTarget,
    Item,
    Observation,
    Relationship,
    ResourceStateRow,
    Scene,
    SceneParticipant,
)


@dataclass(frozen=True)
class HeardClaim:
    """A Claim as the recipient is entitled to see it: no deception flags, no speaker-side
    confidence, no source references."""

    claim_id: uuid.UUID
    speaker_actor_id: uuid.UUID
    statement_event_id: uuid.UUID
    subject_entity_id: uuid.UUID | None
    predicate: str
    object_entity_id: uuid.UUID | None
    object_value: Any
    stance: str


@dataclass(frozen=True)
class KnownItem:
    item_id: uuid.UUID
    entity_id: uuid.UUID
    template_key: str | None
    name: str | None
    equipped: bool
    public_properties: dict[str, Any] = field(default_factory=dict)


class PerspectiveRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def actor(self, actor_id: uuid.UUID) -> Actor | None:
        return await self.s.get(Actor, actor_id)

    async def self_name(self, actor_id: uuid.UUID) -> str | None:
        """An actor knows their own canonical name (public structural data about oneself)."""
        row = (
            await self.s.execute(
                select(Entity.canonical_name)
                .join(Actor, Actor.entity_id == Entity.id)
                .where(Actor.id == actor_id)
            )
        ).scalar_one_or_none()
        return row

    async def controller_type(self, actor_id: uuid.UUID) -> str | None:
        row = (
            await self.s.execute(
                select(ActorController.controller_type).where(
                    ActorController.actor_id == actor_id,
                    ActorController.valid_until_event_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        return row

    async def beliefs(
        self, actor_id: uuid.UUID, *, include_superseded: bool = False
    ) -> list[Belief]:
        q = select(Belief).where(Belief.actor_id == actor_id)
        if not include_superseded:
            q = q.where(Belief.status != "superseded")
        return list((await self.s.execute(q.order_by(Belief.created_at))).scalars().all())

    async def beliefs_about(self, actor_id: uuid.UUID, proposition_key: str) -> list[Belief]:
        return list(
            (
                await self.s.execute(
                    select(Belief).where(
                        Belief.actor_id == actor_id, Belief.proposition_key == proposition_key
                    )
                )
            )
            .scalars()
            .all()
        )

    async def holds_fact(self, actor_id: uuid.UUID, fact_id: uuid.UUID) -> bool:
        """The speaker may reference a fact only if it is in their perspective: an active
        belief of theirs points at it."""
        row = (
            await self.s.execute(
                select(Belief.id)
                .where(
                    Belief.actor_id == actor_id,
                    Belief.fact_id == fact_id,
                    Belief.status != "superseded",
                )
                .limit(1)
            )
        ).first()
        return row is not None

    async def holds_belief(self, actor_id: uuid.UUID, belief_id: uuid.UUID) -> Belief | None:
        b = await self.s.get(Belief, belief_id)
        return b if b is not None and b.actor_id == actor_id and b.status != "superseded" else None

    async def observations(
        self, actor_id: uuid.UUID, *, limit: int = 50, since_tick: int | None = None
    ) -> list[Observation]:
        q = select(Observation).where(Observation.actor_id == actor_id)
        if since_tick is not None:
            q = q.where(Observation.game_tick >= since_tick)
        rows = (
            (
                await self.s.execute(
                    q.order_by(Observation.game_tick.desc(), Observation.created_at.desc()).limit(
                        limit
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(reversed(rows))

    async def heard_claims(self, actor_id: uuid.UUID, *, limit: int = 50) -> list[HeardClaim]:
        q = (
            select(
                Claim.id,
                Claim.speaker_actor_id,
                Claim.statement_event_id,
                Claim.subject_entity_id,
                Claim.predicate,
                Claim.object_entity_id,
                Claim.object_value,
                Claim.speaker_stance,
            )
            .join(Observation, Observation.claim_id == Claim.id)
            .where(Observation.actor_id == actor_id)
            .order_by(Observation.game_tick.desc())
            .limit(limit)
        )
        return [HeardClaim(*row) for row in (await self.s.execute(q)).all()]

    async def identity_knowledge(
        self, actor_id: uuid.UUID
    ) -> dict[uuid.UUID, EntityIdentityKnowledge]:
        rows = (
            (
                await self.s.execute(
                    select(EntityIdentityKnowledge).where(
                        EntityIdentityKnowledge.actor_id == actor_id,
                        EntityIdentityKnowledge.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        return {r.entity_id: r for r in rows}

    async def resolve_name(self, actor_id: uuid.UUID, name: str) -> list[uuid.UUID]:
        """Entity resolution is perspective-specific: only names this actor knows resolve."""
        rows = (
            (
                await self.s.execute(
                    select(EntityIdentityKnowledge.entity_id).where(
                        EntityIdentityKnowledge.actor_id == actor_id,
                        EntityIdentityKnowledge.status == "active",
                        EntityIdentityKnowledge.known_name.ilike(name),
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def goals(self, actor_id: uuid.UUID) -> list[Goal]:
        """The actor's own active goals, highest priority first."""
        return list(
            (
                await self.s.execute(
                    select(Goal)
                    .where(
                        Goal.owner_type == "actor",
                        Goal.owner_id == actor_id,
                        Goal.status == "active",
                    )
                    .order_by(Goal.priority.desc(), Goal.created_at)
                )
            )
            .scalars()
            .all()
        )

    async def goal_target_entities(self, actor_id: uuid.UUID) -> set[uuid.UUID]:
        rows = (
            await self.s.execute(
                select(GoalTarget.entity_id)
                .join(Goal, Goal.id == GoalTarget.goal_id)
                .where(
                    Goal.owner_type == "actor",
                    Goal.owner_id == actor_id,
                    Goal.status == "active",
                )
            )
        ).all()
        return {r[0] for r in rows}

    async def emotions(self, actor_id: uuid.UUID) -> list[EmotionState]:
        return list(
            (
                await self.s.execute(
                    select(EmotionState)
                    .where(EmotionState.actor_id == actor_id, EmotionState.status == "active")
                    .order_by(EmotionState.intensity.desc())
                )
            )
            .scalars()
            .all()
        )

    async def ai_profile(self, actor_id: uuid.UUID) -> ActorAIProfile | None:
        return await self.s.get(ActorAIProfile, actor_id)

    async def relationships_from(self, actor_id: uuid.UUID) -> list[Relationship]:
        return list(
            (
                await self.s.execute(
                    select(Relationship).where(Relationship.source_actor_id == actor_id)
                )
            )
            .scalars()
            .all()
        )

    async def relationship(
        self, source_actor_id: uuid.UUID, target_entity_id: uuid.UUID
    ) -> Relationship | None:
        return (
            await self.s.execute(
                select(Relationship).where(
                    Relationship.source_actor_id == source_actor_id,
                    Relationship.target_entity_id == target_entity_id,
                )
            )
        ).scalar_one_or_none()

    async def current_scene(self, actor_id: uuid.UUID) -> Scene | None:
        p = (
            await self.s.execute(
                select(SceneParticipant).where(
                    SceneParticipant.actor_id == actor_id, SceneParticipant.left_event_id.is_(None)
                )
            )
        ).scalar_one_or_none()
        return await self.s.get(Scene, p.scene_id) if p else None

    async def scene_participants(self, scene_id: uuid.UUID) -> list[tuple[Actor, Entity]]:
        rows = (
            await self.s.execute(
                select(Actor, Entity)
                .join(SceneParticipant, SceneParticipant.actor_id == Actor.id)
                .join(Entity, Entity.id == Actor.entity_id)
                .where(
                    SceneParticipant.scene_id == scene_id, SceneParticipant.left_event_id.is_(None)
                )
            )
        ).all()
        return [(a, e) for a, e in rows]

    async def active_conditions(self, entity_ids: list[uuid.UUID]) -> dict[uuid.UUID, set[str]]:
        if not entity_ids:
            return {}
        rows = (
            await self.s.execute(
                select(
                    ConditionInstanceRow.target_entity_id, ConditionInstanceRow.condition_key
                ).where(
                    ConditionInstanceRow.target_entity_id.in_(entity_ids),
                    ConditionInstanceRow.status == "active",
                )
            )
        ).all()
        out: dict[uuid.UUID, set[str]] = {}
        for eid, key in rows:
            out.setdefault(eid, set()).add(key)
        return out

    async def own_resources(self, entity_id: uuid.UUID) -> list[ResourceStateRow]:
        return list(
            (
                await self.s.execute(
                    select(ResourceStateRow).where(ResourceStateRow.entity_id == entity_id)
                )
            )
            .scalars()
            .all()
        )

    async def possessed_items(self, entity_id: uuid.UUID) -> list[KnownItem]:
        """Items the actor holds, public properties only. `hidden_properties` is never selected."""
        q = (
            select(
                Item.id,
                Item.entity_id,
                Item.template_key,
                Entity.canonical_name,
                Item.mechanical_snapshot,
                Item.public_properties,
            )
            .join(Entity, Entity.id == Item.entity_id)
            .where(Item.possessor_entity_id == entity_id)
        )
        return [
            KnownItem(
                item_id=i,
                entity_id=e,
                template_key=t,
                name=n,
                equipped=bool((snap or {}).get("equipped", False)),
                public_properties=dict(pub or {}),
            )
            for i, e, t, n, snap, pub in (await self.s.execute(q)).all()
        ]
