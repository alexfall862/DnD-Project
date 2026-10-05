"""Milestone 06d: a scripted session walks the Red Lantern through the terminal harness over
the HTTP API (ASGI transport) with FakeModel fixtures, and the printed mechanics match the API
responses. The harness never reads a service directly and never parses narration for state."""

from __future__ import annotations

import re

import pytest

from app.cli.play import Harness, HarnessError
from tests.integration.test_ai_actors import by_actor, npc, pc
from tests.integration.test_orchestrator import intent, responder

pytestmark = pytest.mark.integration


@pytest.fixture
def fixtures(app):
    fake = app.state.provider
    fake.register(
        "intent_interpreter",
        responder(
            {
                "lantern": intent("do", intents=[("search", "tables", None)]),
                "been in lately": intent(
                    "say",
                    intents=[("ask", "mira", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "oric",
                                "predicate": "was here lately",
                            },
                            "stance": "question",
                        }
                    ],
                    band="brief",
                ),
                "keep this between us": intent(
                    "whisper",
                    intents=[("whisper", "elara", None)],
                    conveys=[
                        {
                            "kind": "proposition",
                            "proposition": {
                                "subject_entity_id": "mira",
                                "predicate": "knows more than she says",
                            },
                            "stance": "uncertain",
                        }
                    ],
                    band="brief",
                ),
            }
        ),
    )
    fake.register(
        "npc_actor",
        by_actor(
            {
                "Mira": npc("Not for a week. He kept to himself.", conveys=[], act="evade"),
                "Renn": npc(None, act="silence"),
            }
        ),
    )
    fake.register(
        "ai_player",
        by_actor({"Elara": pc("Understood.", channel="whisper", target="alex"), "Tomas": pc(None)}),
    )
    fake.register("narrator", "Rain ticks on the shutters while Mira wipes the same glass twice.")
    fake.register(
        "memory_processor", {"memories": [], "belief_proposals": [], "emotion_proposals": []}
    )
    fake.register("journal_writer", {"title": "Red Lantern", "body": "Mira is hiding something."})
    app.state.settings.narrator_enabled = True
    return fake


async def test_scripted_session_through_the_harness(app, client, fixtures) -> None:
    lines: list[str] = []
    h = Harness(client, out=lines.append)
    await h.new_campaign(fixture="tavern")
    assert h.actor_name == "Alex" and h.campaign_id and h.scene_id
    scene = await h.show_scene()
    assert "Red Lantern Tavern" in lines[-2] and "Mira" in lines[-1]
    assert {p["known_as"] for p in scene["participants"] if not p["is_self"]} >= {
        "Mira",
        "Elara",
        "Tomas",
    }

    # a plain action: mechanics printed from the stream, narration streamed, metrics on a line
    lines.clear()
    assert await h.handle("I look under the lantern on the tables.")
    names = [n for n, _ in h.last_events]
    assert names[0] == "accepted" and "mechanics" in names and names[-1] == "result"
    assert names.index("mechanics") < names.index("narration_delta")
    res = h.last_result
    assert res["actions"][0]["action"] == "action.search"
    printed_actions = [ln for ln in lines if ln.startswith("  ⚙ action.search")]
    assert printed_actions and res["actions"][0]["status"] in printed_actions[0]
    assert (
        "".join(p["text"] for n, p in h.last_events if n == "narration_delta") == res["narration"]
    )
    status = [ln for ln in lines if ln.startswith("[") and "ms" in ln][-1]
    assert f"calls {res['metrics']['sync_model_calls']}" in status

    # speech: the AI line is labelled with the speaker's name, as the API returned it
    lines.clear()
    await h.handle("/say Mira, has Oric been in lately?")
    res = h.last_result
    mira_lines = [s for s in res["speakers"] if s["text"].startswith("Not for a week")]
    assert mira_lines and any(ln.startswith('  Mira: "Not for a week') for ln in lines)
    assert any("Rain ticks on the shutters" in ln for ln in lines)

    # whisper by name resolves the target through the actor list, not by parsing prose
    lines.clear()
    await h.handle("/whisper Elara keep this between us: Mira knows more than she says.")
    res = h.last_result
    alex_line = [
        s
        for s in res["speakers"]
        if s["channel"] == "whisper" and s["text"].startswith("keep this")
    ][0]
    elara_id = h.actors["Elara"]["actor_id"]
    assert alex_line["recipients"] == [elara_id]
    assert any(ln.startswith('  Elara: "Understood."') for ln in lines)

    # perspective views and debug subcommands go through their own endpoints
    lines.clear()
    await h.handle("/beliefs")
    assert any("knows more than she says" in ln for ln in lines)
    lines.clear()
    await h.handle("/debug events 5")
    assert len([ln for ln in lines if ln.startswith("  #")]) == 5
    lines.clear()
    await h.handle("/debug metrics")
    assert len([ln for ln in lines if re.match(r"  [0-9a-f]{8} \d+ ms", ln)]) == 3
    lines.clear()
    await h.handle("/debug runs")
    run_line = [ln for ln in lines if " narrator " in ln][-1]
    run_id = run_line.split()[0]
    lines.clear()
    await h.handle(f"/debug context {run_id}")
    # the latest narrator run is the whisper turn: its bundle holds exactly what Alex perceived
    assert lines[0].startswith("# narrator ok")
    assert any("keep this between us" in ln for ln in lines)
    assert any("Understood." in ln for ln in lines)
    # an earlier turn reaches the narrator only through the scene log (continuity), never as
    # this turn's dialogue: log lines are " | "-joined summaries of whole turns
    earlier = [ln for ln in lines if "Not for a week" in ln]
    assert earlier and all(" | " in ln for ln in earlier)
    lines.clear()
    await h.handle("/debug beliefs Tomas")
    assert not any("knows more than she says" in ln for ln in lines)  # Tomas was not whispered to

    # scene end runs the checkpoint; the journal then shows the character's view
    lines.clear()
    await h.handle("/end")
    assert lines[-1].startswith("scene ended")
    lines.clear()
    await h.handle("/journal")
    assert any("Mira is hiding something." in ln for ln in lines)
    assert await h.handle("/quit") is False


async def test_harness_refuses_ai_actors_and_reports_api_errors(app, client, fixtures) -> None:
    lines: list[str] = []
    h = Harness(client, out=lines.append)
    await h.new_campaign(fixture="tavern")
    with pytest.raises(HarnessError):
        await h.load_campaign(h.campaign_id, actor="Elara")


async def test_harness_opens_the_full_frostbridge_fixture_at_the_gate(
    app, client, fixtures
) -> None:
    """The default `--new` seed is the whole Frostbridge world: the party starts at the Town
    Gate in cold rain, Mira and Renn are elsewhere, and the player can read and travel."""
    lines: list[str] = []
    h = Harness(client, out=lines.append)
    await h.new_campaign()
    scene = await h.show_scene()
    assert "Town Gate" in lines[-2]
    known = {p["known_as"] for p in scene["participants"] if not p["is_self"]}
    assert "Elara" in known and "Tomas" in known and "Mira" not in known
    lines.clear()
    await h.handle("/inventory")
    assert any("knife" in ln for ln in lines) and not any("Dagger" in ln for ln in lines)
    app.state.settings.debug_mode = False
    try:
        with pytest.raises(HarnessError):
            await h.debug(["events"])
    finally:
        app.state.settings.debug_mode = True
