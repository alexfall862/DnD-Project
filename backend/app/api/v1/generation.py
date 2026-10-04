"""Campaign brief and generation (api-contracts §6).

POST /campaigns                                   create a draft campaign
PUT  /campaigns/{id}/brief                        store the CampaignBrief (or surprise)
POST /campaigns/{id}/generation-runs              start a run (202; `inline=true` runs now)
GET  /generation-runs/{run_id}                    stage statuses
POST /generation-runs/{run_id}/stages/{stage}/regenerate   pre-play reroll
GET  /campaigns/{id}/generation-preview           preview (secrets only under debug)
POST /campaigns/{id}/start                        build, check, activate
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError, DebugModeRequired, NotFound
from app.persistence.db import get_session
from app.persistence.models import Campaign
from app.services.jobs import JobQueue
from app.services.world import WorldError, WorldService
from app.worldgen.brief import CampaignBrief, surprise
from app.worldgen.service import GenerationService

router = APIRouter(tags=["generation"])


class CreateCampaign(BaseModel):
    name: str = "New campaign"
    creation_mode: str = "guided"


class RegenerateBody(BaseModel):
    guidance: str | None = None


class ImportBody(BaseModel):
    format: str = "text"  # text | markdown | structured
    content: str | dict[str, Any]


class BriefBody(BaseModel):
    brief: dict[str, Any] | None = None
    surprise_seed: int | None = None


def _svc(request: Request, session: AsyncSession) -> GenerationService:
    st = request.app.state
    return GenerationService(
        session,
        st.settings,
        engine=st.rules_engine,
        provider=st.provider,
        embedder=getattr(st, "embedder", None),
    )


def _world_error(exc: WorldError) -> ApiError:
    return ApiError(str(exc), code="GENERATION_ERROR", status_code=409)


@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CreateCampaign, request: Request, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    h = await WorldService(session).create_campaign(
        body.name,
        ruleset_key="core_adventure",
        ruleset_version="0.1.0",
        engine_version=request.app.state.settings.engine_version,
        creation_mode=body.creation_mode,
    )
    await session.commit()
    return {"campaign_id": str(h.campaign_id), "timeline_id": str(h.timeline_id), "status": "draft"}


@router.put("/campaigns/{campaign_id}/brief")
async def put_brief(
    campaign_id: uuid.UUID, body: BriefBody, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    c = await session.get(Campaign, campaign_id)
    if c is None:
        raise NotFound("campaign not found")
    if c.status not in ("draft", "generating"):
        raise ApiError("the brief is pre-play only", code="CAMPAIGN_ACTIVE", status_code=409)
    if body.surprise_seed is not None:
        brief = surprise(body.surprise_seed, **(body.brief or {}))
    else:
        brief = CampaignBrief.model_validate(body.brief or {})
    c.generation_brief = brief.model_dump()
    await session.commit()
    return {"campaign_id": str(campaign_id), "brief": c.generation_brief}


class GuidedBody(BaseModel):
    message: str


def _guided(request: Request, session: AsyncSession):
    from app.worldgen.guided import GuidedCreationService

    st = request.app.state
    return GuidedCreationService(
        session,
        st.settings,
        engine=st.rules_engine,
        provider=st.provider,
        embedder=getattr(st, "embedder", None),
    )


@router.get("/campaigns/{campaign_id}/brief/guided")
async def guided_state(
    campaign_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Guided creation (campaign-generation §2): the current question and brief."""
    try:
        brief, state = await _guided(request, session).state(campaign_id)
    except WorldError as exc:
        raise _world_error(exc) from exc
    return {
        "question": state.question or None,
        "done": state.done,
        "turns": len(state.turns),
        "brief": brief.model_dump(),
    }


@router.post("/campaigns/{campaign_id}/brief/guided")
async def guided_answer(
    campaign_id: uuid.UUID,
    body: GuidedBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await _guided(request, session).answer(campaign_id, body.message)
    except WorldError as exc:
        raise _world_error(exc) from exc


@router.post("/campaigns/{campaign_id}/imports")
async def import_world(
    campaign_id: uuid.UUID,
    body: ImportBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Custom / imported world (campaign-generation §2): the content becomes established canon
    that the next generation run extends."""
    from app.worldgen.importer import ImportService

    st = request.app.state
    svc = ImportService(
        session,
        st.settings,
        engine=st.rules_engine,
        provider=st.provider,
        embedder=getattr(st, "embedder", None),
    )
    fmt = "structured" if body.format in ("structured", "json") else "text"
    try:
        result = await svc.import_source(campaign_id, body.content, fmt=fmt)
    except WorldError as exc:
        raise _world_error(exc) from exc
    return result.to_dict()


@router.post("/campaigns/{campaign_id}/generation-runs")
async def start_run(
    campaign_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    inline: bool = False,
) -> JSONResponse:
    c = await session.get(Campaign, campaign_id)
    if c is None:
        raise NotFound("campaign not found")
    svc = _svc(request, session)
    try:
        run = await svc.create_run(
            campaign_id, CampaignBrief.model_validate(c.generation_brief or {})
        )
        if inline:
            run = await svc.run(run.id)
        else:
            await JobQueue(session).enqueue(
                "campaign.generate",
                campaign_id=campaign_id,
                timeline_id=c.active_timeline_id,
                payload={"run_id": str(run.id)},
            )
            await session.commit()
    except WorldError as exc:
        raise _world_error(exc) from exc
    return JSONResponse(
        status_code=202, content={"run_id": str(run.id), "status": run.status, "inline": inline}
    )


@router.get("/generation-runs/{run_id}")
async def get_run(
    run_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    svc = _svc(request, session)
    try:
        run = await svc._run(run_id)
    except WorldError as exc:
        raise NotFound(str(exc)) from exc
    return {
        "run_id": str(run.id),
        "campaign_id": str(run.campaign_id),
        "status": run.status,
        "error": run.error,
        "stages": [
            {
                "stage": s.stage_key,
                "status": s.status,
                "attempts": s.attempts,
                "errors": s.errors,
                "model_run_id": str(s.model_run_id) if s.model_run_id else None,
            }
            for s in await svc.stages(run_id)
        ],
    }


@router.post("/generation-runs/{run_id}/stages/{stage}/regenerate")
async def regenerate(
    run_id: uuid.UUID,
    stage: str,
    body: RegenerateBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    svc = _svc(request, session)
    try:
        invalidated = await svc.regenerate(run_id, stage, guidance=body.guidance)
    except WorldError as exc:
        raise _world_error(exc) from exc
    return {"run_id": str(run_id), "stage": stage, "invalidated": invalidated}


@router.get("/campaigns/{campaign_id}/generation-preview")
async def preview(
    campaign_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    include_secrets: bool = False,
) -> dict[str, Any]:
    if include_secrets and not request.app.state.settings.debug_mode:
        raise DebugModeRequired("secrets in the preview need DEBUG_MODE=true")
    try:
        return await _svc(request, session).preview(campaign_id, include_secrets=include_secrets)
    except WorldError as exc:
        raise NotFound(str(exc)) from exc


@router.post("/campaigns/{campaign_id}/start")
async def start_campaign(
    campaign_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        result = await _svc(request, session).start(campaign_id)
    except WorldError as exc:
        raise _world_error(exc) from exc
    return result.to_dict()
