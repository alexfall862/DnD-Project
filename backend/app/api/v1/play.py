"""POST /campaigns/{id}/play (api-contracts §9, §9a streaming, §10 clarification, §23
optimistic concurrency, §25 turn correlation)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import campaign_engine
from app.api.errors import ApiError, UnauthorizedPerspectiveError
from app.persistence.db import get_session
from app.services.orchestrator import (
    NeedsClarification,
    PlayRequest,
    SessionOrchestrator,
    StaleState,
)
from app.services.perspective import UnauthorizedPerspective
from app.services.world import CampaignHandle, WorldError

router = APIRouter(tags=["play"])
logger = logging.getLogger(__name__)


class ClientState(BaseModel):
    known_world_version: int | None = None
    known_scene_version: int | None = None


class PlayBody(BaseModel):
    actor_id: uuid.UUID
    text: str = Field(min_length=1, max_length=4000)
    channel: str = "auto"
    target_actor_ids: list[uuid.UUID] = Field(default_factory=list)
    client_state: ClientState = Field(default_factory=ClientState)
    clarification_id: uuid.UUID | None = None
    roll_request_id: uuid.UUID | None = None
    roll_decision: str | None = None  # "roll" | "reconsider"


class PlayOut(BaseModel):
    turn_id: uuid.UUID
    channel: str
    narration: str | None
    speakers: list[dict[str, Any]]
    visible_rolls: list[dict[str, Any]]
    mechanical_notices: list[str]
    state_changes: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    assertions: list[dict[str, Any]]
    time_advanced_seconds: int
    versions: dict[str, int | None]
    needs_player_input: bool
    metrics: dict[str, Any]
    ooc: str | None = None
    dev_notes: list[str] = Field(default_factory=list)
    roll_request: dict[str, Any] | None = None


async def _handle(
    campaign_id: uuid.UUID,
    h: CampaignHandle,
    body: PlayBody,
    request: Request,
    session: AsyncSession,
    emit=None,
) -> PlayOut:
    state = request.app.state
    orch = SessionOrchestrator(
        session,
        state.settings,
        engine=await campaign_engine(state, session, campaign_id),
        provider=state.provider,
        embedder=getattr(state, "embedder", None),
    )
    req = PlayRequest(
        body.actor_id,
        body.text,
        body.channel,
        body.target_actor_ids,
        body.client_state.known_world_version,
        body.client_state.known_scene_version,
        body.clarification_id,
        body.roll_request_id,
        body.roll_decision,
    )  # type: ignore[arg-type]
    try:
        res = await orch.process_player_input(h, req, emit=emit)
    except NeedsClarification as exc:
        await _record_failure(
            session,
            h,
            body,
            getattr(orch, "current_turn_id", None),
            {
                "clarification": {
                    "clarification_id": str(exc.clarification_id),
                    "question": exc.question,
                    "candidates": exc.candidates,
                    "original_input": exc.original_input,
                    "reason": exc.reason,
                }
            },
        )
        raise ApiError(
            exc.question,
            code="ACTION_NEEDS_CLARIFICATION",
            status_code=409,
            details={
                "clarification_id": str(exc.clarification_id),
                "question": exc.question,
                "candidates": exc.candidates,
                "original_input": exc.original_input,
                "reason": exc.reason,
            },
        ) from exc
    except StaleState as exc:
        raise ApiError(
            "client state is stale",
            code="STALE_STATE",
            status_code=409,
            details={"world_version": exc.world_version, "scene_version": exc.scene_version},
        ) from exc
    except UnauthorizedPerspective as exc:
        raise UnauthorizedPerspectiveError(str(exc)) from exc
    except WorldError as exc:
        await _record_failure(
            session,
            h,
            body,
            getattr(orch, "current_turn_id", None),
            {"error": {"code": "ACTION_INVALID", "message": str(exc)}},
        )
        raise ApiError(str(exc), code="ACTION_INVALID", status_code=400) from exc
    except Exception as exc:
        await _record_failure(
            session,
            h,
            body,
            getattr(orch, "current_turn_id", None),
            {"error": {"code": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}},
        )
        raise
    out = PlayOut(
        turn_id=res.turn_id,
        channel=res.channel,
        narration=res.narration,
        speakers=res.speakers,
        visible_rolls=res.visible_rolls,
        mechanical_notices=res.mechanical_notices,
        state_changes=res.state_changes,
        actions=res.actions,
        assertions=res.assertions,
        time_advanced_seconds=res.time_advanced_seconds,
        versions=res.versions,
        needs_player_input=res.needs_player_input,
        metrics=res.metrics,
        ooc=res.ooc,
        dev_notes=res.dev_notes,
        roll_request=res.roll_request,
    )
    await _record_feed(session, h, body, out)
    return out


async def _record_failure(
    session: AsyncSession,
    h: CampaignHandle,
    body: PlayBody,
    turn_id: uuid.UUID | None,
    result: dict[str, Any],
) -> None:
    """A turn that asked for clarification or failed still belongs in the player's history,
    with its turn id so dev view can open the trace (play session 2026-10-05)."""
    from app.persistence.models import PlayerTurn

    if turn_id is None:
        return
    try:
        session.add(
            PlayerTurn(
                campaign_id=h.campaign_id,
                timeline_id=h.timeline_id,
                actor_id=body.actor_id,
                turn_id=turn_id,
                input_text=body.text,
                channel=body.channel,
                to_names=[],
                result={"turn_id": str(turn_id), **result},
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001 - history is best-effort; never mask the turn's error
        await session.rollback()


async def _record_feed(
    session: AsyncSession, h: CampaignHandle, body: PlayBody, out: PlayOut
) -> None:
    """The player's feed (Milestone 10): the turn exactly as this player saw it, so any device
    can show the history. Presentation only, like turn metrics: no Event, no world state."""
    from app.persistence.models import PlayerTurn
    from app.services.perspective import PerspectiveService

    to_names: list[str] = []
    if body.target_actor_ids:
        view = await PerspectiveService(session).scene_view(body.actor_id)
        known = {p.actor_id: p.known_as for p in (view.participants if view else [])}
        to_names = [known.get(t, "someone") for t in body.target_actor_ids]
    session.add(
        PlayerTurn(
            campaign_id=h.campaign_id,
            timeline_id=h.timeline_id,
            actor_id=body.actor_id,
            turn_id=out.turn_id,
            input_text=body.text,
            channel=body.channel,
            to_names=to_names,
            result=json.loads(out.model_dump_json()),
        )
    )
    await session.commit()


async def _handle_for(campaign_id: uuid.UUID, session: AsyncSession) -> CampaignHandle:
    from app.persistence.models import Campaign

    c = await session.get(Campaign, campaign_id)
    if c is None or c.active_timeline_id is None:
        raise ApiError("campaign not found", code="NOT_FOUND", status_code=404)
    return CampaignHandle(c.id, c.active_timeline_id)


@router.post("/campaigns/{campaign_id}/play")
async def play(
    campaign_id: uuid.UUID,
    body: PlayBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    h = await _handle_for(campaign_id, session)
    if "text/event-stream" not in request.headers.get("accept", ""):
        return await _handle(campaign_id, h, body, request, session)

    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    def emit(name: str, payload: dict[str, Any]) -> None:
        queue.put_nowait((name, payload))

    async def run() -> None:
        try:
            out = await _handle(campaign_id, h, body, request, session, emit=emit)
            queue.put_nowait(("result", json.loads(out.model_dump_json())))
        except ApiError as exc:
            queue.put_nowait(
                ("error", {"code": exc.code, "message": exc.message, "details": exc.details})
            )
        except Exception as exc:  # noqa: BLE001 - the stream must end with an error event
            logger.exception("play turn failed")
            queue.put_nowait(
                ("error", {"code": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"})
            )
        finally:
            queue.put_nowait(None)

    async def gen() -> AsyncIterator[str]:
        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                name, payload = item
                yield f"event: {name}\ndata: {json.dumps(payload)}\n\n"
        finally:
            await task

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
