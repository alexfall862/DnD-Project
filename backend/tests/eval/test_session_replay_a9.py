"""Opt-in (`--eval`): replay the 2026-10-05 browser play session at the Frostbridge gate on the
real A9 model, through the full HTTP API (feed, scene log, promotion, dice, OOC), answering
every called-for check with "roll". Nothing about the story is asserted; the record shows,
per turn, what was interpreted, rolled, said and narrated, and the safety facts that must
hold are asserted. Report: SESSION_A9_REPORT (default: system temp dir)."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.main import create_app
from app.persistence.models import ActorController, Belief, Claim, Event, Memory

pytestmark = [pytest.mark.eval, pytest.mark.integration]
API = "/api/v1"

SESSION: list[tuple[str, str, list[str]]] = [
    ("auto", "Can you describe my surroundings? Where are we?", []),
    ("ooc", "Tell me more about what I see at this moment", []),
    (
        "say",
        "Excuse me, merchant! What is your issue with these guards? May we be of assistance?",
        [],
    ),
    (
        "auto",
        "I'd like to subtly motion for Elara to discretely inspect the suspicious crate while I "
        "distract the guards and merchant with conversation. I want to ask about both where he's "
        "coming from and what the guards think is suspicious about the crate.",
        [],
    ),
    ("whisper", "Go see if you can learn more about the crate.", ["Elara"]),
    (
        "auto",
        "We'd like to discretely tail this merchant where he's going. Can we pay a small bribe to "
        "the guards to let us know where the merchant is headed so we can work around while also "
        "tracking his movements? We'll have Tomas track ahead to his destination and Elara will "
        "tail his movement. I'll meet with anyone he encounters after the merchant interacts "
        "with them.",
        [],
    ),
    ("auto", "Yes - we want in on whatever is in that crate you just got past the guards.", []),
    (
        "auto",
        "I'd like to say \"You know and I know what you have. Let me in on it. Either way it's "
        "mine - one way we both make money and the other way ends up with you missing your "
        'goods"',
        [],
    ),
    (
        "say",
        "My partners Tomas and Elara and myself are going to cross through the town and cover more "
        "ground and get these goods moved asap. How many units can we move?",
        [],
    ),
    (
        "auto",
        "Okay - let's make it serious. We'll leave Tomas here as collateral so you can trust we'll "
        "come back with your profit.",
        [],
    ),
    ("auto", "We're going to sell your goods for you and split the profits.", []),
    ("ooc", "What does my character remember about the deal with the merchant so far?", []),
    (
        "auto",
        "Okay then the three of us are just going to attack and rob the merchant of all his goods. "
        "I say \"Okay if you won't play ball we'll make you\"",
        [],
    ),
]


def summarize(label: str, body: dict, seconds: float, names: dict[str, str]) -> dict:
    return {
        "turn": label,
        "seconds": round(seconds, 1),
        "channel": body.get("channel"),
        "actions": [f"{a.get('action')}→{a.get('status')}" for a in body.get("actions", [])],
        "rolls": [
            {k: r.get(k) for k in ("purpose", "natural", "total", "dc", "success")}
            for r in body.get("visible_rolls", [])
        ],
        "speakers": [
            f"{names.get(s.get('actor_id'), s.get('actor_id'))}: {s.get('text', '')[:160]}"
            for s in body.get("speakers", [])
        ],
        "ooc": (body.get("ooc") or "")[:500],
        "narration": (body.get("narration") or "")[:700],
        "dev_notes": body.get("dev_notes", [])[:8],
        "calls": body.get("metrics", {}).get("calls_by_role"),
        "roll_request": (body.get("roll_request") or {}).get("prompt"),
    }


async def test_replay_the_play_session_on_a9() -> None:
    base = get_settings()
    if not base.a9_token:
        pytest.skip("A9_TOKEN not set")
    settings = base.model_copy(
        update={
            "database_url": base.test_database_url,
            "debug_mode": True,
            "narrator_enabled": True,
        }
    )
    import asyncio

    from alembic import command

    from tests.conftest import alembic_config

    await asyncio.to_thread(command.upgrade, alembic_config(settings.database_url), "head")
    app = create_app(settings)
    report: dict = {"turns": [], "errors": []}
    t_all = time.perf_counter()
    try:
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test", timeout=600
            ) as client:
                w = (
                    await client.post(f"{API}/debug/seed-demo", params={"fixture": "frostbridge"})
                ).json()
                cid, alex = w["campaign_id"], w["actors"]["Alex"]
                report["campaign_id"] = cid
                await client.patch(
                    f"{API}/campaigns/{cid}/settings", json={"changes": {"dice_mode": "manual"}}
                )
                names = {v: k for k, v in w["actors"].items()}
                for i, (channel, text, to) in enumerate(SESSION, 1):
                    body = {
                        "actor_id": alex,
                        "text": text,
                        "channel": channel,
                        "target_actor_ids": [w["actors"][n] for n in to],
                    }
                    t0 = time.perf_counter()
                    r = await client.post(f"{API}/campaigns/{cid}/play", json=body)
                    out = r.json()
                    if r.status_code != 200:
                        report["turns"].append({"turn": i, "input": text[:80], "error": out})
                        continue
                    entry = summarize(f"{i}", out, time.perf_counter() - t0, names)
                    entry["input"] = text[:90]
                    report["turns"].append(entry)
                    if out.get("roll_request"):
                        t0 = time.perf_counter()
                        r2 = await client.post(
                            f"{API}/campaigns/{cid}/play",
                            json={
                                "actor_id": alex,
                                "text": "Roll",
                                "roll_request_id": out["roll_request"]["id"],
                                "roll_decision": "roll",
                            },
                        )
                        o2 = r2.json()
                        e2 = (
                            summarize(f"{i} (rolled)", o2, time.perf_counter() - t0, names)
                            if r2.status_code == 200
                            else {"turn": f"{i} (rolled)", "error": o2}
                        )
                        report["turns"].append(e2)
                merchant = uuid.UUID(w["actors"]["Irritated merchant"])
                async with app.state.session_factory() as s:
                    ctrl = (
                        await s.execute(
                            select(ActorController.controller_type).where(
                                ActorController.actor_id == merchant,
                                ActorController.valid_until_event_id.is_(None),
                            )
                        )
                    ).scalar_one()
                    promoted = (
                        (
                            await s.execute(
                                select(Event).where(
                                    Event.campaign_id == uuid.UUID(cid),
                                    Event.event_type == "actor.promoted",
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    mems = (
                        (await s.execute(select(Memory).where(Memory.actor_id == merchant)))
                        .scalars()
                        .all()
                    )
                    claims = (
                        (await s.execute(select(Claim).where(Claim.campaign_id == uuid.UUID(cid))))
                        .scalars()
                        .all()
                    )
                    truth = w["facts"].get("renn_killed_oric")
                    party_truth = []
                    if truth:
                        for who in ("Alex", "Elara", "Tomas"):
                            held = (
                                await s.execute(
                                    select(Belief.id).where(
                                        Belief.actor_id == uuid.UUID(w["actors"][who]),
                                        Belief.fact_id == uuid.UUID(truth),
                                    )
                                )
                            ).first()
                            if held:
                                party_truth.append(who)
                report["merchant"] = {
                    "controller": ctrl,
                    "promoted_events": [e.payload for e in promoted],
                    "memories": [m.subjective_summary for m in mems],
                }
                report["claims"] = len(claims)
                report["party_holds_hidden_truth"] = party_truth
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        report["seconds"] = round(time.perf_counter() - t_all, 1)
        path = Path(
            os.environ.get("SESSION_A9_REPORT") or Path(tempfile.gettempdir()) / "session_a9.json"
        )
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nreport written to {path}")
    assert report["party_holds_hidden_truth"] == []
    assert not [t for t in report["turns"] if "error" in t], [
        t for t in report["turns"] if "error" in t
    ]
