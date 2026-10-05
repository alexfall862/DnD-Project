"""Test-only API server for the browser end-to-end tests (frontend/e2e).

The real app, wired to the `ttrpg_test` database with DEBUG_MODE on and a FakeModelProvider
scripted for the Red Lantern scene (the same replies the harness test uses) or, with
E2E_FIXTURE=frostbridge, for the whole Frostbridge vertical slice, so a browser can play
deterministic turns without a model. Never used outside tests.

    .venv/Scripts/python -m tests.e2e_server   # serves on 127.0.0.1:8001
"""

from __future__ import annotations

import os

import uvicorn
from alembic import command

from app.config import get_settings
from tests.conftest import alembic_config
from tests.integration.test_ai_actors import by_actor, npc, pc
from tests.integration.test_orchestrator import intent, responder


def script(fake) -> None:
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


def build():
    base = get_settings()
    settings = base.model_copy(
        update={
            "app_env": "test",
            "database_url": base.test_database_url,
            "a9_token": "",
            "debug_mode": True,
            "narrator_enabled": True,
            # one visible reaction per turn, as the slice runs it: reactions run concurrently,
            # so two would make who acts first (and the script) depend on timing
            "spotlight_visible_reactions": 1,
        }
    )
    command.upgrade(alembic_config(settings.database_url), "head")
    import app.main as main
    from app.main import create_app

    plain = main.FakeModelProvider

    def scripted(*args, **kwargs):
        if os.environ.get("E2E_FIXTURE") == "frostbridge":
            # the whole vertical-slice script (tests/integration/test_frostbridge_slice.py)
            from tests.integration.test_frostbridge_slice import Script, make_fake

            return make_fake(Script())
        fake = plain(*args, **kwargs)
        script(fake)
        return fake

    main.FakeModelProvider = scripted  # the lifespan builds the provider; this scripts it
    # fixed dice, so a scripted scene plays the same way every run (the slice's seed)
    load = main.RulesEngine.load

    class SeededRules:
        load = staticmethod(lambda key, **kw: load(key, **{"master_seed": 7, **kw}))

    main.RulesEngine = SeededRules
    app = create_app(settings)
    return app


if __name__ == "__main__":
    uvicorn.run(build(), host="127.0.0.1", port=int(os.environ.get("E2E_PORT", "8001")))
