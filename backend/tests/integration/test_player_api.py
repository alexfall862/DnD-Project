"""Milestone 10 backend: the endpoints the browser client needs (campaign list/detail, settings,
sheet, party, debug turn trace), and that none of them reveals hidden data in normal mode."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.persistence.models import Event
from app.services.scenes import SceneService
from app.services.world import CampaignHandle
from tests.integration.test_play_harness import fixtures  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.integration
API = "/api/v1"


async def seed(client, fixture: str = "frostbridge") -> dict:
    r = await client.post(f"{API}/debug/seed-demo", params={"fixture": fixture})
    assert r.status_code == 200, r.text
    return r.json()


async def test_campaign_list_and_detail_name_only_the_players_characters(client) -> None:
    w = await seed(client)
    r = await client.get(f"{API}/campaigns")
    assert r.status_code == 200
    assert w["campaign_id"] in {c["id"] for c in r.json()}
    d = (await client.get(f"{API}/campaigns/{w['campaign_id']}")).json()
    assert d["debug_mode"] is True
    assert [f["name"] for f in d["focus_actors"]] == ["Alex"]  # AI companions and NPCs are not
    assert d["world_time"]["label"].startswith("Day ")
    assert (await client.get(f"{API}/campaigns/{uuid.uuid4()}")).status_code == 404


async def test_the_sheet_is_the_focus_actors_own(client) -> None:
    w = await seed(client)
    r = await client.get(f"{API}/characters/{w['actors']['Alex']}/sheet")
    assert r.status_code == 200, r.text
    sheet = r.json()
    assert sheet["name"] == "Alex"
    assert {a["name"] for a in sheet["attributes"]} >= {"Might", "Agility"}
    health = next(x for x in sheet["resources"] if x["key"] == "resource.health")
    assert 0 < health["current"] <= health["max"]
    # an AI companion's or an NPC's sheet is not the player's to read
    for who in ("Elara", "Mira"):
        r = await client.get(f"{API}/characters/{w['actors'][who]}/sheet")
        assert r.status_code == 403, who
        assert r.json()["error"]["code"] == "UNAUTHORIZED_PERSPECTIVE"


async def test_the_party_is_what_the_focus_actor_perceives(client, session_factory) -> None:
    w = await seed(client)
    cid, alex = w["campaign_id"], w["actors"]["Alex"]
    r = await client.get(f"{API}/campaigns/{cid}/party", params={"actor_id": alex})
    assert r.status_code == 200, r.text
    members = {m["known_as"]: m for m in r.json()}
    assert set(members) == {"you", "Elara", "Tomas"}
    assert all(m["with_you"] and m["wound_state"] == "unhurt" for m in members.values())
    assert members["Elara"]["controller"] == "ai" and members["you"]["is_focus"]
    # no numbers, goals or relationships for anyone
    assert all(set(m) == set(members["you"]) for m in members.values())
    assert not any(k in str(r.json()) for k in ("trust", "goal", "current", "max"))

    # split party: Tomas leaves; he is "away" with nothing else known about him
    async with session_factory() as s:
        h = CampaignHandle(uuid.UUID(cid), uuid.UUID(w["timeline_id"]))
        await SceneService(s).travel(
            h, [uuid.UUID(w["actors"]["Tomas"])], uuid.UUID(w["locations"]["guard_house"])
        )
        await s.commit()
    members = {
        m["known_as"]: m
        for m in (
            await client.get(f"{API}/campaigns/{cid}/party", params={"actor_id": alex})
        ).json()
    }
    assert members["Tomas"]["with_you"] is False
    assert members["Tomas"]["wound_state"] is None and members["Tomas"]["visible_conditions"] == []
    # an AI actor cannot be used as the viewpoint
    r = await client.get(f"{API}/campaigns/{cid}/party", params={"actor_id": w["actors"]["Elara"]})
    assert r.status_code == 403


async def test_player_settings_change_with_an_event_and_nothing_else_is_writable(
    client, session_factory
) -> None:
    w = await seed(client)
    cid = w["campaign_id"]
    r = await client.patch(
        f"{API}/campaigns/{cid}/settings", json={"changes": {"narration_style": "terse"}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["settings"]["narration_style"] == "terse"
    async with session_factory() as s:
        evs = (
            (
                await s.execute(
                    select(Event).where(
                        Event.campaign_id == uuid.UUID(cid),
                        Event.event_type == "settings.changed",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert evs and evs[-1].payload["changes"] == {"narration_style": "terse"}
    r = await client.patch(
        f"{API}/campaigns/{cid}/settings", json={"changes": {"genre_modules": ["horror"]}}
    )
    assert r.status_code == 422


async def test_a_turn_can_be_traced_in_debug_mode_only(app, client, fixtures) -> None:  # noqa: F811
    w = await seed(client, "tavern")
    cid, alex = w["campaign_id"], w["actors"]["Alex"]
    r = await client.post(
        f"{API}/campaigns/{cid}/play",
        json={"actor_id": alex, "text": "I look under the lantern on the tables."},
    )
    assert r.status_code == 200, r.text
    turn_id = r.json()["turn_id"]
    tr = await client.get(f"{API}/debug/turns/{turn_id}")
    assert tr.status_code == 200, tr.text
    t = tr.json()
    assert t["actions"] and t["actions"][0]["action"] == "action.search"
    assert t["model_runs"] and {m["role"] for m in t["model_runs"]} >= {"intent_interpreter"}
    assert t["metrics"]["sync_model_calls"] >= 1
    assert t["events"]  # (the interpretation itself is the intent_interpreter model run)
    assert (await client.get(f"{API}/debug/turns/{uuid.uuid4()}")).status_code == 404
    app.state.settings.debug_mode = False
    try:
        assert (await client.get(f"{API}/debug/turns/{turn_id}")).status_code == 403
        d = (await client.get(f"{API}/campaigns/{cid}")).json()
        assert d["debug_mode"] is False
    finally:
        app.state.settings.debug_mode = True


async def test_scene_and_turn_responses_carry_no_hidden_data(app, client, fixtures) -> None:  # noqa: F811
    """Hidden-data absence on the normal surface the UI renders: the dagger's hidden property
    and Renn's secret never appear in scene, inventory, party, sheet, journal or a play turn."""
    w = await seed(client, "tavern")
    cid, alex = w["campaign_id"], w["actors"]["Alex"]
    r = await client.post(
        f"{API}/campaigns/{cid}/play",
        json={"actor_id": alex, "text": "I look under the lantern on the tables."},
    )
    bodies = [r.text]
    for url, params in (
        (f"{API}/campaigns/{cid}/scene", {"actor_id": alex}),
        (f"{API}/characters/{alex}/inventory", None),
        (f"{API}/campaigns/{cid}/party", {"actor_id": alex}),
        (f"{API}/characters/{alex}/sheet", None),
        (f"{API}/characters/{alex}/journal", None),
        (f"{API}/characters/{alex}/encyclopedia", None),
        (f"{API}/campaigns/{cid}", None),
    ):
        resp = await client.get(url, params=params)
        assert resp.status_code == 200, (url, resp.text)
        bodies.append(resp.text)
    text = " ".join(bodies).lower()
    for secret in ("killed", "spirit", "hidden_properties", "renn_killed_oric", "truth"):
        assert secret not in text, secret


async def test_the_feed_is_kept_on_the_server_for_the_player_who_saw_it(
    app,
    client,
    fixtures,  # noqa: F811
) -> None:
    """Any device shows the same history: each turn as the API returned it to this player,
    and nobody else's."""
    w = await seed(client, "tavern")
    cid, alex = w["campaign_id"], w["actors"]["Alex"]
    for text in (
        "I look under the lantern on the tables.",
        "Innkeeper, has Oric Dane been in lately?",
    ):
        r = await client.post(f"{API}/campaigns/{cid}/play", json={"actor_id": alex, "text": text})
        assert r.status_code == 200, r.text
    r = await client.post(
        f"{API}/campaigns/{cid}/play",
        json={
            "actor_id": alex,
            "text": "keep this between us, Mira knows more than she says",
            "channel": "whisper",
            "target_actor_ids": [w["actors"]["Elara"]],
        },
    )
    assert r.status_code == 200, r.text
    feed = (await client.get(f"{API}/characters/{alex}/feed")).json()
    assert [f["input"]["text"][:14] for f in feed] == [
        "I look under t",
        "Innkeeper, has",
        "keep this betw",
    ]
    assert feed[0]["result"]["narration"].startswith("Rain ticks")
    assert feed[1]["result"]["speakers"]
    assert feed[2]["input"] == {
        "text": "keep this between us, Mira knows more than she says",
        "channel": "whisper",
        "to": ["Elara"],
    }
    assert len((await client.get(f"{API}/characters/{alex}/feed", params={"limit": 1})).json()) == 1
    # an AI companion's feed is not the player's to read
    assert (await client.get(f"{API}/characters/{w['actors']['Elara']}/feed")).status_code == 403


async def _stream(client, url: str, body: dict) -> list[tuple[str, dict]]:
    import json as _json

    events: list[tuple[str, dict]] = []
    async with client.stream("POST", url, json=body, headers={"Accept": "text/event-stream"}) as r:
        name = None
        async for line in r.aiter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:") and name:
                events.append((name, _json.loads(line[5:])))
    return events


async def test_the_turn_stream_reports_stages_and_each_model_call(
    app,
    client,
    fixtures,  # noqa: F811
) -> None:
    """Play session 2026-10-05: the player could not tell what a slow turn was doing. The
    stream now carries stages and every model call's start and finish, with the run id that
    opens what was sent."""
    w = await seed(client, "tavern")
    cid, alex = w["campaign_id"], w["actors"]["Alex"]
    events = await _stream(
        client,
        f"{API}/campaigns/{cid}/play",
        {"actor_id": alex, "text": "I look under the lantern on the tables."},
    )
    names = [n for n, _ in events]
    stages = [p["stage"] for n, p in events if n == "stage"]
    assert stages[:2] == ["interpreting", "resolving"] and "narrating" in stages
    calls = [p for n, p in events if n == "model_call"]
    started = [c for c in calls if c["phase"] == "started"]
    finished = [c for c in calls if c["phase"] == "finished"]
    assert started and started[0]["role"] == "intent_interpreter"
    assert started[0]["context_snapshot_id"] and started[0]["max_tokens"] >= 1000
    assert {c["run_id"] for c in started} == {c["run_id"] for c in finished}
    assert names.index("accepted") < names.index("model_call") < names.index("result")
    ctx = await client.get(f"{API}/debug/model-runs/{started[0]['run_id']}/context")
    assert ctx.status_code == 200  # "what was sent" opens while the turn is still running


async def test_a_failed_turn_keeps_its_audit_and_history(app, client, fixtures) -> None:  # noqa: F811
    """Play session 2026-10-05: a failing turn rolled back the record of the calls it made.
    The world change rolls back; the model runs, the feed entry and the trace stay. (An
    unparseable interpretation no longer fails a turn, so the failure here is a ruling call
    that blows up.)"""
    w = await seed(client, "tavern")
    cid, alex = w["campaign_id"], w["actors"]["Alex"]
    fixtures.replace(
        "intent_interpreter",
        lambda req: {
            "channel": "do",
            "confidence": 0.9,
            "intents": [{"order": 1, "action_type": "other", "target_ref": None}],
        },
    )

    def explode(req):
        raise RuntimeError("adjudicator crashed")

    fixtures.replace("rules_adjudicator", explode)
    events = await _stream(
        client,
        f"{API}/campaigns/{cid}/play",
        {"actor_id": alex, "text": "I juggle the tankards."},
    )
    errors = [p for n, p in events if n == "error"]
    assert errors and errors[-1]["code"] == "INTERNAL_ERROR"
    feed = (await client.get(f"{API}/characters/{alex}/feed")).json()
    last = feed[-1]
    assert last["input"]["text"] == "I juggle the tankards." and "error" in last["result"]
    trace = (await client.get(f"{API}/debug/turns/{last['turn_id']}")).json()
    runs = {m["role"]: m["status"] for m in trace["model_runs"]}
    assert runs.get("intent_interpreter") == "ok" and runs.get("rules_adjudicator") == "failed"


async def test_a_whisper_can_go_to_several_listeners(app, client, fixtures) -> None:  # noqa: F811
    """Play session 2026-10-05: whispers were one-to-one in the UI. The API takes several
    targets: each of them hears it, nobody else does."""
    from sqlalchemy import select as _select

    from app.persistence.models import TranscriptMessage, TranscriptRecipient

    w = await seed(client, "tavern")
    cid, alex = w["campaign_id"], w["actors"]["Alex"]
    party = [w["actors"]["Elara"], w["actors"]["Tomas"]]
    r = await client.post(
        f"{API}/campaigns/{cid}/play",
        json={
            "actor_id": alex,
            "text": "keep this between us: Mira knows more than she says",
            "channel": "whisper",
            "target_actor_ids": party,
        },
    )
    assert r.status_code == 200, r.text

    async with app.state.session_factory() as s:
        msg = (
            (
                await s.execute(
                    _select(TranscriptMessage)
                    .where(
                        TranscriptMessage.speaker_actor_id == uuid.UUID(alex),
                        TranscriptMessage.channel == "whisper",
                    )
                    .order_by(TranscriptMessage.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        heard = {
            str(x.actor_id)
            for x in (
                await s.execute(
                    _select(TranscriptRecipient).where(TranscriptRecipient.message_id == msg.id)
                )
            ).scalars()
        }
    assert set(party) <= heard and w["actors"]["Mira"] not in heard
    feed = (await client.get(f"{API}/characters/{alex}/feed")).json()
    assert sorted(feed[-1]["input"]["to"]) == ["Elara", "Tomas"]
