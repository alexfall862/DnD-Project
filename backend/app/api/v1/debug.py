"""Omniscient debug endpoints (api-contracts.md §18–§20). Separate service/repository paths
from the normal API; refused unless DEBUG_MODE is on."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import DebugModeRequired, NotFound
from app.persistence.db import get_session
from app.persistence.models import (
    Actor,
    ActorController,
    Campaign,
    ContextSnapshot,
    Entity,
    Event,
    ModelRun,
    Scene,
    TurnMetrics,
)
from app.persistence.repositories.objective import ObjectiveWorldRepository
from app.services.perspective import PerspectiveService

router = APIRouter(prefix="/debug", tags=["debug"])


async def require_debug(request: Request) -> None:
    if not request.app.state.settings.debug_mode:
        raise DebugModeRequired("set DEBUG_MODE=true to use /debug endpoints")


def _belief(b) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "proposition": b.proposition,
        "type": b.belief_type,
        "confidence": float(b.confidence),
        "status": b.status,
        "source_type": b.source_type,
        "fact_id": str(b.fact_id) if b.fact_id else None,
        "claim_id": str(b.claim_id) if b.claim_id else None,
    }


@router.get("/campaigns/{campaign_id}/facts", dependencies=[Depends(require_debug)])
async def facts(
    campaign_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    repo = ObjectiveWorldRepository(session)
    return [
        {
            "id": str(f.id),
            "key": f.key,
            "subject_entity_id": str(f.subject_entity_id) if f.subject_entity_id else None,
            "predicate": f.predicate,
            "object_entity_id": str(f.object_entity_id) if f.object_entity_id else None,
            "object_value": f.object_value,
            "canon_status": f.canon_status,
            "truth_status": f.truth_status,
            "sensitivity": f.sensitivity,
        }
        for f in await repo.facts(campaign_id)
    ]


@router.get("/actors/{actor_id}/perspective", dependencies=[Depends(require_debug)])
async def actor_perspective(
    actor_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """The same view the actor's own context would be compiled from, for any actor."""
    svc = PerspectiveService(session)
    actor = await session.get(Actor, actor_id)
    if actor is None:
        raise NotFound("actor not found")
    ctx = await svc.context_candidates(actor_id)
    scene = ctx.get("scene")
    return {
        "actor_id": str(actor_id),
        "scene": scene.__dict__ | {"participants": [p.__dict__ for p in scene.participants]}
        if scene
        else None,
        "beliefs": [b.__dict__ | {"belief_id": str(b.belief_id)} for b in ctx.get("beliefs", [])],
        "heard_claims": [c.__dict__ for c in ctx.get("heard_claims", [])],
        "observations": ctx.get("observations", []),
        "known_entities": ctx.get("known_entities", {}),
        "inventory": [i.__dict__ for i in ctx.get("inventory", [])],
        "resources": ctx.get("resources", []),
    }


@router.get("/campaigns/{campaign_id}/perspectives/compare", dependencies=[Depends(require_debug)])
async def compare(
    campaign_id: uuid.UUID,
    actor_ids: str = Query(..., description="comma-separated actor ids"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Objective facts side by side with each actor's beliefs (api-contracts §19)."""
    repo = ObjectiveWorldRepository(session)
    ids = [uuid.UUID(x) for x in actor_ids.split(",") if x]
    out: dict[str, Any] = {"facts": await facts(campaign_id, session), "actors": {}}
    for aid in ids:
        actor = await session.get(Actor, aid)
        if actor is None:
            continue
        entity = await session.get(Entity, actor.entity_id)
        beliefs = [b for b in await repo.beliefs_all(campaign_id) if b.actor_id == aid]
        identity = [
            {"entity_id": str(r.entity_id), "known_name": r.known_name}
            for r in await repo.identity_all(campaign_id)
            if r.actor_id == aid and r.status == "active"
        ]
        out["actors"][str(aid)] = {
            "name": entity.canonical_name if entity else None,
            "beliefs": [_belief(b) for b in beliefs],
            "identity": identity,
        }
    return out


@router.get("/claims", dependencies=[Depends(require_debug)])
async def claims(
    event_id: uuid.UUID = Query(...), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Claims with their speaker-private flags and provenance (api-contracts §18)."""
    repo = ObjectiveWorldRepository(session)
    return [
        {
            "id": str(c.id),
            "speaker_actor_id": str(c.speaker_actor_id),
            "predicate": c.predicate,
            "subject_entity_id": str(c.subject_entity_id) if c.subject_entity_id else None,
            "object_entity_id": str(c.object_entity_id) if c.object_entity_id else None,
            "object_value": c.object_value,
            "stance": c.speaker_stance,
            "fidelity": c.fidelity,
            "deliberate_false": c.deliberate_false,
            "source_fact_id": str(c.source_fact_id) if c.source_fact_id else None,
            "source_belief_id": str(c.source_belief_id) if c.source_belief_id else None,
            "conveyance_source": c.conveyance_source,
        }
        for c in await repo.claims_for_event(event_id)
    ]


@router.get("/campaigns/{campaign_id}/events", dependencies=[Depends(require_debug)])
async def events(
    campaign_id: uuid.UUID, limit: int = 200, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(Event)
                .where(Event.campaign_id == campaign_id)
                .order_by(Event.sequence_number.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(e.id),
            "sequence": e.sequence_number,
            "type": e.event_type,
            "tick": e.game_tick,
            "payload": e.payload,
            "world_version_after": e.world_version_after,
        }
        for e in reversed(rows)
    ]


@router.post("/seed-demo", dependencies=[Depends(require_debug)])
async def seed_demo(
    request: Request,
    session: AsyncSession = Depends(get_session),
    name: str | None = None,
    fixture: str = "frostbridge",
) -> dict[str, Any]:
    """Create a demo campaign: the full Frostbridge fixture (default) or the small Red
    Lantern scene (`fixture=tavern`). Returns the symbolic-name → id map the harness needs."""
    engine_version = request.app.state.settings.engine_version
    if fixture == "tavern":
        from app.seeds.frostbridge_tavern import seed_tavern

        w = await seed_tavern(
            session, name=name or "frostbridge-tavern", engine_version=engine_version
        )
    elif fixture == "frostbridge":
        from app.seeds.frostbridge import seed_frostbridge

        w = await seed_frostbridge(
            session, name=name or "frostbridge", engine_version=engine_version
        )
    else:
        raise NotFound(f"unknown fixture {fixture!r}")
    await session.commit()
    return w.summary()


@router.get("/campaigns/{campaign_id}/actors", dependencies=[Depends(require_debug)])
async def actors(
    campaign_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Actor, Entity)
            .join(Entity, Entity.id == Actor.entity_id)
            .where(Entity.campaign_id == campaign_id)
        )
    ).all()
    out = []
    for a, e in rows:
        ctrl = (
            await session.execute(
                select(ActorController.controller_type).where(
                    ActorController.actor_id == a.id,
                    ActorController.valid_until_event_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        out.append(
            {
                "actor_id": str(a.id),
                "entity_id": str(e.id),
                "name": e.canonical_name,
                "controller": ctrl,
                "importance": a.importance_tier,
                "scene_id": str(a.current_scene_id) if a.current_scene_id else None,
            }
        )
    return sorted(out, key=lambda x: x["name"])


@router.get("/campaigns/{campaign_id}/metrics", dependencies=[Depends(require_debug)])
async def metrics(
    campaign_id: uuid.UUID, limit: int = 20, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(TurnMetrics)
                .where(TurnMetrics.campaign_id == campaign_id)
                .order_by(TurnMetrics.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "turn_id": str(t.turn_id),
            "wall_ms_total": t.wall_ms_total,
            "ms_to_first_output": t.ms_to_first_output,
            "ms_to_first_narration_token": t.ms_to_first_narration_token,
            "sync_model_calls": t.sync_model_calls,
            "background_model_calls": t.background_model_calls,
            "calls_by_role": t.calls_by_role,
            "prompt_tokens_total": t.prompt_tokens_total,
            "completion_tokens_total": t.completion_tokens_total,
            "degradation_steps": t.degradation_steps,
            "budget_breached": t.budget_breached,
        }
        for t in reversed(rows)
    ]


@router.get("/campaigns/{campaign_id}/model-runs", dependencies=[Depends(require_debug)])
async def model_runs(
    campaign_id: uuid.UUID,
    turn_id: uuid.UUID | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(ModelRun).where(ModelRun.campaign_id == campaign_id)
    if turn_id is not None:
        q = q.where(ModelRun.turn_id == turn_id)
    rows = (
        (await session.execute(q.order_by(ModelRun.started_at.desc()).limit(limit))).scalars().all()
    )
    return [
        {
            "model_run_id": str(r.id),
            "turn_id": str(r.turn_id) if r.turn_id else None,
            "role": r.role,
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "status": r.status,
            "model": r.model_requested,
            "latency_ms": r.latency_ms,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
        }
        for r in reversed(rows)
    ]


@router.get("/model-runs/{model_run_id}/context", dependencies=[Depends(require_debug)])
async def model_run_context(
    model_run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    run = await session.get(ModelRun, model_run_id)
    if run is None:
        raise NotFound("model run not found")
    snap = (
        await session.get(ContextSnapshot, run.context_snapshot_id)
        if run.context_snapshot_id
        else None
    )
    return {
        "model_run_id": str(run.id),
        "role": run.role,
        "status": run.status,
        "actor_id": str(run.actor_id) if run.actor_id else None,
        "prompt_id": run.prompt_id,
        "prompt_version": run.prompt_version,
        "rendered_context": snap.rendered_context if snap else None,
        "authorization_scope": snap.authorization_scope if snap else None,
        "raw_output": run.raw_output,
        "structured_output": run.structured_output,
        "validation": run.validation,
        "error": run.error,
    }


@router.post(
    "/campaigns/{campaign_id}/scenes/{scene_id}/end", dependencies=[Depends(require_debug)]
)
async def end_scene(
    campaign_id: uuid.UUID,
    scene_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Scene end = the main memory checkpoint (06c). Travel between locations (07) ends
    emptied scenes by itself; this endpoint ends one explicitly (rest, leaving town)."""
    from app.services.orchestrator import SessionOrchestrator
    from app.services.world import CampaignHandle

    c = await session.get(Campaign, campaign_id)
    scene = await session.get(Scene, scene_id)
    if c is None or c.active_timeline_id is None or scene is None:
        raise NotFound("campaign or scene not found")
    state = request.app.state
    orch = SessionOrchestrator(
        session,
        state.settings,
        engine=state.rules_engine,
        provider=state.provider,
        embedder=getattr(state, "embedder", None),
    )
    return await orch.end_scene(CampaignHandle(c.id, c.active_timeline_id), scene_id)
