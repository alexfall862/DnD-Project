"""Shared request helpers."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.core import RulesEngine
from app.persistence.models import Actor, Campaign, Entity


async def campaign_engine(state, session: AsyncSession, campaign_id: uuid.UUID) -> RulesEngine:
    """The campaign's rules: the app's base engine unless the campaign enabled genre modules
    (campaign-generation §4), in which case the base ruleset plus those modules."""
    c = await session.get(Campaign, campaign_id)
    if c is None or not (c.settings or {}).get("genre_modules"):
        return state.rules_engine
    return RulesEngine.for_campaign(c.ruleset_key, c.settings)


async def actor_engine(state, session: AsyncSession, actor_id: uuid.UUID) -> RulesEngine:
    cid = (
        await session.execute(
            select(Entity.campaign_id)
            .join(Actor, Actor.entity_id == Entity.id)
            .where(Actor.id == actor_id)
        )
    ).scalar_one_or_none()
    if cid is None:
        return state.rules_engine
    return await campaign_engine(state, session, cid)
