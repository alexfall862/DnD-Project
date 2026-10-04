"""GET /characters/{actor_id}/journal and /encyclopedia (api-contracts §14–§15;
human-visibility §7): perspective projections of one human-controlled actor."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_engine
from app.api.errors import NotFound, UnauthorizedPerspectiveError
from app.persistence.db import get_session
from app.services.memory_processing import MemoryProcessingService
from app.services.perspective import PerspectiveService, UnauthorizedPerspective
from app.services.world import CampaignHandle

router = APIRouter(tags=["journal"])


class JournalEntryOut(BaseModel):
    id: uuid.UUID
    entry_type: str
    title: str
    body: str
    game_tick: int
    from_sequence: int | None
    to_sequence: int | None


class EncyclopediaOut(BaseModel):
    entity_id: uuid.UUID
    category: str
    display_name: str
    summary: str
    knowledge: dict[str, Any]


async def _focus(session: AsyncSession, actor_id: uuid.UUID) -> CampaignHandle:
    svc = PerspectiveService(session)
    try:
        await svc.require_focus_actor(actor_id)
    except UnauthorizedPerspective as exc:
        raise UnauthorizedPerspectiveError(str(exc)) from exc
    actor = await svc.repo.actor(actor_id)
    if actor is None:
        raise NotFound("actor not found")
    from app.persistence.models import Campaign, Entity

    ent = await session.get(Entity, actor.entity_id)
    campaign = await session.get(Campaign, ent.campaign_id) if ent else None
    if campaign is None or campaign.active_timeline_id is None:
        raise NotFound("campaign not found")
    return CampaignHandle(campaign.id, campaign.active_timeline_id)


def _svc(request: Request, session: AsyncSession, engine=None) -> MemoryProcessingService:
    from app.ai.context import ContextCompiler
    from app.ai.routing import ModelRouter
    from app.ai.runner import ModelRunner
    from app.services.memory import MemoryService

    state = request.app.state
    memory = MemoryService(session, getattr(state, "embedder", None))
    return MemoryProcessingService(
        session,
        compiler=ContextCompiler(session, memory=memory, engine=engine or state.rules_engine),
        runner=ModelRunner(session, ModelRouter(state.settings, state.provider)),
        memory=memory,
    )


@router.get("/characters/{actor_id}/journal", response_model=list[JournalEntryOut])
async def journal(
    actor_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
):
    await _focus(session, actor_id)
    rows = await _svc(
        request, session, await actor_engine(request.app.state, session, actor_id)
    ).journal(actor_id)
    return [
        JournalEntryOut(
            id=r.id,
            entry_type=r.entry_type,
            title=r.title,
            body=r.body,
            game_tick=r.game_tick,
            from_sequence=r.from_sequence,
            to_sequence=r.to_sequence,
        )
        for r in rows
    ]


@router.get("/characters/{actor_id}/encyclopedia", response_model=list[EncyclopediaOut])
async def encyclopedia(
    actor_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    category: str | None = Query(default=None),
):
    h = await _focus(session, actor_id)
    rows = await _svc(
        request, session, await actor_engine(request.app.state, session, actor_id)
    ).rebuild_encyclopedia(h, actor_id)
    await session.commit()
    return [
        EncyclopediaOut(
            entity_id=r.entity_id,
            category=r.category,
            display_name=r.display_name,
            summary=r.summary,
            knowledge=r.knowledge,
        )
        for r in rows
        if category is None or r.category == category
    ]


@router.get("/characters/{actor_id}/encyclopedia/{entity_id}", response_model=EncyclopediaOut)
async def encyclopedia_entry(
    actor_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    h = await _focus(session, actor_id)
    rows = await _svc(
        request, session, await actor_engine(request.app.state, session, actor_id)
    ).rebuild_encyclopedia(h, actor_id)
    await session.commit()
    for r in rows:
        if r.entity_id == entity_id:
            return EncyclopediaOut(
                entity_id=r.entity_id,
                category=r.category,
                display_name=r.display_name,
                summary=r.summary,
                knowledge=r.knowledge,
            )
    raise NotFound("this character knows nothing of that entity")  # knowing an id grants nothing
