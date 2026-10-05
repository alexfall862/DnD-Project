"""Campaign metadata, settings, character sheet and party status for the player client
(api-contracts §5, §7, §13; human-visibility §2, §4).

Everything here is perspective-safe: the campaign view names only the human-controlled actors
(the player's own characters), the sheet is the focus actor's own, and the party is what the
focus actor perceives. Omniscient views stay under /debug."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_engine, campaign_engine
from app.api.errors import ApiError, NotFound, UnauthorizedPerspectiveError
from app.domain import events as ev
from app.persistence.db import get_session
from app.persistence.models import Actor, ActorController, Campaign, Entity
from app.persistence.models.campaign import WorldClock
from app.services.events import EventTransaction
from app.services.perspective import UnauthorizedPerspective
from app.services.sheets import SheetService

router = APIRouter(tags=["campaigns"])

DAY, HOUR = 86400, 3600

# the player-facing tunables (api-contracts §5; design-iteration §5); nothing else is writable
PLAYER_SETTINGS = {
    "narration_style",
    "spotlight",
    "spectator_mode",
    "latency_budget",
    "player_canon_policy",
    "dice_mode",  # manual (click to roll) | auto
}


class CampaignSummary(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    campaign_mode: str
    ruleset: str
    updated_at: datetime


class FocusActor(BaseModel):
    actor_id: uuid.UUID
    name: str


class WorldTime(BaseModel):
    tick: int
    day: int
    hour: int
    minute: int
    label: str


class CampaignDetail(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    ruleset: str
    world_version: int
    world_time: WorldTime | None
    settings: dict[str, Any]
    debug_mode: bool
    focus_actors: list[FocusActor]


class SettingsPatch(BaseModel):
    changes: dict[str, Any] = Field(min_length=1)


class SheetEntryOut(BaseModel):
    key: str
    name: str
    value: int
    description: str = ""


class ResourceOut(BaseModel):
    key: str
    name: str
    current: int
    max: int
    tracked_as: str = "pool"


class ConditionOut(BaseModel):
    key: str
    name: str
    intensity: int


class SheetOut(BaseModel):
    actor_id: uuid.UUID
    name: str
    attributes: list[SheetEntryOut]
    skills: list[SheetEntryOut]
    traits: list[SheetEntryOut]
    resources: list[ResourceOut]
    conditions: list[ConditionOut]


class PartyMemberOut(BaseModel):
    actor_id: uuid.UUID
    known_as: str
    controller: str
    is_focus: bool
    with_you: bool
    wound_state: str | None = None
    visible_conditions: list[str] = Field(default_factory=list)


def world_time(tick: int) -> WorldTime:
    day, rest = divmod(tick, DAY)
    hour, rest = divmod(rest, HOUR)
    minute = rest // 60
    return WorldTime(
        tick=tick,
        day=day + 1,
        hour=hour,
        minute=minute,
        label=f"Day {day + 1}, {hour:02d}:{minute:02d}",
    )


async def _campaign(session: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
    c = await session.get(Campaign, campaign_id)
    if c is None:
        raise NotFound("campaign not found")
    return c


@router.get("/campaigns", response_model=list[CampaignSummary])
async def list_campaigns(session: AsyncSession = Depends(get_session)) -> list[CampaignSummary]:
    rows = (
        (await session.execute(select(Campaign).order_by(Campaign.updated_at.desc())))
        .scalars()
        .all()
    )
    return [
        CampaignSummary(
            id=c.id,
            name=c.name,
            status=c.status,
            campaign_mode=c.campaign_mode,
            ruleset=f"{c.ruleset_key} {c.ruleset_version}",
            updated_at=c.updated_at,
        )
        for c in rows
    ]


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(
    campaign_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> CampaignDetail:
    c = await _campaign(session, campaign_id)
    clock = await session.get(WorldClock, c.active_timeline_id) if c.active_timeline_id else None
    humans = (
        await session.execute(
            select(Actor.id, Entity.canonical_name)
            .join(Entity, Entity.id == Actor.entity_id)
            .join(ActorController, ActorController.actor_id == Actor.id)
            .where(
                Entity.campaign_id == campaign_id,
                ActorController.controller_type == "human",
                ActorController.valid_until_event_id.is_(None),
            )
        )
    ).all()
    return CampaignDetail(
        id=c.id,
        name=c.name,
        description=c.description,
        status=c.status,
        ruleset=f"{c.ruleset_key} {c.ruleset_version}",
        world_version=c.world_version,
        world_time=world_time(clock.current_tick) if clock else None,
        settings={k: v for k, v in (c.settings or {}).items() if k in PLAYER_SETTINGS},
        debug_mode=bool(request.app.state.settings.debug_mode),
        focus_actors=[FocusActor(actor_id=a, name=n) for a, n in humans],
    )


@router.patch("/campaigns/{campaign_id}/settings", response_model=CampaignDetail)
async def patch_settings(
    campaign_id: uuid.UUID,
    body: SettingsPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CampaignDetail:
    """Change player-facing tunables; recorded as a `settings.changed` event."""
    c = await _campaign(session, campaign_id)
    unknown = sorted(set(body.changes) - PLAYER_SETTINGS)
    if unknown:
        raise ApiError(
            f"not a player setting: {', '.join(unknown)}",
            code="VALIDATION_ERROR",
            status_code=422,
            details={"allowed": sorted(PLAYER_SETTINGS)},
        )
    if c.active_timeline_id is None:
        raise ApiError("campaign has no timeline", code="CAMPAIGN_NOT_PLAYABLE", status_code=409)
    current = dict(c.settings or {})
    previous = {k: current.get(k) for k in body.changes}
    async with EventTransaction(session, c.id, c.active_timeline_id) as tx:
        await tx.emit(ev.SettingsChanged(changes=body.changes, previous=previous))
        c.settings = {**current, **body.changes}
    await session.commit()
    return await get_campaign(campaign_id, request, session)


@router.get("/characters/{actor_id}/sheet", response_model=SheetOut)
async def sheet(
    actor_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> SheetOut:
    engine = await actor_engine(request.app.state, session, actor_id)
    try:
        sh = await SheetService(session, engine).sheet(actor_id)
    except UnauthorizedPerspective as exc:
        raise UnauthorizedPerspectiveError(str(exc)) from exc
    return SheetOut.model_validate(sh, from_attributes=True)


class HereZoneOut(BaseModel):
    key: str
    name: str
    features: list[str]
    people: list[str]
    you_are_here: bool
    adjacent: bool


class HereExitOut(BaseModel):
    location_id: uuid.UUID
    known_as: str
    travel_minutes: int
    blocked_by: str | None = None


class HereOut(BaseModel):
    actor_id: uuid.UUID
    location: str
    scene_type: str
    zone: str | None
    zones: list[HereZoneOut]
    exits: list[HereExitOut]
    situations: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/characters/{actor_id}/here", response_model=HereOut)
async def here(actor_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> HereOut:
    """Where the focus character is, as they perceive it: the place, its spots and who is in
    each, the ways out (and whether something blocks them), and the situations they can see
    (play session 2: "a report of where we are within the scene")."""
    from app.services.here import HereService

    try:
        v = await HereService(session).view(actor_id)
    except UnauthorizedPerspective as exc:
        raise UnauthorizedPerspectiveError(str(exc)) from exc
    if v is None:
        raise NotFound("not in a scene")
    return HereOut.model_validate(v, from_attributes=True)


class FeedInput(BaseModel):
    text: str
    channel: str
    to: list[str] = Field(default_factory=list)


class FeedEntry(BaseModel):
    turn_id: uuid.UUID
    created_at: datetime
    input: FeedInput
    result: dict[str, Any]


@router.get("/characters/{actor_id}/feed", response_model=list[FeedEntry])
async def feed(
    actor_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[FeedEntry]:
    """The focus actor's own play history, oldest first (the last `limit` turns): each turn as
    the API returned it to this player. Another actor's id is refused."""
    from app.persistence.models import PlayerTurn
    from app.services.perspective import PerspectiveService

    try:
        await PerspectiveService(session).require_focus_actor(actor_id)
    except UnauthorizedPerspective as exc:
        raise UnauthorizedPerspectiveError(str(exc)) from exc
    rows = (
        (
            await session.execute(
                select(PlayerTurn)
                .where(PlayerTurn.actor_id == actor_id)
                .order_by(PlayerTurn.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        FeedEntry(
            turn_id=r.turn_id,
            created_at=r.created_at,
            input=FeedInput(text=r.input_text, channel=r.channel, to=list(r.to_names or [])),
            result=r.result,
        )
        for r in reversed(rows)
    ]


@router.get("/campaigns/{campaign_id}/party", response_model=list[PartyMemberOut])
async def party(
    campaign_id: uuid.UUID,
    request: Request,
    actor_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[PartyMemberOut]:
    await _campaign(session, campaign_id)
    in_campaign = (
        await session.execute(
            select(Actor.id)
            .join(Entity, Entity.id == Actor.entity_id)
            .where(Actor.id == actor_id, Entity.campaign_id == campaign_id)
        )
    ).first()
    if not in_campaign:
        raise NotFound("actor not in this campaign")
    engine = await campaign_engine(request.app.state, session, campaign_id)
    try:
        members = await SheetService(session, engine).party(actor_id)
    except UnauthorizedPerspective as exc:
        raise UnauthorizedPerspectiveError(str(exc)) from exc
    return [PartyMemberOut.model_validate(m, from_attributes=True) for m in members]
