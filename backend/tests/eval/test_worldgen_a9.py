"""Opt-in (`--eval`): the real A9 model (GLM-4.5-Air) generates a whole campaign through the
18 World Author stages, answers two guided-creation turns and fills the §23 artifact slot.
Nothing is asserted about content quality; the test records, per stage, whether the output
was accepted, how many attempts it took, latency, tokens and the validation errors, and
writes the record to WORLDGEN_A9_REPORT (default: the system temp dir) as JSON.

Resumable: WORLDGEN_A9_RESUME=<run id> (printed in the report as `run_id`) skips guided
creation and the artifact and continues that run from its first unfinished stage; itemized
stages continue from their first unfinished item."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import A9Provider
from app.config import get_settings
from app.engine.core import RulesEngine
from app.persistence.models import ModelRun
from app.persistence.models.generation import GenerationRun
from app.services.world import WorldError, WorldService
from app.worldgen.artifact import generate_artifact
from app.worldgen.brief import CampaignBrief
from app.worldgen.guided import GuidedCreationService
from app.worldgen.service import GenerationService

pytestmark = [pytest.mark.eval, pytest.mark.integration]

BRIEF = CampaignBrief(
    title="Ash Over Calder",
    genres=["low fantasy"],
    central_pressure="a mining town whose silver seam is failing",
    party_ai_companions=2,
    player_character={"name": "Rook", "concept": "a surveyor with a debt"},  # type: ignore[arg-type]
    seed=11,
)


async def _guided_and_artifact(session, s, provider, world, report) -> None:
    h = await world.create_campaign(
        "a9-guided",
        ruleset_key="core_adventure",
        ruleset_version="0.1.0",
        engine_version="eval",
    )
    await session.commit()
    g = GuidedCreationService(
        session, s, engine=RulesEngine.load("core_adventure"), provider=provider
    )
    guided = []
    for answer in (
        "Something bleak and quiet: a dying mining town in the hills, lots of secrets, "
        "not much fighting. I'm a surveyor called Rook who owes money to the wrong people.",
        "Two companions, and I'd like it to run for a long while.",
    ):
        t0 = time.perf_counter()
        out = await g.answer(h.campaign_id, answer)
        guided.append({"seconds": round(time.perf_counter() - t0, 1), **out})
    report["guided"] = guided

    # the artifact slot
    t0 = time.perf_counter()
    definition, errors = await generate_artifact(
        session,
        h,
        provider=provider,
        settings=s,
        theme="a relic of a silver mine that remembers who dug it",
        key="item.generated_relic",
    )
    await session.commit()
    report["artifact"] = {
        "seconds": round(time.perf_counter() - t0, 1),
        "definition": definition,
        "errors": errors,
    }


async def test_generate_a_campaign_on_a9(session: AsyncSession) -> None:
    s = get_settings()
    if not s.a9_token:
        pytest.skip("A9_TOKEN not set")
    provider = A9Provider(s.a9_base_url, s.a9_token, client_name=s.a9_client_name, max_concurrent=1)
    report: dict = {"model_profile": s.model_profile_deep_world_author, "stages": []}
    world = WorldService(session)
    resume = os.environ.get("WORLDGEN_A9_RESUME")
    try:
        if not resume:
            await _guided_and_artifact(session, s, provider, world, report)
        svc = GenerationService(
            session, s, engine=RulesEngine.load("core_adventure"), provider=provider
        )
        if resume:
            run = await session.get(GenerationRun, uuid.UUID(resume))
            assert run is not None, f"no generation run {resume}"
            report["resumed"] = resume
        else:
            h2 = await world.create_campaign(
                "a9-generate",
                ruleset_key="core_adventure",
                ruleset_version="0.1.0",
                engine_version="eval",
            )
            await session.commit()
            run = await svc.create_run(h2.campaign_id, BRIEF)
        report["run_id"] = str(run.id)
        campaign_id = run.campaign_id
        t_all = time.perf_counter()
        for _ in range(18):
            before = {x.stage_key: x.status for x in await svc.stages(run.id)}
            t0 = time.perf_counter()
            run = await svc.run(run.id, max_stages=1)
            rows = await svc.stages(run.id)
            changed = [
                x for x in rows if before.get(x.stage_key) != x.status or x.status == "failed"
            ]
            for x in changed[:1]:
                mr = await session.get(ModelRun, x.model_run_id) if x.model_run_id else None
                report["stages"].append(
                    {
                        "stage": x.stage_key,
                        "status": x.status,
                        "attempts": x.attempts,
                        "seconds": round(time.perf_counter() - t0, 1),
                        "prompt_tokens": mr.prompt_tokens if mr else None,
                        "completion_tokens": mr.completion_tokens if mr else None,
                        "model_echo": mr.model_echo if mr else None,
                        "status_run": mr.status if mr else None,
                        "raw_tail": (mr.raw_output or "")[-300:]
                        if mr and x.status == "failed"
                        else None,
                        "errors": x.errors[:12],
                        "progress": {
                            "filled": sorted((x.progress or {}).get("filled", {})),
                            "failed": (x.progress or {}).get("failed", []),
                        }
                        if x.progress
                        else None,
                        "counts": {
                            k: len(v)
                            for k, v in (x.output or {}).items()
                            if isinstance(v, list) and v
                        },
                    }
                )
            if run.status in ("ready", "failed"):
                break
        report["pipeline_seconds"] = round(time.perf_counter() - t_all, 1)
        report["run_status"] = run.status
        report["run_error"] = run.error
        if run.status == "ready":
            try:
                started = await svc.start(campaign_id)
                report["start"] = started.to_dict()
            except WorldError as exc:
                report["start_error"] = str(exc)[:2000]
        runs = (
            (await session.execute(select(ModelRun).where(ModelRun.campaign_id == campaign_id)))
            .scalars()
            .all()
        )
        report["model_runs"] = len(runs)
        report["echoes"] = sorted({r.model_echo for r in runs if r.model_echo})
    finally:
        await provider.aclose()
        path = Path(
            os.environ.get("WORLDGEN_A9_REPORT") or Path(tempfile.gettempdir()) / "worldgen_a9.json"
        )
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nreport written to {path}")
    assert report["stages"], "no stage ran"
