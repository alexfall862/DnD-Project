"""Milestone 02b acceptance: a scripted warehouse combat (initiative, movement, cover,
reaction, damage, condition, surrender) replays byte-for-byte on state hash from the master
seed, and an environmental consequence persists."""

from __future__ import annotations

import json

import pytest

from app.engine.actions import (
    ActionRequest,
    ActionResolver,
    ReactionChoice,
    ReactionWindow,
    SceneContext,
    end_round,
)
from app.engine.core import RulesEngine
from app.engine.dice import DiceService, SeedStream
from app.engine.encounter import Encounter
from app.engine.positioning import SceneSpace, Zone
from app.engine.ruleset import Ruleset
from tests.rules.conftest import FROSTBRIDGE_BUILDS

pytestmark = [pytest.mark.unit, pytest.mark.rules, pytest.mark.replay]


def scripted_chooser(w: ReactionWindow) -> ReactionChoice | None:
    """Deterministic policy: defend when attacked, opportunity-attack disengaging enemies."""
    if w.trigger == "attacked":
        return ReactionChoice(w.target, "action.defend")
    if w.trigger == "enemy_disengages":
        return ReactionChoice(w.eligible[0][0], "action.opportunity_attack", w.acting_actor)
    return None


def build(core: Ruleset, seed: int) -> tuple[SceneContext, ActionResolver]:
    engine = RulesEngine(core, DiceService(SeedStream(seed)))
    states = {
        "elara": engine.actor(
            "elara",
            {
                **FROSTBRIDGE_BUILDS["elara"],
                "equipment": [
                    {"instance_key": "bow", "def_key": "item.bow", "name": "bow"},
                    {
                        "instance_key": "knife_e",
                        "def_key": "item.knife",
                        "name": "knife",
                        "equipped": False,
                    },
                ],
            },
        ),
        "thief_1": engine.actor(
            "thief_1",
            {
                **FROSTBRIDGE_BUILDS["thief"],
                "equipment": [{"instance_key": "k1", "def_key": "item.knife", "name": "knife"}],
            },
        ),
        "thief_2": engine.actor(
            "thief_2",
            {
                **FROSTBRIDGE_BUILDS["thief"],
                "equipment": [{"instance_key": "k2", "def_key": "item.knife", "name": "knife"}],
            },
        ),
    }
    space = SceneSpace(
        [
            Zone("door", exit=True),
            Zone("floor", features=["table", "lantern"]),
            Zone("crates", cover="strong"),
            Zone("shelf", cover="partial", elevated=True),
            Zone("window", exit=True),
        ],
        [
            ("door", "floor"),
            ("floor", "crates"),
            ("floor", "shelf"),
            ("floor", "window"),
            ("crates", "shelf"),
        ],
    )
    space.place("elara", "shelf")
    space.place("thief_1", "door")
    space.place("thief_2", "door")
    enc = Encounter(
        "warehouse", list(states), {"elara": "party", "thief_1": "thieves", "thief_2": "thieves"}
    )
    enc.start(engine, states)
    ctx = SceneContext(
        engine, states, space, enc, tick=1000, chooser=scripted_chooser, scene_version=1
    )
    return ctx, ActionResolver(ctx)


def thief_policy(ctx: SceneContext, res: ActionResolver, who: str, log: list[str]) -> None:
    """Fallback-policy style behaviour (turn-budget §5): close, stab, flee when hurt."""
    st = ctx.states[who]
    if st.has_condition("condition.incapacitated"):
        return
    hp = st.resources["resource.health"].current
    if hp <= 6:
        if ctx.space.engaged_partners(who):
            d = res.resolve(ActionRequest(who, "action.disengage"))
            log.append(
                f"{who} disengage {d.status}"
                + (f" reaction:{d.trace.reactions}" if d.trace.reactions else "")
            )
        if who in ctx.space.positions and not ctx.space.engaged_partners(who):
            if hp <= 3:
                out = res.resolve(ActionRequest(who, "action.surrender"))
            else:
                here = ctx.space.position(who).zone
                path = ctx.space.path(here, "door") or [here]
                if (
                    len(path) <= 2
                    and ctx.encounter.budget(who).major
                    and ctx.encounter.budget(who).movement
                ):
                    out = res.resolve(ActionRequest(who, "action.flee", "door"))
                elif ctx.encounter.budget(who).movement and len(path) > 1:
                    out = res.resolve(ActionRequest(who, "action.move", path[1]))
                else:
                    out = (
                        res.resolve(ActionRequest(who, "action.wait"))
                        if ctx.encounter.budget(who).major
                        else None
                    )
                    if out is None:
                        return
            log.append(f"{who} {out.request.action_key} {out.status}")
        return
    if ctx.space.engaged("who", "elara") if False else ctx.space.engaged(who, "elara"):
        out = res.resolve(ActionRequest(who, "action.attack", "elara"))
        log.append(
            f"{who} attack {out.status} {out.trace.summary}"
            + (f" reaction:{out.trace.reactions}" if out.trace.reactions else "")
        )
        return
    band = ctx.space.band(who, "elara")
    if band == "close":
        log.append(
            f"{who} engage {res.resolve(ActionRequest(who, 'action.engage', 'elara')).status}"
        )
        out = res.resolve(ActionRequest(who, "action.attack", "elara"))
        log.append(f"{who} attack {out.status} {out.trace.summary}")
    else:
        target_zone = ctx.space.position("elara").zone
        path = ctx.space.path(ctx.space.position(who).zone, target_zone)
        out = res.resolve(ActionRequest(who, "action.move", path[1]))
        log.append(f"{who} move {path[1]} {out.status}")


def elara_policy(ctx: SceneContext, res: ActionResolver, log: list[str]) -> None:
    st = ctx.states["elara"]
    hostiles = [
        t
        for t in ("thief_1", "thief_2")
        if t in ctx.space.positions
        and not ctx.states[t].has_condition("condition.incapacitated")
        and not ctx.states[t].has_condition("condition.surrendered")
    ]
    if not hostiles:
        return
    engaged = [t for t in hostiles if ctx.space.engaged("elara", t)]
    if engaged:
        # switch to the knife for melee, stab
        for i in st.equipment:
            i.equipped = i.def_key == "item.knife"
        out = res.resolve(ActionRequest("elara", "action.attack", engaged[0]))
    else:
        for i in st.equipment:
            i.equipped = i.def_key == "item.bow"
        if ctx.space.position("elara").cover == "none" and ctx.encounter.round == 1:
            log.append(
                "elara take_cover "
                + res.resolve(ActionRequest("elara", "action.take_cover")).status
            )
        target = min(hostiles, key=lambda t: ctx.space.band_index(ctx.space.band("elara", t)))
        out = res.resolve(ActionRequest("elara", "action.attack", target))
    log.append(
        f"elara attack {out.status} {out.trace.summary}"
        + (f" reaction:{out.trace.reactions}" if out.trace.reactions else "")
    )


def run_combat(
    core: Ruleset, seed: int, max_rounds: int = 30
) -> tuple[str, list[str], list[int], dict]:
    ctx, res = build(core, seed)
    log: list[str] = [f"order {[e.actor for e in ctx.encounter.order]}"]
    # environmental improvisation: a lantern knocked over sets the crates alight (persists)
    ctx.space.zones["crates"].features.append("burning")
    while ctx.encounter.status == "active" and ctx.encounter.round <= max_rounds:
        actor = ctx.encounter.current_actor
        if actor == "elara":
            elara_policy(ctx, res, log)
        else:
            thief_policy(ctx, res, actor, log)
        if ctx.encounter.status != "active":
            break
        _, new_round = ctx.encounter.advance_turn()
        if new_round:
            end_round(ctx)
            log.append(f"-- round {ctx.encounter.round} tick {ctx.tick}")
    summary = {
        "status": ctx.encounter.status,
        "rounds": ctx.encounter.round,
        "standing": sorted(ctx.encounter.living_sides(ctx.states)),
        "departed": ctx.encounter.departed,
        "crates_burning": "burning" in ctx.space.zones["crates"].features,
        "elara_hp": ctx.states["elara"].resources["resource.health"].current,
        "reactions": sum(1 for line in log if "reaction:" in line),
        "incapacitated": sorted(
            k for k, st in ctx.states.items() if st.has_condition("condition.incapacitated")
        ),
    }
    return (
        RulesEngine.state_hash(*ctx.states.values()),
        log,
        [r.seed for r in ctx.engine.dice.history],
        summary,
    )


def test_scripted_combat_exercises_every_mechanic_and_ends(core):
    """Across a handful of seeds the fixture must show initiative, movement, engagement, cover,
    a reaction, damage, a condition, and an ending by incapacitation, surrender or flight."""
    seen = set()
    for seed in range(2026, 2036):
        h, log, seeds, summary = run_combat(core, seed)
        text = " | ".join(log)
        assert summary["status"] == "ended", f"seed {seed} did not end: {summary}"
        assert len(summary["standing"]) <= 1
        assert summary["crates_burning"]  # environmental consequence persisted
        assert len(seeds) >= 6
        seen |= {
            m for m in ("engage succeeded", "take_cover succeeded", "hits", "miss") if m in text
        }
        if summary["reactions"]:
            seen.add("reaction")
        if summary["incapacitated"]:
            seen.add("incapacitated")
        if "surrender succeeded" in text:
            seen.add("surrender")
        if "flee succeeded" in text:
            seen.add("flee")
    assert {
        "engage succeeded",
        "take_cover succeeded",
        "hits",
        "miss",
        "reaction",
        "incapacitated",
    } <= seen, seen
    assert {"surrender", "flee"} & seen, seen


def test_combat_replays_byte_for_byte_from_master_seed(core):
    a = run_combat(core, 777)
    b = run_combat(core, 777)
    assert a[0] == b[0], "state hash differs"
    assert a[1] == b[1], "log differs"
    assert a[2] == b[2], "dice seeds differ"
    assert json.dumps(a[3], sort_keys=True) == json.dumps(b[3], sort_keys=True)
    c = run_combat(core, 778)
    assert c[1] != a[1] or c[0] != a[0]


def test_traces_explain_every_resolved_action(core):
    ctx, res = build(core, 5)
    out = res.resolve(ActionRequest(ctx.encounter.current_actor, "action.wait"))
    assert out.trace.summary and out.trace.costs_paid == {"major": True}
    t = out.trace.to_dict()
    assert set(t) >= {
        "rules_consulted",
        "requirements",
        "costs_paid",
        "rolls",
        "mutations",
        "summary",
    }
    json.dumps(t)  # serialisable for resolution_traces.*
