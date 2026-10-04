"""Pure 06b engine pieces: autonomy gates, reaction significance tiers, fallback policies and
the tactical controller (orchestration §12, §19–§20; world-memory §4)."""

from __future__ import annotations

import pytest

from app.engine.actions import SceneContext
from app.engine.autonomy import AutonomyProfile, domain_of, gate
from app.engine.core import RulesEngine
from app.engine.encounter import Encounter
from app.engine.positioning import SceneSpace, Zone
from app.engine.reactions import ReactionSignals, significance, tier
from app.engine.stats import ConditionInstance
from app.engine.tactics import FallbackPolicy, choose_action, situation_unchanged
from tests.rules.conftest import FROSTBRIDGE_BUILDS

pytestmark = pytest.mark.unit


def test_autonomy_defaults_and_overrides() -> None:
    p = AutonomyProfile.from_dict({"item_transfer": "ask", "combat": "blocked", "bogus": "x"})
    assert gate(p, "action.pick_up").paused and gate(p, "action.pick_up").domain == "item_transfer"
    assert gate(p, "action.attack").blocked
    assert gate(p, "action.move").execute  # exploration stays autonomous
    assert gate(p, "action.surrender").paused  # major_irreversible defaults to ask
    assert domain_of("action.search", params={"irreversible": True}) == "major_irreversible"
    assert AutonomyProfile.from_dict(None).level("conversation") == "autonomous"


@pytest.mark.parametrize(
    "signals, expected",
    [
        (ReactionSignals("a", "important", asked=True, new_information=True, novelty=1.0), "high"),
        (ReactionSignals("a", "full", direct_target=True, new_information=True), "high"),
        (ReactionSignals("a", "full", relationship_relevant=True, novelty=1.0), "low"),
        (ReactionSignals("a", "standard", new_information=True, relationship_relevant=True), "low"),
        (
            ReactionSignals(
                "a", "full", new_information=True, relationship_relevant=True, novelty=1.0
            ),
            "medium",
        ),
        (ReactionSignals("a", "background", direct_target=True), "low"),
        (ReactionSignals("a", "full"), "low"),
    ],
)
def test_significance_tiers(signals: ReactionSignals, expected: str) -> None:
    assert tier(significance(signals)) == expected


def _combat_ctx(engine: RulesEngine, *, far: bool = False) -> SceneContext:
    states = {
        "tomas": engine.actor("tomas", FROSTBRIDGE_BUILDS["tomas"]),
        "thief": engine.actor("thief", FROSTBRIDGE_BUILDS["thief"]),
        "thief2": engine.actor("thief2", FROSTBRIDGE_BUILDS["thief"]),
    }
    space = SceneSpace([Zone("a"), Zone("b"), Zone("c")], [("a", "b"), ("b", "c")])
    space.place("tomas", "a")
    space.place("thief", "c" if far else "a")
    space.place("thief2", "b")
    enc = Encounter("s", list(states), {"tomas": "party", "thief": "t", "thief2": "t"})
    enc.start(engine, states)
    return SceneContext(engine, states, space, enc)


def test_tactics_attack_engage_move_and_flee() -> None:
    engine = RulesEngine.load("core_adventure", master_seed=3)
    ctx = _combat_ctx(engine)
    policy = FallbackPolicy(target="thief")
    # same zone, not engaged: close to melee first
    key, target, _ = choose_action(ctx, "tomas", policy)
    assert (key, target) == ("action.engage", "thief")
    ctx.space.engage("tomas", "thief")
    key, target, _ = choose_action(ctx, "tomas", policy)
    assert (key, target) == ("action.attack", "thief")
    assert situation_unchanged(ctx, "tomas", policy)
    # the preferred target drops: nearest hostile replaces it, policy counts as changed
    ctx.states["thief"].conditions.append(ConditionInstance("condition.incapacitated"))
    assert not situation_unchanged(ctx, "tomas", policy)
    key, target, _ = choose_action(ctx, "tomas", policy)
    assert key in ("action.move", "action.engage", "action.attack") and target != "thief"
    # far target → move toward it
    ctx2 = _combat_ctx(engine, far=True)
    key, target, _ = choose_action(ctx2, "tomas", FallbackPolicy(target="thief"))
    assert key == "action.move" and target == "b"  # one step along the route
    # low health → flee regardless of target
    hp = ctx2.states["tomas"].resources["resource.health"]
    hp.current = 1
    key, _, reason = choose_action(ctx2, "tomas", FallbackPolicy(target="thief"))
    assert key == "action.flee" and "health" in reason
    assert not situation_unchanged(ctx2, "tomas", FallbackPolicy(target="thief"))


def test_policy_round_trip() -> None:
    p = FallbackPolicy(target="x", intent="protect", flee_below=0.2, protect="y", scene_version=4)
    assert FallbackPolicy.from_dict(p.to_dict()) == p and FallbackPolicy.from_dict(None) is None
