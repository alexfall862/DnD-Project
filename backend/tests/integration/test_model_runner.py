"""ModelRunner with FakeModelProvider: audited runs, validation, one bounded repair,
failure handling, streaming."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.providers import FakeModelProvider, ModelRequest, ProviderError
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner, RunResult
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import DecisionTrace, ModelRun
from tests.fixtures.frostbridge import World

pytestmark = pytest.mark.integration


def good_player(ctx) -> dict:
    ref = sorted(ctx.belief_refs)[0]
    return {
        "decision_summary": "Keep quiet and watch Mira.",
        "spoken_text": None,
        "speech_channel": "none",
        "conveys": [{"kind": "belief_ref", "ref_id": ref, "stance": "asserts_true"}],
        "intentions": [
            {
                "action_type": "observe",
                "target_ref": "mira",
                "description": "watch her",
                "private": True,
            }
        ],
        "belief_proposals": [],
        "emotion_proposals": [],
    }


async def test_run_records_audit_and_decision_trace(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    compiler = ContextCompiler(session, engine=RulesEngine.load("core_adventure"))
    ctx = await compiler.compile(
        w.h, "ai_player", actor_id=w.actors["Elara"], purpose="react", situation="Decide."
    )
    fake.register("ai_player", good_player(ctx))
    runner = ModelRunner(session, ModelRouter(Settings(), fake))
    res = await runner.run(w.h, ctx)
    assert res.ok and res.status == "ok" and res.calls == 1
    assert (
        res.output.decision_summary.startswith("Keep quiet")
        and res.output.conveys[0].kind == "belief_ref"
    )
    row = await session.get(ModelRun, res.model_run_id)
    assert (
        row.role == "ai_player"
        and row.context_snapshot_id == ctx.snapshot_id
        and row.structured_output["decision_summary"].startswith("Keep")
    )
    assert (
        row.prompt_id == "ai_player"
        and row.prompt_version == 1
        and len(row.prompt_hash) == 64
        and row.status == "ok"
    )
    assert (
        row.model_requested == Settings().model_profile_balanced_reasoning
        and row.provider == "fake"
    )
    trace = (
        await session.execute(select(DecisionTrace).where(DecisionTrace.model_run_id == row.id))
    ).scalar_one()
    assert (
        trace.actor_id == w.actors["Elara"]
        and trace.selected_intent["intentions"][0]["action_type"] == "observe"
    )
    # the request the provider saw: role-keyed system prompt, context as user, unique run id
    call = fake.calls[-1].request
    assert (
        call.system.startswith("# role: ai_player") and call.user == ctx.rendered and call.json_mode
    )
    assert call.messages()[1]["content"].startswith(f"run_id: {res.model_run_id}")


async def test_one_bounded_repair_then_invalid(session: AsyncSession, frostbridge: World) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    compiler = ContextCompiler(session)
    ctx = await compiler.compile(
        w.h,
        "npc_actor",
        actor_id=w.actors["Mira"],
        purpose="answer",
        situation="Alex asks about Renn.",
    )
    broken = (
        '```json\n{"decision_summary": "Deflect", "speech_act": {"type": "evade"}, '
        '"spoken_text": "People come and go", "conveys": [{"kind": "proposition", '
        '"predicate": "people come and go"'
    )
    fixed = {
        "decision_summary": "Deflect",
        "speech_act": {"type": "evade"},
        "spoken_text": "People come and go.",
        "conveys": [
            {
                "kind": "proposition",
                "proposition": {"predicate": "people come and go"},
                "stance": "asserts_true",
            }
        ],
        "intentions": [],
        "emotion_proposals": [],
    }
    fake.register("npc_actor", broken).register("npc_actor", fixed)
    runner = ModelRunner(session, ModelRouter(Settings(), fake))
    res = await runner.run(w.h, ctx)
    assert res.status == "repaired" and res.calls == 2 and res.ok
    repair_req: ModelRequest = fake.calls[-1].request
    assert (
        repair_req.history
        and "failed validation" in repair_req.history[-1]["content"]
        and repair_req.temperature == 0.1
    )
    row = await session.get(ModelRun, res.model_run_id)
    assert row.status == "repaired" and row.validation["calls"] == 2
    # twice invalid → invalid, no mutation anywhere, errors recorded
    fake2 = (
        FakeModelProvider().register("npc_actor", "garbage").register("npc_actor", "still garbage")
    )
    res2 = await ModelRunner(session, ModelRouter(Settings(), fake2)).run(w.h, ctx)
    assert res2.status == "invalid" and not res2.ok and res2.output is None and res2.errors
    assert (await session.get(ModelRun, res2.model_run_id)).status == "invalid"


async def test_provider_failure_is_recorded_not_raised(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge

    class Broken(FakeModelProvider):
        async def generate(self, req):
            raise ProviderError("A9 500")

    ctx = await ContextCompiler(session).compile(
        w.h, "ai_player", actor_id=w.actors["Elara"], purpose="x", situation="x"
    )
    res = await ModelRunner(session, ModelRouter(Settings(), Broken())).run(w.h, ctx)
    assert (
        res.status == "failed" and (await session.get(ModelRun, res.model_run_id)).error == "A9 500"
    )


async def test_narrator_streams_then_reports(session: AsyncSession, frostbridge: World) -> None:
    w = frostbridge
    fake = FakeModelProvider()
    fake.register("narrator", "The taproom is warm; a fire crackles in the hearth. Mira nods.")
    ctx = await ContextCompiler(session).compile(
        w.h,
        "narrator",
        actor_id=w.actors["Alex"],
        purpose="narrate",
        situation="Narrate entering the tavern.",
        extra_sections={"style": "second person, concise"},
    )
    deltas, final = [], None
    async for item in ModelRunner(session, ModelRouter(Settings(), fake)).stream(w.h, ctx):
        if isinstance(item, RunResult):
            final = item
        else:
            deltas.append(item)
    assert len(deltas) > 1 and final is not None and final.ok
    assert "".join(deltas).startswith("The taproom") and final.output is None  # prose role
    assert (await session.get(ModelRun, final.model_run_id)).parameters["stream"] is True
