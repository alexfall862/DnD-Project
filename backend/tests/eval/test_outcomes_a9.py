"""Opt-in (`--eval`): the lines that failed in play session 2 (campaign 879ea872), replayed on
the real A9 model at the Frostbridge gate through the full HTTP API, to see the 10d changes
work with GLM: table-assistant suggestions, a called check whose ruling names consequences,
a social attempt with its ruling, buying at list price (and failing to afford a wagon), and
going into town as travel. Every called-for check is rolled. Nothing about the story is
asserted; the safety facts are. Report: OUTCOMES_A9_REPORT (default: system temp dir)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import create_app

pytestmark = [pytest.mark.eval, pytest.mark.integration]
API = "/api/v1"

# (channel, text, check skill or None)
SESSION: list[tuple[str, str, str | None]] = [
    ("ooc", "We want to get into town without waiting all day. What are our options?", None),
    ("say", "Excuse me, what's the hold-up with the inspections today?", None),
    ("do", "along the town wall and the hedgerow for another way in", "skill.investigation"),
    (
        "auto",
        "I tell the older guard firmly that his captain will hear about this delay unless he "
        "waves us through now.",
        None,
    ),
    ("auto", "I buy the merchant's whole wagon.", None),
    ("auto", "I buy a coil of rope from the merchant.", None),
    ("ooc", "yes", None),
    ("auto", "We go into town.", None),
    ("auto", "Where are we?", None),
]


def summarize(label: str, body: dict, seconds: float, names: dict[str, str]) -> dict:
    return {
        "turn": label,
        "seconds": round(seconds, 1),
        "channel": body.get("channel"),
        "actions": [
            f"{a.get('action')}→{a.get('status')}"
            + (f" ({a.get('reason')})" if a.get("reason") else "")
            for a in body.get("actions", [])
        ],
        "consequences": [c.get("text") for c in body.get("consequences", [])],
        "rolls": [
            {k: r.get(k) for k in ("purpose", "natural", "total", "dc", "success")}
            for r in body.get("visible_rolls", [])
        ],
        "speakers": [
            f"{names.get(s.get('actor_id'), s.get('actor_id'))}: {s.get('text', '')[:160]}"
            for s in body.get("speakers", [])
        ],
        "notices": body.get("mechanical_notices", [])[:6],
        "ooc": (body.get("ooc") or "")[:500],
        "suggestions": body.get("suggestions", []),
        "narration": (body.get("narration") or "")[:700],
        "dev_notes": body.get("dev_notes", [])[:12],
        "calls": body.get("metrics", {}).get("calls_by_role"),
        "roll_request": (body.get("roll_request") or {}).get("prompt"),
    }


async def test_outcomes_change_the_world_on_a9() -> None:
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
    report: dict = {"turns": [], "here": []}
    t_all = time.perf_counter()
    try:
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test", timeout=900
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
                for i, (channel, text, skill) in enumerate(SESSION, 1):
                    body = {"actor_id": alex, "text": text, "channel": channel}
                    if skill:
                        body["check_skill"] = skill
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
                        report["turns"].append(
                            summarize(f"{i} (rolled)", o2, time.perf_counter() - t0, names)
                            if r2.status_code == 200
                            else {"turn": f"{i} (rolled)", "error": o2}
                        )
                    here = await client.get(f"{API}/characters/{alex}/here")
                    if here.status_code == 200:
                        h = here.json()
                        report["here"].append(
                            {
                                "after": i,
                                "location": h["location"],
                                "exits": [
                                    e["known_as"]
                                    + (f" BLOCKED: {e['blocked_by']}" if e["blocked_by"] else "")
                                    for e in h["exits"]
                                ],
                                "situations": [s["text"] for s in h["situations"]],
                            }
                        )
    finally:
        report["total_seconds"] = round(time.perf_counter() - t_all, 1)
        path = Path(
            os.environ.get("OUTCOMES_A9_REPORT") or Path(tempfile.gettempdir()) / "outcomes_a9.json"
        )
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    failed = [t for t in report["turns"] if "error" in t]
    assert not [t for t in failed if t["error"].get("error", {}).get("code") == "INTERNAL_ERROR"]
    # nothing structured reaches the player as prose
    for t in report["turns"]:
        for field in ("narration", "ooc"):
            assert not (t.get(field) or "").lstrip().startswith(("{", "```")), t
