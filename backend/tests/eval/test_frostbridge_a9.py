"""Opt-in (`--eval`): the real A9 model (GLM-4.5-Air) plays the Frostbridge slice and runs the
World Simulator over the Frostbridge clocks.

The slice replays the deterministic slice's player script (tests/integration/
test_frostbridge_slice.py) through the real orchestrator: interpreter, AI companions, NPCs and
narrator are all the real model. Story beats are *recorded*, not asserted: a real model may
take the scene somewhere else. What is asserted is what must hold whatever the model does:
no speaker conveys a fact it does not hold, the objective truth is untouched, the party never
holds the hidden truth it did not discover, and every turn is measured.

Reports are written as JSON to FROSTBRIDGE_A9_REPORT and WORLDSIM_A9_REPORT (default: the
system temp dir)."""

from __future__ import annotations

import json
import os
import tempfile
import time
import traceback
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.embeddings import A9Embedder
from app.ai.providers import A9Provider
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import get_settings
from app.engine.core import RulesEngine
from app.persistence.models import Belief, Claim, Event, Fact, ModelRun, Plan
from app.seeds.frostbridge import DAY, seed_frostbridge
from app.services.memory import MemoryService
from app.services.orchestrator import NeedsClarification, PlayRequest, SessionOrchestrator
from app.services.perspective import PerspectiveService
from app.services.scenes import SceneService
from app.services.simulation import SimulationService
from app.services.turns import Turn, budget_from_settings

pytestmark = [pytest.mark.eval, pytest.mark.integration]

# the deterministic slice's player script, in order (section numbers as in that test)
SCRIPT: list[tuple[str, str]] = [
    ("1 gate notice", "I read the notice on the gatepost."),
    ("2 to the tavern", "We head to the Red Lantern, all three of us."),
    ("3 ask Mira", "Innkeeper, has Oric Dane been in lately?"),
    # whispers go through the API's channel + targets, as the browser and harness send them
    ("3 whisper Mira", "whisper:Mira|Just between us: did he meet someone before he vanished?"),
    (
        "4 whisper Elara",
        "whisper:Elara|I think the innkeeper had something to do with his disappearance.",
    ),
    ("5 ask Tomas", "Tomas, what do you make of the captain?"),
    ("6 Tomas to the guard house", "Tomas, would you look at the guard house records?"),
    ("6 to the warehouse", "Elara and I go to the shuttered warehouse with the merchant sign."),
    ("7 search office", "I search the office."),
    ("7 read ledger", "I read the ledger."),
    ("7 search floor", "I search the main floor."),
    ("7 take dagger", "I pick up the dagger."),
    ("COMBAT", ""),
    ("9 rejoin", "We go over to the guard house."),
    ("10 tell Tomas", "Tomas, we found Oric's ledger. The dock numbers don't match."),
    ("11 back to tavern", "We go back to the tavern."),
    ("11 ask Renn", "Captain, when did you last speak to Oric Dane?"),
]


def report_path(env: str, default: str) -> Path:
    return Path(os.environ.get(env) or Path(tempfile.gettempdir()) / default)


def provider_and_embedder(s):
    provider = A9Provider(s.a9_base_url, s.a9_token, client_name=s.a9_client_name, max_concurrent=1)
    embedder = A9Embedder(s.a9_base_url, s.a9_token, client_name=s.a9_client_name)
    return provider, embedder


def turn_record(label: str, text: str, res, seconds: float, names: dict) -> dict:
    return {
        "label": label,
        "input": text,
        "seconds": round(seconds, 1),
        "actions": [
            {k: a.get(k) for k in ("action", "status", "text", "target") if k in a}
            for a in res.actions
        ],
        "speakers": [
            {
                "who": names.get(sp.get("actor_id"), sp.get("actor_id")),
                "channel": sp.get("channel"),
                "text": (sp.get("text") or "")[:400],
            }
            for sp in res.speakers
        ],
        "rolls": [r.get("expression") or r.get("label") for r in res.visible_rolls],
        "notices": res.mechanical_notices[:8],
        "narration": (res.narration or "")[:1200],
        "metrics": {
            k: res.metrics.get(k)
            for k in ("sync_model_calls", "calls_by_role", "latency_ms", "reactions", "budget")
            if k in res.metrics
        },
    }


async def play(orch, w, label: str, text: str, report: dict) -> object | None:
    """One player turn; a clarification is answered with the first candidate; an error is
    recorded and the script goes on."""
    t0 = time.perf_counter()
    channel, targets = "auto", []
    if text.startswith("whisper:"):
        head, text = text.split("|", 1)
        channel, targets = "whisper", [w.actors[head.split(":", 1)[1]]]
    try:
        try:
            res = await orch.process_player_input(
                w.h, PlayRequest(w.actors["Alex"], text, channel, targets)
            )
        except NeedsClarification as cl:
            report["turns"].append(
                {"label": label, "input": text, "clarification": cl.question[:300]}
            )
            res = await orch.process_player_input(
                w.h,
                PlayRequest(
                    w.actors["Alex"], "the first one", clarification_id=cl.clarification_id
                ),
            )
        await orch.session.commit()
        names = {str(v): k for k, v in w.actors.items()}
        report["turns"].append(turn_record(label, text, res, time.perf_counter() - t0, names))
        return res
    except Exception as exc:  # noqa: BLE001 - an eval records failures and continues
        await orch.session.rollback()
        report["turns"].append(
            {
                "label": label,
                "input": text,
                "error": f"{type(exc).__name__}: {exc}"[:600],
                "trace": traceback.format_exc()[-1500:],
            }
        )
        return None


async def combat(orch, w, session: AsyncSession, report: dict) -> None:
    """Section 8: two dock thieves engage Alex in the warehouse (engine setup, as in the slice);
    the real model interprets the attack and plays the companions' turns."""
    from app.persistence.models import Scene

    A = w.actors["Alex"]
    scene_id = (await PerspectiveService(session).repo.current_scene(A)).id
    scenes = SceneService(session)
    t1, t2 = w.actors["Dock thief 1"], w.actors["Dock thief 2"]
    await scenes.travel(w.h, [t1, t2], w.locations["oric_warehouse"])
    wh = await session.get(Scene, scene_id)
    space = dict(wh.state["space"])
    pos = dict(space["positions"])
    zone = pos[str(A)]["zone"]
    for t in (t1, t2):
        pos[str(t)] = {"zone": zone, "engaged_with": [str(A)], "cover": "none", "elevated": False}
    pos[str(A)] = {**pos[str(A)], "engaged_with": [str(t1), str(t2)]}
    wh.state = {**wh.state, "space": {**space, "positions": pos}}
    await session.commit()
    sides = {A: "party", w.actors["Elara"]: "party", t1: "thieves", t2: "thieves"}
    enc = await orch.actions.start_encounter(w.h, scene_id, sides)
    await session.commit()
    while enc.current_actor != str(A):
        await orch.actions.next_turn(w.h, scene_id)
        enc = (await orch.actions.load_scene(w.h, scene_id)).ctx.encounter
    await play(orch, w, "8 attack", "I attack the closest thief with my sword.", report)
    for rnd in range(1, 8):
        loaded = await orch.actions.load_scene(w.h, scene_id)
        if loaded.ctx.encounter is None or loaded.ctx.encounter.status != "active":
            report["combat_rounds"] = rnd - 1
            return
        text = "I shove the heavy shelf over onto them." if rnd == 1 else "I press the attack."
        if await play(orch, w, f"8 round {rnd}", text, report) is None:
            break
    report["combat_rounds"] = "did not end within 7 rounds"


async def safety(session: AsyncSession, w) -> dict:
    """What must hold whatever the model did. Returned for the report; asserted by the test."""
    psv = PerspectiveService(session)
    out: dict = {"conveyed_unheld": [], "party_holds_hidden_truth": []}
    claims = (
        (await session.execute(select(Claim).where(Claim.campaign_id == w.h.campaign_id)))
        .scalars()
        .all()
    )
    for c in claims:
        if c.conveyance_source == "document":
            continue  # a document's text speaks for its author (seeded, not model-proposed)
        if c.source_fact_id is not None and not await psv.repo.holds_fact(
            c.speaker_actor_id, c.source_fact_id
        ):
            out["conveyed_unheld"].append(str(c.id))
    for who in ("Alex", "Elara", "Tomas"):
        held = (
            (
                await session.execute(
                    select(Belief).where(
                        Belief.actor_id == w.actors[who],
                        Belief.fact_id == w.facts["renn_killed_oric"],
                    )
                )
            )
            .scalars()
            .all()
        )
        if held:
            out["party_holds_hidden_truth"].append(who)
    truth = await session.get(Fact, w.facts["renn_killed_oric"])
    out["truth_status"] = truth.truth_status
    out["leakage_rejections"] = [
        e.payload
        for e in (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == w.h.campaign_id,
                    Event.event_type == "proposal.rejected_leakage",
                )
            )
        ).scalars()
    ]
    out["claims"] = [
        {
            "speaker": str(c.speaker_actor_id),
            "predicate": c.predicate,
            "stance": c.speaker_stance,
            "fidelity": c.fidelity,
            "deliberate_false": c.deliberate_false,
        }
        for c in claims
    ]
    return out


async def beats(session: AsyncSession, w, report: dict) -> dict:
    """Story beats of the scripted slice, recorded (a real model may play them differently)."""

    async def fact_belief(who: str, fact: str) -> bool:
        return bool(
            (
                await session.execute(
                    select(Belief.id).where(
                        Belief.actor_id == w.actors[who], Belief.fact_id == w.facts[fact]
                    )
                )
            ).first()
        )

    said = {t["label"]: " ".join(s["text"] for s in t.get("speakers", [])) for t in report["turns"]}
    renn_claims = [c for c in report["safety"]["claims"] if c["speaker"] == str(w.actors["Renn"])]
    return {
        "alex_knows_oric_missing": await fact_belief("Alex", "oric_missing"),
        "mira_whisper_mentions_meeting": any(
            k in said.get("3 whisper Mira", "").lower() for k in ("argu", "met", "captain", "renn")
        ),
        "alex_read_ledger_discrepancies": await fact_belief("Alex", "ledger_shows_discrepancies"),
        "elara_did_not_read_ledger": not await fact_belief("Elara", "ledger_shows_discrepancies"),
        "party_saw_dock_clay": await fact_belief("Alex", "satchel_has_dock_clay"),
        "renn_lied": any(c["deliberate_false"] for c in renn_claims),
        "renn_claims": renn_claims,
    }


async def test_frostbridge_slice_on_a9(session: AsyncSession) -> None:
    s = get_settings()
    if not s.a9_token:
        pytest.skip("A9_TOKEN not set")
    settings = s.model_copy(update={"narrator_enabled": True})
    provider, embedder = provider_and_embedder(s)
    report: dict = {"turns": []}
    t_all = time.perf_counter()
    try:
        w = await seed_frostbridge(session, name="a9-slice", engine_version="eval")
        await session.commit()
        orch = SessionOrchestrator(
            session,
            settings,
            engine=RulesEngine.load("core_adventure", master_seed=11),
            provider=provider,
            embedder=embedder,
        )
        report["campaign_id"] = str(w.h.campaign_id)
        for label, text in SCRIPT:
            if label == "COMBAT":
                try:
                    await combat(orch, w, session, report)
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    report["combat_error"] = f"{type(exc).__name__}: {exc}"[:600]
                continue
            await play(orch, w, label, text, report)
        report["seconds"] = round(time.perf_counter() - t_all, 1)
        report["safety"] = await safety(session, w)
        report["beats"] = await beats(session, w, report)
        runs = (
            (await session.execute(select(ModelRun).where(ModelRun.campaign_id == w.h.campaign_id)))
            .scalars()
            .all()
        )
        by_role: dict[str, dict] = {}
        for r in runs:
            d = by_role.setdefault(r.role, {"calls": 0, "ms": [], "statuses": {}})
            d["calls"] += 1
            d["ms"].append(r.latency_ms or 0)
            d["statuses"][r.status] = d["statuses"].get(r.status, 0) + 1
        for d in by_role.values():
            ms = sorted(d.pop("ms"))
            d["median_s"] = round(ms[len(ms) // 2] / 1000, 1) if ms else None
            d["max_s"] = round(ms[-1] / 1000, 1) if ms else None
        report["model_runs"] = by_role
        report["echoes"] = sorted({r.model_echo for r in runs if r.model_echo})
    finally:
        await provider.aclose()
        path = report_path("FROSTBRIDGE_A9_REPORT", "frostbridge_a9.json")
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nreport written to {path}")
    played = [t for t in report["turns"] if "error" not in t and "clarification" not in t]
    assert played, "no turn completed"
    sf = report["safety"]
    assert sf["conveyed_unheld"] == [], sf["conveyed_unheld"]
    assert sf["party_holds_hidden_truth"] == [], sf["party_holds_hidden_truth"]
    assert sf["truth_status"] == "true"


async def test_world_simulator_on_a9(session: AsyncSession) -> None:
    """Six days pass with the party away: deterministic clocks run, then one bounded World
    Simulator call decides the due shipment; its proposal is validated before it applies."""
    s = get_settings()
    if not s.a9_token:
        pytest.skip("A9_TOKEN not set")
    provider, embedder = provider_and_embedder(s)
    report: dict = {}
    try:
        w = await seed_frostbridge(session, name="a9-sim", engine_version="eval")
        await session.commit()
        engine = RulesEngine.load("core_adventure", master_seed=3)
        memory = MemoryService(session, embedder)
        sim = SimulationService(
            session,
            s,
            engine=engine,
            compiler=ContextCompiler(session, memory=memory, engine=engine),
            runner=ModelRunner(session, ModelRouter(s, provider)),
        )
        turn = Turn(w.h, budget=budget_from_settings(s, None))
        start = (await w.world.clock(w.h)).current_tick
        await w.world.advance_time(w.h, 6 * DAY, reason="the party is away")
        now = (await w.world.clock(w.h)).current_tick
        t0 = time.perf_counter()
        run = await sim.tick(w.h, from_tick=start, to_tick=now, turn=turn)
        await session.commit()
        report["seconds"] = round(time.perf_counter() - t0, 1)
        report["run"] = run.to_dict()
        sim_runs = (
            (
                await session.execute(
                    select(ModelRun).where(
                        ModelRun.campaign_id == w.h.campaign_id,
                        ModelRun.role == "world_simulator",
                    )
                )
            )
            .scalars()
            .all()
        )
        report["simulator_calls"] = [
            {
                "status": r.status,
                "latency_s": round((r.latency_ms or 0) / 1000, 1),
                "tokens": [r.prompt_tokens, r.completion_tokens],
                "model_echo": r.model_echo,
                "output": r.structured_output,
                "validation": r.validation,
            }
            for r in sim_runs
        ]
        plan = await session.get(Plan, w.plan)
        report["plan"] = {"current_step": plan.current_step, "status": plan.status}
        departed = await session.get(Fact, w.facts["shipment_departed"])
        report["shipment_departed"] = departed.canon_status
        events = (
            (
                await session.execute(
                    select(Event).where(
                        Event.campaign_id == w.h.campaign_id, Event.event_type == "simulation.run"
                    )
                )
            )
            .scalars()
            .all()
        )
        report["simulation_events"] = [e.payload for e in events]
    finally:
        await provider.aclose()
        path = report_path("WORLDSIM_A9_REPORT", "worldsim_a9.json")
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nreport written to {path}")
    assert report["run"]["model_calls"] <= 1  # bounded: at most one simulator call per run
    assert len(report["simulation_events"]) == 1  # the run is on the ledger (Invariant 14)
