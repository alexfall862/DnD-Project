"""ObjectiveWorldRepository — omniscient reads for engine services, seeding and debug.

Never import this from perspective/context code (Invariant 3)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import (
    Actor,
    Belief,
    Claim,
    Entity,
    EntityIdentityKnowledge,
    Fact,
    Item,
    Observation,
    Relationship,
    SceneParticipant,
)


class ObjectiveWorldRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def fact(self, fact_id: uuid.UUID) -> Fact | None:
        return await self.s.get(Fact, fact_id)

    async def fact_by_key(self, campaign_id: uuid.UUID, key: str) -> Fact | None:
        return (
            await self.s.execute(
                select(Fact).where(Fact.campaign_id == campaign_id, Fact.key == key)
            )
        ).scalar_one_or_none()

    async def facts(self, campaign_id: uuid.UUID) -> list[Fact]:
        return list(
            (
                await self.s.execute(
                    select(Fact).where(Fact.campaign_id == campaign_id).order_by(Fact.created_at)
                )
            )
            .scalars()
            .all()
        )

    async def claims_for_event(self, event_id: uuid.UUID) -> list[Claim]:
        return list(
            (await self.s.execute(select(Claim).where(Claim.statement_event_id == event_id)))
            .scalars()
            .all()
        )

    async def claims(self, campaign_id: uuid.UUID) -> list[Claim]:
        return list(
            (
                await self.s.execute(
                    select(Claim).where(Claim.campaign_id == campaign_id).order_by(Claim.created_at)
                )
            )
            .scalars()
            .all()
        )

    async def beliefs_all(self, campaign_id: uuid.UUID) -> list[Belief]:
        return list(
            (await self.s.execute(select(Belief).where(Belief.campaign_id == campaign_id)))
            .scalars()
            .all()
        )

    async def observations_for_event(self, event_id: uuid.UUID) -> list[Observation]:
        return list(
            (
                await self.s.execute(
                    select(Observation).where(Observation.source_event_id == event_id)
                )
            )
            .scalars()
            .all()
        )

    async def entity(self, entity_id: uuid.UUID) -> Entity | None:
        return await self.s.get(Entity, entity_id)

    async def actor(self, actor_id: uuid.UUID) -> Actor | None:
        return await self.s.get(Actor, actor_id)

    async def actors_in_scene(self, scene_id: uuid.UUID) -> list[Actor]:
        rows = (
            (
                await self.s.execute(
                    select(Actor)
                    .join(SceneParticipant, SceneParticipant.actor_id == Actor.id)
                    .where(
                        SceneParticipant.scene_id == scene_id,
                        SceneParticipant.left_event_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def identity_all(self, campaign_id: uuid.UUID) -> list[EntityIdentityKnowledge]:
        return list(
            (
                await self.s.execute(
                    select(EntityIdentityKnowledge).where(
                        EntityIdentityKnowledge.campaign_id == campaign_id
                    )
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

    async def item(self, item_id: uuid.UUID) -> Item | None:
        return await self.s.get(Item, item_id)
