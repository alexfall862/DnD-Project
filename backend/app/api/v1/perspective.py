"""Perspective-safe normal endpoints (api-contracts.md §7 inventory, §8 scene, §9b focus actor).

Every response is evaluated against the human-controlled focus actor named by `actor_id`.
Knowing an AI actor's id, an entity id or an item id grants nothing (leakage §16)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFound, UnauthorizedPerspectiveError
from app.persistence.db import get_session
from app.services.perspective import PerspectiveService, UnauthorizedPerspective

router = APIRouter(tags=["perspective"])


class ParticipantOut(BaseModel):
    entity_id: uuid.UUID
    known_as: str
    is_self: bool
    visible_conditions: list[str]
    zone: str | None = None
    actor_id: uuid.UUID | None = None


class SceneOut(BaseModel):
    scene_id: uuid.UUID
    scene_type: str
    location_known_as: str | None
    world_tick: int
    your_zone: str | None
    participants: list[ParticipantOut]


class ItemOut(BaseModel):
    item_id: uuid.UUID
    name: str | None
    template_key: str | None
    equipped: bool
    properties: dict


class BeliefOut(BaseModel):
    proposition: dict
    belief_type: str
    confidence: float
    status: str
    source_type: str
    source_known_as: str | None = None
    subject_known_as: str | None = None  # the actor's own name for the subject, if any
    object_known_as: str | None = None


async def _focus(svc: PerspectiveService, actor_id: uuid.UUID) -> None:
    try:
        await svc.require_focus_actor(actor_id)
    except UnauthorizedPerspective as exc:
        raise UnauthorizedPerspectiveError(str(exc)) from exc


@router.get("/campaigns/{campaign_id}/scene", response_model=SceneOut)
async def current_scene(
    campaign_id: uuid.UUID,
    actor_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> SceneOut:
    svc = PerspectiveService(session)
    await _focus(svc, actor_id)
    view = await svc.scene_view(actor_id)
    if view is None:
        raise NotFound("actor is not in an active scene")
    return SceneOut(
        scene_id=view.scene_id,
        scene_type=view.scene_type,
        location_known_as=view.location_known_as,
        world_tick=view.world_tick,
        your_zone=view.space_zone,
        participants=[ParticipantOut(**p.__dict__) for p in view.participants],
    )


@router.get("/characters/{actor_id}/inventory", response_model=list[ItemOut])
async def inventory(
    actor_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[ItemOut]:
    svc = PerspectiveService(session)
    await _focus(svc, actor_id)
    return [
        ItemOut(
            item_id=i.item_id,
            name=i.name,
            template_key=i.template_key,
            equipped=i.equipped,
            properties=i.public_properties,
        )
        for i in await svc.inventory(actor_id)
    ]


@router.get("/characters/{actor_id}/beliefs", response_model=list[BeliefOut])
async def beliefs(
    actor_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[BeliefOut]:
    """The focus actor's own beliefs (the encyclopedia/journal projections build on this)."""
    svc = PerspectiveService(session)
    await _focus(svc, actor_id)
    names = await svc.known_entities(actor_id)

    def known(raw) -> str | None:
        try:
            return names.get(uuid.UUID(str(raw))) if raw else None
        except ValueError:
            return str(raw)  # free-text subject

    return [
        BeliefOut(
            proposition=b.proposition,
            belief_type=b.belief_type,
            confidence=b.confidence,
            status=b.status,
            source_type=b.source_type,
            source_known_as=b.source_known_as,
            subject_known_as=known(b.proposition.get("subject_entity_id")),
            object_known_as=known(b.proposition.get("object_entity_id")),
        )
        for b in await svc.beliefs(actor_id)
    ]
