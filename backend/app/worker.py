"""Background worker (orchestration §37; implementation-plan §16): claims `background_jobs` one
at a time and runs the optional work the player never waits for — memory embeddings, deferred
memory processing, journal updates, world-simulation ticks. Each job runs in its own session;
a failing job is recorded on the job row and retried with backoff. Nothing a job does can roll
back a turn, and no job writes authoritative state except through the same services the
orchestrator uses (every mutation still commits with its Event).

    uv run python -m app.worker            # loop until interrupted
    uv run python -m app.worker --once     # drain what is runnable now, then exit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import sys
import traceback
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.context import ContextCompiler
from app.ai.embeddings import Embedder
from app.ai.providers import A9Provider, FakeModelProvider, ModelProvider
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import Settings, get_settings
from app.engine.core import RulesEngine
from app.persistence.db import make_engine, make_session_factory
from app.persistence.models import Campaign, Scene
from app.persistence.models.jobs import BackgroundJob
from app.services.jobs import JobQueue
from app.services.memory import MemoryService
from app.services.memory_processing import MemoryProcessingService
from app.services.turns import Turn, budget_from_settings
from app.services.world import CampaignHandle

log = logging.getLogger("ttrpg.worker")


class WorkerContext:
    """Everything a job handler may use, built per job on a fresh session."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        engine: RulesEngine,
        provider: ModelProvider,
        embedder: Embedder | None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.engine = engine
        self.provider = provider
        self.embedder = embedder
        self.memory = MemoryService(session, embedder)
        self.compiler = ContextCompiler(session, memory=self.memory, engine=engine)
        self.runner = ModelRunner(session, ModelRouter(settings, provider))
        self.memory_processing = MemoryProcessingService(
            session, compiler=self.compiler, runner=self.runner, memory=self.memory
        )

    async def handle(self, h: CampaignHandle) -> CampaignHandle:
        return h

    async def turn(self, h: CampaignHandle) -> Turn:
        campaign = await self.session.get(Campaign, h.campaign_id)
        return Turn(
            h, budget=budget_from_settings(self.settings, campaign.settings if campaign else None)
        )


Handler = Callable[[WorkerContext, BackgroundJob], Awaitable[dict[str, Any]]]


def _handle_of(job: BackgroundJob) -> CampaignHandle:
    if job.campaign_id is None or job.timeline_id is None:
        raise ValueError("job has no campaign/timeline")
    return CampaignHandle(job.campaign_id, job.timeline_id)


async def memory_embedding(ctx: WorkerContext, job: BackgroundJob) -> dict[str, Any]:
    n = await ctx.memory.embed_pending(job.subject_id, batch=int(job.payload.get("batch", 64)))
    return {"embedded": n}


async def memory_process(ctx: WorkerContext, job: BackgroundJob) -> dict[str, Any]:
    h = _handle_of(job)
    if job.subject_id is None:
        raise ValueError("memory.process needs subject_id = actor id")
    scene = (
        await ctx.session.get(Scene, uuid.UUID(str(job.payload["scene_id"])))
        if job.payload.get("scene_id")
        else None
    )
    turn = await ctx.turn(h)
    r = await ctx.memory_processing.checkpoint(
        h, job.subject_id, reason=job.payload.get("reason", "background"), turn=turn, scene=scene
    )
    await turn.finish(ctx.session)
    await ctx.session.commit()
    return {k: v for k, v in r.__dict__.items() if not isinstance(v, uuid.UUID)}


async def journal_update(ctx: WorkerContext, job: BackgroundJob) -> dict[str, Any]:
    h = _handle_of(job)
    if job.subject_id is None:
        raise ValueError("journal.update needs subject_id = actor id")
    scene = (
        await ctx.session.get(Scene, uuid.UUID(str(job.payload["scene_id"])))
        if job.payload.get("scene_id")
        else None
    )
    turn = await ctx.turn(h)
    entry = await ctx.memory_processing.write_journal(
        h,
        job.subject_id,
        turn=turn,
        scene=scene,
        entry_type=job.payload.get("entry_type", "session"),
    )
    await turn.finish(ctx.session)
    await ctx.session.commit()
    return {"journal_entry_id": str(entry.id) if entry else None}


async def simulation_advance(ctx: WorkerContext, job: BackgroundJob) -> dict[str, Any]:
    from app.services.simulation import SimulationService

    h = _handle_of(job)
    sim = SimulationService(
        ctx.session,
        ctx.settings,
        engine=ctx.engine,
        compiler=ctx.compiler,
        runner=ctx.runner,
    )
    turn = await ctx.turn(h)
    run = await sim.tick(
        h,
        from_tick=int(job.payload["from_tick"]),
        to_tick=int(job.payload["to_tick"]),
        turn=turn,
    )
    await turn.finish(ctx.session)
    await ctx.session.commit()
    return run.to_dict()


async def world_materialize(ctx: WorkerContext, job: BackgroundJob) -> dict[str, Any]:
    """Progressive materialization (campaign-generation §27) of one outline/latent place."""
    from app.worldgen.materialize import MaterializeService

    h = _handle_of(job)
    if job.subject_id is None:
        raise ValueError("world.materialize needs subject_id = location id")
    svc = MaterializeService(
        ctx.session, ctx.settings, engine=ctx.engine, provider=ctx.provider, embedder=ctx.embedder
    )
    out = await svc.materialize_location(h, job.subject_id, need=job.payload.get("need", ""))
    await ctx.session.commit()
    return out


async def campaign_generate(ctx: WorkerContext, job: BackgroundJob) -> dict[str, Any]:
    from app.worldgen.service import GenerationService

    svc = GenerationService(
        ctx.session, ctx.settings, engine=ctx.engine, provider=ctx.provider, embedder=ctx.embedder
    )
    run = await svc.run(uuid.UUID(str(job.payload["run_id"])))
    return {"run_id": str(run.id), "status": run.status, "error": run.error}


HANDLERS: dict[str, Handler] = {
    "memory.embedding": memory_embedding,
    "memory.process": memory_process,
    "journal.update": journal_update,
    "simulation.advance": simulation_advance,
    "world.materialize": world_materialize,
    "campaign.generate": campaign_generate,
}


async def run_once(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    engine: RulesEngine,
    provider: ModelProvider,
    embedder: Embedder | None,
    worker_id: str,
    job_types: tuple[str, ...] | None = None,
    campaign_id: uuid.UUID | None = None,
) -> BackgroundJob | None:
    """Claim and run at most one job. Returns the job (with its final status) or None when
    nothing was runnable. The claim and the work use separate sessions so a crashed handler
    can never leave the claim transaction open."""
    async with session_factory() as queue_session:
        queue = JobQueue(queue_session)
        job = await queue.claim(worker_id, job_types=job_types, campaign_id=campaign_id)
        if job is None:
            return None
        handler = HANDLERS.get(job.job_type)
        try:
            if handler is None:
                raise ValueError(f"no handler for job type {job.job_type!r}")
            async with session_factory() as work_session:
                job_engine = engine
                if job.campaign_id is not None:
                    c = await work_session.get(Campaign, job.campaign_id)
                    if c is not None and (c.settings or {}).get("genre_modules"):
                        job_engine = RulesEngine.for_campaign(c.ruleset_key, c.settings)
                ctx = WorkerContext(
                    work_session, settings, engine=job_engine, provider=provider, embedder=embedder
                )
                try:
                    result = await handler(ctx, job)
                except Exception:
                    await work_session.rollback()  # optional work never dirties the world
                    raise
            await queue.complete(job, result)
        except Exception as exc:  # noqa: BLE001 - recorded on the job, never propagated
            log.warning("job %s (%s) failed: %s", job.id, job.job_type, exc)
            await queue.fail(job, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")
        return job


async def run_forever(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    engine: RulesEngine,
    provider: ModelProvider,
    embedder: Embedder | None,
    worker_id: str,
    poll_seconds: float = 2.0,
    stop: asyncio.Event | None = None,
) -> None:
    while stop is None or not stop.is_set():
        job = await run_once(
            session_factory,
            settings,
            engine=engine,
            provider=provider,
            embedder=embedder,
            worker_id=worker_id,
        )
        if job is None:
            await asyncio.sleep(poll_seconds)


def build_provider(settings: Settings) -> tuple[ModelProvider, Embedder | None]:
    if settings.a9_token:
        from app.ai.embeddings import A9Embedder

        return (
            A9Provider(
                settings.a9_base_url,
                settings.a9_token,
                client_name=settings.a9_client_name,
                max_concurrent=settings.max_concurrent_inference,
            ),
            A9Embedder(
                settings.a9_base_url,
                settings.a9_token,
                client_name=settings.a9_client_name,
                model=settings.model_profile_embedding,
                rerank_model=settings.model_profile_rerank,
                dimensions=settings.embedding_dimensions,
            ),
        )
    return FakeModelProvider(), None


async def _main(once: bool) -> int:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    engine = make_engine(settings.database_url)
    rules = RulesEngine.load(settings.default_ruleset)
    provider, embedder = build_provider(settings)
    worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            recovered = await JobQueue(s).recover_stale()
            if recovered:
                log.info("re-queued %d stale job(s)", recovered)
        if once:
            n = 0
            while True:
                job = await run_once(
                    factory,
                    settings,
                    engine=rules,
                    provider=provider,
                    embedder=embedder,
                    worker_id=worker_id,
                )
                if job is None:
                    break
                n += 1
                log.info("job %s %s -> %s", job.id, job.job_type, job.status)
            print(f"ran {n} job(s)")
        else:
            log.info("worker %s polling", worker_id)
            await run_forever(
                factory,
                settings,
                engine=rules,
                provider=provider,
                embedder=embedder,
                worker_id=worker_id,
            )
    finally:
        for closable in (provider, embedder):
            if hasattr(closable, "aclose"):
                await closable.aclose()
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI TTRPG background worker")
    ap.add_argument("--once", action="store_true", help="drain runnable jobs and exit")
    args = ap.parse_args(argv)
    return asyncio.run(_main(args.once))


if __name__ == "__main__":
    sys.exit(main())
