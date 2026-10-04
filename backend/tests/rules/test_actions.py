"""Action state machine: validation, economy, targeting, reactions, rest, items, hidden props."""

from __future__ import annotations

import pytest

from app.engine.actions import (
    ActionRequest,
    ActionResolver,
    ReactionChoice,
    ReactionWindow,
    SceneContext,
)
from app.engine.core import RulesEngine
from app.engine.encounter import Encounter, InitiativeEntry
from app.engine.positioning import SceneSpace, Zone
from app.engine.stats import ItemState
from tests.rules.conftest import FROSTBRIDGE_BUILDS

pytestmark = [pytest.mark.unit, pytest.mark.rules]


def armed(engine: RulesEngine, key: str, weapon: str, extra: dict | None = None):
    profile = dict(FROSTBRIDGE_BUILDS[key])
    profile = {
        **profile,
        "equipment": [{"instance_key": f"{key}_w", "def_key": weapon, "name": weapon}],
        **(extra or {}),
    }
    return engine.actor(key, profile)


def scene(engine: RulesEngine, *, combat=True, chooser=None, order=("elara", "thief", "tomas")):
    states = {
        "elara": armed(engine, "elara", "item.bow"),
        "tomas": armed(
            engine,
            "tomas",
            "item.sword",
            {
                "equipment": [
                    {"instance_key": "tomas_w", "def_key": "item.sword", "name": "sword"},
                    {"instance_key": "tomas_a", "def_key": "item.light_armor", "name": "leathers"},
                ]
            },
        ),
        "thief": armed(engine, "thief", "item.knife"),
    }
    space = SceneSpace(
        [
            Zone("door", exit=True),
            Zone("floor"),
            Zone("crates", cover="strong"),
            Zone("shelf", cover="partial", elevated=True),
        ],
        [("door", "floor"), ("floor", "crates"), ("floor", "shelf"), ("crates", "shelf")],
    )
    space.place("elara", "shelf")
    space.place("tomas", "floor")
    space.place("thief", "floor")
    enc = None
    if combat:
        enc = Encounter("t", list(states), {"elara": "party", "tomas": "party", "thief": "thieves"})
        enc.start(engine, states, provider=lambda e, s: [InitiativeEntry(k, 0, 0) for k in order])
    ctx = SceneContext(engine, states, space, enc, tick=100, chooser=chooser, scene_version=7)
    return ctx, ActionResolver(ctx)


def test_unknown_action_and_wrong_turn_are_invalid(engine):
    ctx, res = scene(engine)
    assert res.resolve(ActionRequest("elara", "action.fly")).status == "invalid"
    out = res.resolve(ActionRequest("thief", "action.attack", "tomas"))
    assert out.status == "invalid" and "turn" in out.reason


def test_stale_scene_version_is_rejected_without_mutation(engine):
    ctx, res = scene(engine)
    before = RulesEngine.state_hash(*ctx.states.values())
    out = res.resolve(ActionRequest("elara", "action.attack", "thief", based_on_scene_version=6))
    assert out.status == "invalid" and "stale" in out.reason
    assert RulesEngine.state_hash(*ctx.states.values()) == before
    assert (
        res.resolve(
            ActionRequest("elara", "action.attack", "thief", based_on_scene_version=7)
        ).status
        != "invalid"
    )


def test_economy_is_enforced_per_turn(engine):
    ctx, res = scene(engine)
    assert res.resolve(ActionRequest("elara", "action.attack", "thief")).status in (
        "succeeded",
        "failed",
    )
    out = res.resolve(ActionRequest("elara", "action.attack", "thief"))
    assert out.status == "invalid" and "major" in out.reason
    assert res.resolve(ActionRequest("elara", "action.move", "floor")).status == "succeeded"
    assert res.resolve(ActionRequest("elara", "action.move", "shelf")).status == "invalid"
    ctx.encounter.advance_turn()
    assert ctx.encounter.current_actor == "thief"


def test_targeting_range_hostility_and_hidden(engine):
    ctx, res = scene(engine, order=("thief", "elara", "tomas"))
    # thief has a knife: must be engaged
    out = res.resolve(ActionRequest("thief", "action.attack", "tomas"))
    assert out.status == "failed" and "cannot reach" in out.reason
    assert res.resolve(ActionRequest("thief", "action.attack", "thief")).status == "invalid"
    ctx.encounter.advance_turn()  # elara
    out = res.resolve(ActionRequest("elara", "action.attack", "tomas"))
    assert out.status == "invalid" and "not hostile" in out.reason
    engine.apply(
        ctx.states["thief"],
        [{"type": "apply_condition", "params": {"condition": "condition.hidden"}}],
    )
    out = res.resolve(ActionRequest("elara", "action.attack", "thief"))
    assert out.status == "invalid" and "hidden" in out.reason
    ctx.detected["elara"] = {"thief"}
    assert res.resolve(ActionRequest("elara", "action.attack", "thief")).status != "invalid"


def test_reaction_only_actions_cannot_be_used_directly(engine):
    ctx, res = scene(engine)
    out = res.resolve(ActionRequest("elara", "action.defend"))
    assert out.status == "invalid" and "reaction" in out.reason


def test_engage_then_knife_attack_with_defend_reaction(engine):
    windows: list[ReactionWindow] = []

    def chooser(w: ReactionWindow):
        windows.append(w)
        if w.trigger == "attacked":
            return ReactionChoice(w.target, "action.defend")
        return None

    ctx, res = scene(engine, chooser=chooser, order=("thief", "tomas", "elara"))
    assert res.resolve(ActionRequest("thief", "action.engage", "tomas")).status == "succeeded"
    assert ctx.space.engaged("thief", "tomas")
    out = res.resolve(ActionRequest("thief", "action.attack", "tomas"))
    assert out.status in ("succeeded", "failed")
    assert any(
        w.trigger == "attacked" and ("tomas", "action.defend") in w.eligible for w in windows
    )
    assert out.trace.reactions and out.trace.reactions[-1]["action"] == "action.defend"
    assert any(m["source"] == "defend" and m["value"] == -2 for m in out.trace.modifiers)
    assert ctx.encounter.budget("tomas").reaction == 0
    # a second attack this round cannot be defended: no reaction left
    ctx.encounter.budget("thief").major = 1
    out2 = res.resolve(ActionRequest("thief", "action.attack", "tomas"))
    assert not out2.trace.reactions


def test_protect_intercepts_an_attack_on_an_ally(engine):
    def chooser(w: ReactionWindow):
        if w.trigger == "ally_attacked" and ("tomas", "action.protect") in w.eligible:
            return ReactionChoice("tomas", "action.protect", w.target)
        return None

    ctx, res = scene(engine, chooser=chooser, order=("thief", "tomas", "elara"))
    ctx.space.move_to("elara", "floor")
    res.resolve(ActionRequest("thief", "action.engage", "elara"))
    out = res.resolve(ActionRequest("thief", "action.attack", "elara"))
    assert out.trace.reactions[0]["intercepted_for"] == "elara"
    assert out.steps[0].detail["target"] == "tomas"
    assert ctx.states["elara"].resources["resource.health"].current == 20


def test_unsafe_disengage_provokes_opportunity_attack(engine):
    def chooser(w: ReactionWindow):
        if w.trigger == "enemy_disengages":
            return ReactionChoice(w.eligible[0][0], "action.opportunity_attack", w.acting_actor)
        return None

    ctx, res = scene(engine, chooser=chooser, order=("thief", "tomas", "elara"))
    res.resolve(ActionRequest("thief", "action.engage", "tomas"))
    ctx.encounter.advance_turn()  # tomas's turn; thief is engaged with him
    ctx.encounter.budget("thief").reaction = 1
    out = res.resolve(ActionRequest("tomas", "action.disengage"))
    assert out.status in ("succeeded", "interrupted")
    assert out.trace.reactions and out.trace.reactions[0]["action"] == "action.opportunity_attack"
    assert any(e["type"] == "attack.rolled" and e["actor"] == "thief" for e in out.events)
    assert not ctx.space.engaged("thief", "tomas")
    # withdraw (careful) does not provoke
    ctx2, res2 = scene(engine, chooser=chooser, order=("thief", "tomas", "elara"))
    res2.resolve(ActionRequest("thief", "action.engage", "tomas"))
    ctx2.encounter.advance_turn()
    out2 = res2.resolve(ActionRequest("tomas", "action.withdraw"))
    assert out2.status == "succeeded" and not out2.trace.reactions


def test_cover_and_high_ground_modify_the_attack(engine):
    ctx, res = scene(engine, order=("thief", "elara", "tomas"))
    res.resolve(ActionRequest("thief", "action.move", "crates"))
    ctx.encounter.budget("thief").movement = 1
    out = res.resolve(ActionRequest("thief", "action.take_cover"))
    assert (
        out.status == "succeeded"
        and ctx.states["thief"].condition_intensity("condition.in_cover") == 2
    )
    ctx.encounter.advance_turn()  # elara: shelf (elevated), bow; thief: near, strong cover
    out = res.resolve(ActionRequest("elara", "action.attack", "thief"))
    srcs = {m["source"]: m["value"] for m in out.trace.modifiers}
    assert srcs.get("high_ground") == 1 and "cover:strong" in srcs
    assert out.check.target == 20 and out.check.situational == 1  # Defense 16 + strong cover 4
    thief = ctx.states["thief"]
    assert engine.stat(thief, "stat.defense", {"attacker_engaged": False}).value == 20
    assert engine.stat(thief, "stat.defense", {"attacker_engaged": True}).value == 16
    # engaging the thief strips the cover condition
    ctx.encounter.advance_turn()  # tomas
    res.resolve(ActionRequest("tomas", "action.move", "crates"))
    ctx.encounter.budget("tomas").movement = 1
    res.resolve(ActionRequest("tomas", "action.engage", "thief"))
    assert not thief.has_condition("condition.in_cover")


def test_hidden_item_property_applies_mechanically_but_stays_hidden(engine):
    ctx, res = scene(engine, order=("tomas", "thief", "elara"))
    tomas = ctx.states["tomas"]
    tomas.equipment[0] = ItemState(
        "dagger",
        "item.dagger",
        "Veyra's Chipped Dagger",
        hidden={"bonus_damage_vs_tags": {"spirit": 2}},
    )
    ctx.states["thief"].tags.add("spirit")
    ctx.space.engage("tomas", "thief")
    hits = [
        o
        for o in (res.resolve(ActionRequest("tomas", "action.attack", "thief")) for _ in range(1))
        if o.status == "succeeded"
    ]
    for _ in range(30):
        ctx.encounter.budget("tomas").major = 1
        o = res.resolve(ActionRequest("tomas", "action.attack", "thief"))
        if o.status == "succeeded":
            hits.append(o)
            break
    assert hits, "expected at least one hit in 31 attempts"
    dmg = next(s for s in hits[-1].steps if s.kind == "damage")
    assert dmg.detail["hidden_bonus"] == 2 and dmg.detail["attribute_bonus"] == 3  # floor(6/2)
    assert "hidden" not in tomas.to_profile()["equipment"][0]
    assert tomas.to_profile(include_hidden=True)["equipment"][0]["hidden"][
        "bonus_damage_vs_tags"
    ] == {"spirit": 2}


def test_pickup_drop_and_ground_items(engine):
    ctx, res = scene(engine, combat=False)
    ledger = ItemState("ledger", "item.travel_supplies", "Oric's ledger", equipped=False)
    ctx.ground["floor"] = [ledger]
    out = res.resolve(ActionRequest("tomas", "action.pick_up", "ledger"))
    assert (
        out.status == "succeeded"
        and ctx.states["tomas"].item("ledger") is ledger
        and ctx.ground["floor"] == []
    )
    assert out.time_cost_seconds == 10 and out.events[0]["type"] == "item.picked_up"
    assert res.resolve(ActionRequest("elara", "action.pick_up", "ledger")).status == "failed"
    out = res.resolve(ActionRequest("tomas", "action.drop", "ledger"))
    assert out.status == "succeeded" and ctx.ground["floor"] == [ledger]
    assert ledger.history == ["picked_up:tomas", "dropped:tomas"]


def test_rest_recovers_resources_and_clears_conditions(engine):
    ctx, res = scene(engine, combat=False)
    tomas = ctx.states["tomas"]
    engine.apply(
        tomas,
        [
            {"type": "deal_damage", "params": {"amount": 12}},
            {"type": "modify_resource", "params": {"resource": "resource.stamina", "amount": -10}},
            {"type": "apply_condition", "params": {"condition": "condition.exhausted"}},
        ],
    )
    out = res.resolve(ActionRequest("tomas", "action.short_rest"))
    assert out.status == "succeeded" and out.time_cost_seconds == 3600
    assert (
        tomas.resources["resource.stamina"].current == 7 + 7
    )  # half of (17 - 2 exhausted) restored... max is 15 while exhausted
    assert tomas.resources["resource.health"].current == 10 and tomas.has_condition(
        "condition.exhausted"
    )
    out = res.resolve(ActionRequest("tomas", "action.long_rest"))
    assert not tomas.has_condition("condition.exhausted")
    assert (
        tomas.resources["resource.health"].current == 21
        and tomas.resources["resource.stamina"].current == 17
    )
    # resting mid-combat is refused by requirement
    ctx2, res2 = scene(engine)
    out = res2.resolve(ActionRequest("elara", "action.short_rest"))
    assert out.status == "invalid" and "requirement" in out.reason


def test_flee_needs_exit_and_no_engagement(engine):
    ctx, res = scene(engine, order=("thief", "tomas", "elara"))
    ctx.space.engage("thief", "tomas")
    assert "engaged" in res.resolve(ActionRequest("thief", "action.flee", "door")).reason
    ctx.space.disengage("thief")
    ctx.encounter.budget("thief").major = ctx.encounter.budget("thief").movement = 1
    assert "not an exit" in res.resolve(ActionRequest("thief", "action.flee", "crates")).reason
    ctx.encounter.budget("thief").major = ctx.encounter.budget("thief").movement = 1
    out = res.resolve(ActionRequest("thief", "action.flee", "door"))
    assert (
        out.status == "succeeded"
        and "thief" in ctx.encounter.departed
        and "thief" not in ctx.space.positions
    )
    assert ctx.encounter.status == "ended"


def test_surrender_ends_the_fight(engine):
    ctx, res = scene(engine, order=("thief", "tomas", "elara"))
    out = res.resolve(ActionRequest("thief", "action.surrender"))
    assert out.status == "succeeded" and ctx.states["thief"].has_condition("condition.surrendered")
    assert ctx.encounter.status == "ended"
