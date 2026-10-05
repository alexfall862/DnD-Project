"""Outcomes change the world (DECISIONS 10d): recorded situations, the closed consequence
vocabulary, travel stopped only by a recorded obstacle, no soft-blocks, and the Phase 1
play fixes (no-op moves, called checks, whispers to companions, table-assistant suggestions).

Play session 2 (campaign 879ea872): the gate was never closed in the world, a successful
Intimidation changed nothing, a found gap in the hedge was scenery, and "go in" failed as
"already there"."""

from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import FakeModelProvider
from app.config import Settings
from app.domain.consequences import SPECS
from app.engine.core import RulesEngine
from app.persistence.models import Entity, Event, Location, Situation
from app.services.consequences import ConsequenceContext, ConsequenceService
from app.services.events import EventTransaction
from app.services.orchestrator import PlayRequest, SessionOrchestrator
from app.services.situations import SituationService, sref
from tests.fixtures.frostbridge import World

pytestmark = pytest.mark.integration


def intent(channel="do", intents=(), utterance=None):
    out = {
        "channel": channel,
        "confidence": 0.9,
        "intents": [
            {"order": i + 1, "action_type": a, "target_ref": t, "params": {}}
            for i, (a, t) in enumerate(intents)
        ],
        "conversation_time_band": "brief" if channel == "say" else "none",
    }
    if utterance:
        out["utterance"] = utterance
    return out


def responder(table: dict[str, dict]):
    def pick(req):
        m = re.search(r'Player input \(channel: \w+\): "(.*)"', req.user)
        text = m.group(1) if m else req.user
        for phrase, out in table.items():
            if phrase in text:
                return out
        raise AssertionError(f"no fake intent for input: {req.user[-200:]}")

    return pick


def make(session: AsyncSession, fake: FakeModelProvider) -> SessionOrchestrator:
    return SessionOrchestrator(
        session,
        Settings(a9_token="", spotlight_visible_reactions=0, narrator_enabled=False),
        engine=RulesEngine.load("core_adventure", master_seed=11),
        provider=fake,
    )


async def where(session: AsyncSession, orch: SessionOrchestrator, actor_id) -> uuid.UUID | None:
    scene = await orch.perspective.repo.current_scene(actor_id)
    return scene.location_id if scene else None


async def place_ref(orch: SessionOrchestrator, w: World, location_id) -> str:
    scene = await orch.perspective.repo.current_scene(w.actors["Alex"])
    cands = await orch._candidates(w.h, w.actors["Alex"], scene)
    return next(c.ref for c in cands if c.kind == "location" and c.id == str(location_id))


async def obstacle(session: AsyncSession, w: World, *, holder: str | None = "Mira") -> Situation:
    async with EventTransaction(session, w.h.campaign_id, w.h.timeline_id) as tx:
        s = await SituationService(session).open(
            tx,
            kind="obstacle",
            label="the back door is barred",
            location_id=w.tavern,
            holder_actor_id=w.actors[holder] if holder else None,
            data={"blocks": [str(w.guard_house)], "ways_past": ["ask Mira"], "passed": []},
        )
    return s


def test_the_vocabulary_is_closed_and_every_kind_has_an_applier() -> None:
    assert len(SPECS) >= 30
    for kind in SPECS:
        assert hasattr(ConsequenceService, f"_k_{kind}"), kind


async def test_travel_is_stopped_only_by_a_recorded_obstacle_and_a_success_opens_it(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    s = await obstacle(session, w)
    fake = FakeModelProvider()
    orch = make(session, fake)
    gh = await place_ref(orch, w, w.guard_house)
    fake.register(
        "intent_interpreter",
        responder(
            {
                "go to the guard house": intent("do", [("travel", gh)]),
                "unbar": intent("do", [("other", None)]),
            }
        ),
    )
    fake.register(
        "rules_adjudicator",
        {
            "requires_check": False,
            "summary": "Mira unbars it for them",
            "consequences": {"success": [{"kind": "grant_passage", "obstacle": sref(s)}]},
        },
    )
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I go to the guard house.")
    )
    assert res.actions[0]["status"] == "blocked"
    assert any("Ways past: ask Mira" in n for n in res.mechanical_notices)
    assert await where(session, orch, w.actors["Alex"]) == w.tavern
    await session.refresh(s)
    assert s.data["attempts"] == 1

    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I ask Mira to unbar the back door for me.")
    )
    assert [c["kind"] for c in res.consequences] == ["grant_passage"]
    applied = (
        (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == w.h.campaign_id, Event.event_type == "consequence.applied"
                )
            )
        )
        .scalars()
        .all()
    )
    assert applied and applied[-1].payload["kind"] == "grant_passage"

    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I go to the guard house.")
    )
    assert res.actions[0]["status"] == "succeeded"
    assert await where(session, orch, w.actors["Alex"]) == w.guard_house


async def test_an_actor_lifts_only_what_it_holds_and_bad_proposals_change_nothing(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    s = await obstacle(session, w)
    engine = RulesEngine.load("core_adventure", master_seed=3)
    svc = ConsequenceService(session, engine)
    orch = make(session, FakeModelProvider())
    scene = await orch.perspective.repo.current_scene(w.actors["Mira"])

    async def ctx(name: str) -> ConsequenceContext:
        cands = await orch._candidates(w.h, w.actors[name], scene)
        return ConsequenceContext(
            w.h,
            scene,
            w.actors[name],
            w.actors[name],
            cands,
            "actor",
            None,
            None,
            focus_actor_id=w.actors["Alex"],
        )

    renn = await svc.apply_one(await ctx("Renn"), "grant_passage", {"obstacle": sref(s)})
    assert not renn.ok and "holding" in renn.reason
    bad = await svc.apply_all(
        await ctx("Mira"),
        [
            {"kind": "summon_dragon"},
            {"kind": "agree", "person": "self"},  # missing the request
            {"kind": "change_attitude", "person": "renn", "dimension": "trust", "delta": 1},
            {"kind": "open_route", "label": "a tunnel", "to": "guard_house"},  # not an actor's
        ],
    )
    assert [a.ok for a in bad] == [False, False, False, False]
    mira = await svc.apply_one(await ctx("Mira"), "grant_passage", {"obstacle": sref(s)})
    assert mira.ok
    await session.refresh(s)
    assert str(w.actors["Alex"]) in s.data["passed"]
    promise = await svc.apply_one(
        await ctx("Mira"),
        "agree",
        {"person": "self", "request": "keep the back door open", "lets_pass": sref(s)},
    )
    assert promise.ok
    rows = (
        (
            await session.execute(
                select(Situation).where(
                    Situation.kind == "commitment", Situation.campaign_id == w.h.campaign_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows and rows[0].subject_actor_id == w.actors["Mira"]


async def test_a_holder_who_promised_or_is_distracted_does_not_block(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    s = await obstacle(session, w)
    sit = SituationService(session)
    assert await sit.blocking(w.actors["Alex"], w.tavern, w.guard_house) is not None
    async with EventTransaction(session, w.h.campaign_id, w.h.timeline_id) as tx:
        await sit.open(
            tx,
            kind="status",
            label="distracted",
            subject_actor_id=w.actors["Mira"],
            data={"distracted": True},
        )
    assert await sit.blocking(w.actors["Alex"], w.tavern, w.guard_house) is None
    # an obstacle with no holder is not lifted by anyone's distraction
    s2 = await obstacle(session, w, holder=None)
    blocked = await sit.blocking(w.actors["Alex"], w.tavern, w.guard_house)
    assert blocked is not None and blocked.situation.id == s2.id
    assert s.id != s2.id


async def test_a_found_way_round_is_a_place_you_can_go(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    await obstacle(session, w, holder=None)
    fake = FakeModelProvider()
    orch = make(session, fake)
    gh = await place_ref(orch, w, w.guard_house)
    fake.register(
        "intent_interpreter",
        responder({"another way": intent("do", [("other", None)])}),
    )
    fake.register(
        "rules_adjudicator",
        {
            "requires_check": False,
            "summary": "a cellar hatch",
            "consequences": {
                "success": [
                    {"kind": "open_route", "label": "a cellar hatch", "to": gh, "minutes": 3}
                ]
            },
        },
    )
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I look for another way out of here.")
    )
    assert [c["kind"] for c in res.consequences] == ["open_route"], res.dev_notes
    hatch = (
        (
            await session.execute(
                select(Location)
                .join(Entity, Entity.id == Location.entity_id)
                .where(Location.location_type == "path", Entity.campaign_id == w.h.campaign_id)
            )
        )
        .scalars()
        .one()
    )
    hatch_ref = await place_ref(orch, w, hatch.id)
    assert "cellar" in hatch_ref  # the party knows it by name
    fake.replace(
        "intent_interpreter",
        responder(
            {
                "through the hatch": intent("do", [("travel", hatch_ref)]),
                "on to the guard house": intent("do", [("travel", None)]),
            }
        ),
    )
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I go through the hatch.")
    )
    assert res.actions[0]["status"] == "succeeded"
    assert await where(session, orch, w.actors["Alex"]) == hatch.id
    sit = SituationService(session)
    assert await sit.blocking(w.actors["Alex"], hatch.id, w.guard_house) is None


async def test_moving_to_where_you_stand_is_nothing_not_a_failure(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    orch = make(session, FakeModelProvider())
    scene = await orch.perspective.repo.current_scene(w.actors["Alex"])
    here = (scene.state["space"]["positions"].get(str(w.actors["Alex"])) or {}).get("zone")
    orch.provider.register("intent_interpreter", responder({"bar": intent("do", [("move", here)])}))
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I stay right here by the bar.")
    )
    assert res.actions[0]["status"] == "noop"
    assert any("From here you can go to" in n for n in res.mechanical_notices)


async def test_going_somewhere_read_as_a_move_where_you_stand_is_read_again_as_travel(
    session: AsyncSession, frostbridge: World
) -> None:
    """A9 outcomes eval: "We go into town" became a move to the gate the party stood at."""
    w = frostbridge
    fake = FakeModelProvider()
    orch = make(session, fake)
    scene = await orch.perspective.repo.current_scene(w.actors["Alex"])
    here = (scene.state["space"]["positions"].get(str(w.actors["Alex"])) or {}).get("zone")
    gh = await place_ref(orch, w, w.guard_house)
    fake.register("intent_interpreter", intent("do", [("move", here)]))
    fake.register("intent_interpreter", intent("do", [("travel", gh)]))
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "We go into the guard house.")
    )
    assert res.metrics["calls_by_role"]["intent_interpreter"] == 2
    assert res.actions[0]["action"] == "travel" and res.actions[0]["status"] == "succeeded"


async def test_a_called_check_rolls_the_named_skill_even_when_the_ruling_wants_none(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider().register(
        "rules_adjudicator", {"requires_check": False, "summary": "just look"}
    )
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h,
        PlayRequest(
            w.actors["Alex"], "the hearth stones for a loose one", check_skill="investigation"
        ),
    )
    assert "intent_interpreter" not in res.metrics["calls_by_role"]
    assert res.visible_rolls and res.visible_rolls[0]["purpose"] == "investigation"


async def test_a_whisper_to_nobody_goes_to_the_companions(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    await w.world.create_party(w.h, "party", [w.actors[n] for n in ("Alex", "Elara", "Tomas")])
    fake = FakeModelProvider().register(
        "intent_interpreter",
        responder({"your voices": intent("whisper", [("whisper", None)])}),
    )
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], '"Keep your voices down."', channel="whisper")
    )
    heard = set(res.speakers[0]["recipients"])
    assert {str(w.actors["Elara"]), str(w.actors["Tomas"])} <= heard
    assert str(w.actors["Mira"]) not in heard


async def test_the_table_assistant_remembers_and_offers_things_to_try(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    seen: list[str] = []

    def ta(req):
        seen.append(req.user)
        return (
            "You could look the hearth over.\n"
            "TRY: I search the hearth for a loose stone\n"
            "TRY: I ask Mira about the back door"
        )

    fake = FakeModelProvider().register("table_assistant", ta)
    orch = make(session, fake)
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "/ooc what could I do here?")
    )
    assert res.ooc == "You could look the hearth over."
    assert res.suggestions == [
        "I search the hearth for a loose stone",
        "I ask Mira about the back door",
    ]


async def test_the_consequence_kinds_apply_through_their_services(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    orch = make(session, FakeModelProvider())
    alex = w.actors["Alex"]
    scene = await orch.perspective.repo.current_scene(alex)
    cands = await orch._candidates(w.h, alex, scene)
    mira = next(c.ref for c in cands if c.id == str(w.actors["Mira"]))
    zone = next(c.ref for c in cands if c.kind == "zone")
    c = ConsequenceContext(w.h, scene, alex, None, cands, "ruling", "success", None)
    svc = orch.consequences
    proposals = [
        {"kind": "set_status", "who": "party", "status": "inspected"},
        {"kind": "advance_clock", "name": "Suspicion", "by": 1, "of": 4},
        {"kind": "advance_clock", "name": "Suspicion", "by": 2},
        {"kind": "reveal_feature", "description": "a loose hearthstone"},
        {"kind": "learn", "text": "Mira keeps the cellar key on her belt"},
        {"kind": "introduce", "person": "renn" if "renn" in [x.ref for x in cands] else mira},
        {"kind": "change_attitude", "person": mira, "dimension": "trust", "delta": 1},
        {"kind": "agree", "person": mira, "request": "hold a room for the party"},
        {"kind": "distract", "person": mira, "minutes": 5},
        {"kind": "raise_alarm", "text": "someone shouts for the watch"},
        {"kind": "owe_favor", "debtor": mira, "creditor": "you", "what": "a quiet word"},
        {"kind": "set_price", "seller": mira, "percent": -20},
        {"kind": "pay", "from": "you", "to": mira, "amount": 3},
        {"kind": "create_item", "name": "stamped pass", "holder": "you"},
        {"kind": "reposition", "who": "you", "zone": zone},
        {"kind": "harm", "who": "you", "amount": 1},
        {"kind": "heal", "who": "you", "amount": 1},
        {"kind": "condition", "who": mira, "condition": "condition.prone"},
        {"kind": "pass_time", "minutes": 5},
        {"kind": "schedule", "minutes": 30, "what": "the watch arrives"},
        {"kind": "add_obstacle", "label": "a crowd at the door", "minutes": 20},
        {"kind": "clear_status", "who": "you", "status": "inspected"},
    ]
    results = [
        await svc.apply_one(c, p["kind"], {k: v for k, v in p.items() if k != "kind"})
        for p in proposals
    ]
    failed = [(r.kind, r.reason) for r in results if not r.ok]
    # a condition the ruleset lacks is the only acceptable rejection here
    assert all(k == "condition" for k, _ in failed), failed
    kinds = {
        e.payload["kind"]
        for e in (
            await session.execute(
                select(Event).where(
                    Event.campaign_id == w.h.campaign_id, Event.event_type == "consequence.applied"
                )
            )
        ).scalars()
    }
    assert {"set_status", "pay", "learn", "reveal_feature", "advance_clock"} <= kinds
    sits = await SituationService(session).visible_to(alex)
    assert any(s.kind == "clock" and s.data["value"] == 3 for s in sits)
    assert any(s.kind == "alarm" for s in sits)


async def test_a_social_success_on_the_holder_lets_the_party_through_without_a_ruling(
    session: AsyncSession, frostbridge: World
) -> None:
    """The safety net: a convincing appeal to whoever holds the obstacle, with a ruling that
    named no consequence, still lets the party pass."""
    w = frostbridge
    s = await obstacle(session, w)
    fake = FakeModelProvider()
    fake.register(
        "intent_interpreter",
        responder(
            {
                "please": intent(
                    "say", [("persuade", "mira")], utterance="Please, Mira, let us out the back."
                )
            }
        ),
    )
    fake.register("rules_adjudicator", {"requires_check": True, "check": {"difficulty": "routine"}})
    orch = make(session, fake)
    for _ in range(6):
        res = await orch.process_player_input(
            w.h, PlayRequest(w.actors["Alex"], "please, Mira, let us out the back")
        )
        social = [a for a in res.actions if a["action"] == "social.persuade"]
        assert social, res.dev_notes
        if social[0]["status"] == "succeeded":
            break
    assert social[0]["status"] == "succeeded"
    assert any(c["kind"] == "grant_passage" for c in res.consequences)
    await session.refresh(s)
    assert str(w.actors["Alex"]) in s.data["passed"]


async def test_buying_costs_coin_and_what_you_cannot_afford_does_not_happen(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    fake = FakeModelProvider().register(
        "intent_interpreter",
        responder(
            {
                "wagon": intent("do", [("buy", "mira")]),
                "rope": intent("do", [("buy", "mira")]),
            }
        ),
    )
    orch = make(session, fake)

    async def coin(name: str) -> int:
        scene = await orch.perspective.repo.current_scene(w.actors["Alex"])
        loaded = await orch.actions.load_scene(w.h, scene.id)
        return loaded.ctx.states[str(w.actors[name])].resources["resource.coin"].current

    alex0, mira0 = await coin("Alex"), await coin("Mira")
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I buy the whole wagon from Mira.")
    )
    assert res.actions[0]["status"] == "invalid" and "can't afford" in res.actions[0]["reason"]
    assert await coin("Alex") == alex0
    res = await orch.process_player_input(
        w.h, PlayRequest(w.actors["Alex"], "I buy two rope coils from Mira.")
    )
    assert res.actions[0]["status"] == "succeeded", res.actions
    assert await coin("Alex") == alex0 - 4 and await coin("Mira") == mira0 + 4
    inv = [i.name for i in await orch.perspective.inventory(w.actors["Alex"])]
    assert any("Rope" in (n or "") for n in inv)


async def test_someone_who_says_their_name_is_known_by_it(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    orch = make(session, FakeModelProvider())
    names = await orch.perspective.known_entities(w.actors["Alex"])
    assert w.entities["Renn"] not in names
    scene = await orch.perspective.repo.current_scene(w.actors["Renn"])
    r = await orch.speech.utter(
        w.h, scene.id, w.actors["Renn"], "I'm Renn. Keep out of trouble.", channel="say"
    )
    await orch.ai._self_introduction(w.h, w.actors["Renn"], "I'm Renn. Keep out of trouble.", r)
    names = await orch.perspective.known_entities(w.actors["Alex"])
    assert names.get(w.entities["Renn"]) == "Renn"
