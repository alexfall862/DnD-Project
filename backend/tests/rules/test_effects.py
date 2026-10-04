"""Effect primitives: resource bounds, damage pipeline, conditions and stacking, expiry,
invalid effects rejected."""

from __future__ import annotations

import pytest

from app.engine.core import RulesEngine
from app.engine.effects import EffectError

pytestmark = [pytest.mark.unit, pytest.mark.rules]


def test_resource_overflow_clamps_and_health_allows_negative(engine: RulesEngine, builds):
    alex = builds["alex"]
    m = engine.apply(
        alex,
        [{"type": "restore_resource", "params": {"resource": "resource.stamina", "amount": 99}}],
    )
    assert (
        alex.resources["resource.stamina"].current == 15
        and m[0].after == 15
        and m[0].detail["max"] == 15
    )
    engine.apply(
        alex,
        [{"type": "modify_resource", "params": {"resource": "resource.stamina", "amount": -99}}],
    )
    assert alex.resources["resource.stamina"].current == 0  # floor
    engine.apply(alex, [{"type": "deal_damage", "params": {"amount": 25}}])
    assert alex.resources["resource.health"].current == -5  # depletion: allow (dying rules later)


def test_depleting_health_applies_incapacitated(engine: RulesEngine, builds):
    thief = builds["thief"]
    m = engine.apply(thief, [{"type": "deal_damage", "params": {"amount": 18}}])
    assert thief.resources["resource.health"].current == 0
    assert thief.has_condition("condition.incapacitated")
    kinds = [x.kind for x in m]
    assert kinds[0] == "resource" and "condition_applied" in kinds
    assert engine.stat(thief, "stat.defense").value == 12


def test_damage_pipeline_records_stages_and_resistance(engine: RulesEngine, builds):
    elara = builds["elara"]
    elara.capabilities.add("resist:fire")
    m = engine.apply(
        elara,
        [{"type": "deal_damage", "params": {"amount": 9, "damage_type": "damage.fire"}}],
        engine.context(armor_dr=1),
    )
    stages = dict(m[0].detail["stages"])
    assert stages == {"raw": 9, "source_modifiers": 9, "resistance": 4, "armor": 3, "final": 3}
    assert m[0].detail["damage"] == 3 and elara.resources["resource.health"].current == 17
    elara.capabilities.add("immune:fire")
    m = engine.apply(
        elara, [{"type": "deal_damage", "params": {"amount": 9, "damage_type": "damage.fire"}}]
    )
    assert m[0].detail["damage"] == 0 and elara.resources["resource.health"].current == 17
    with pytest.raises(EffectError, match="unknown damage_type"):
        engine.apply(
            elara, [{"type": "deal_damage", "params": {"amount": 1, "damage_type": "damage.sonic"}}]
        )


def test_dice_amounts_are_rolled_by_the_engine(engine: RulesEngine, builds):
    thief = builds["thief"]
    ctx = engine.context(source="alex")
    m = engine.apply(thief, [{"type": "deal_damage", "params": {"amount": "1d8+2"}}], ctx)
    assert len(ctx.rolls) == 1 and ctx.rolls[0].expression == "1d8+2"
    assert m[0].detail["damage"] == ctx.rolls[0].total and m[0].source == "alex"
    assert engine.dice.history[-1] is ctx.rolls[0]


@pytest.mark.parametrize(
    "condition, stacking",
    [
        ("condition.hidden", "none"),
        ("condition.burning", "refresh"),
        ("condition.poisoned", "intensity"),
    ],
)
def test_condition_stacking_rules(engine: RulesEngine, builds, condition, stacking):
    alex = builds["alex"]
    assert engine.ruleset.conditions[condition].stacking == stacking
    first = engine.apply(
        alex,
        [{"type": "apply_condition", "params": {"condition": condition, "duration_seconds": 30}}],
        engine.context(tick=100),
    )
    assert first[0].kind == "condition_applied"
    second = engine.apply(
        alex,
        [{"type": "apply_condition", "params": {"condition": condition, "duration_seconds": 60}}],
        engine.context(tick=110),
    )
    instances = [c for c in alex.conditions if c.key == condition]
    assert len(instances) == 1
    if stacking == "none":
        assert second[0].kind == "noop" and instances[0].expires_tick == 130
    elif stacking == "refresh":
        assert second[0].kind == "condition_refreshed" and instances[0].expires_tick == 170
    else:
        assert second[0].kind == "condition_intensified" and instances[0].intensity == 2
        engine.apply(
            alex, [{"type": "apply_condition", "params": {"condition": condition, "intensity": 5}}]
        )
        assert instances[0].intensity == 3  # max_intensity


def test_remove_condition_and_partial_reduction(engine: RulesEngine, builds):
    tomas = builds["tomas"]
    engine.apply(
        tomas,
        [
            {
                "type": "apply_condition",
                "params": {"condition": "condition.poisoned", "intensity": 3},
            }
        ],
    )
    m = engine.apply(
        tomas,
        [
            {
                "type": "remove_condition",
                "params": {"condition": "condition.poisoned", "intensity": 1},
            }
        ],
    )
    assert (
        m[0].kind == "condition_intensified"
        and tomas.condition_intensity("condition.poisoned") == 2
    )
    m = engine.apply(
        tomas, [{"type": "remove_condition", "params": {"condition": "condition.poisoned"}}]
    )
    assert m[0].kind == "condition_removed" and not tomas.has_condition("condition.poisoned")
    m = engine.apply(
        tomas, [{"type": "remove_condition", "params": {"condition": "condition.poisoned"}}]
    )
    assert m[0].kind == "noop"


def test_expiry_removes_conditions_and_temp_modifiers(engine: RulesEngine, builds):
    alex = builds["alex"]
    engine.apply(
        alex,
        [
            {
                "type": "apply_condition",
                "params": {"condition": "condition.stunned"},
            },  # default 6 s
            {
                "type": "modify_check",
                "params": {"op": "add", "amount": 2, "duration_seconds": 10, "source": "blessing"},
            },
        ],
        engine.context(tick=1000),
    )
    assert alex.has_condition("condition.stunned") and engine.stat(alex, "check.core").value == 2
    engine.advance(alex, 1005)
    assert alex.has_condition("condition.stunned")
    m = engine.advance(alex, 1006)
    assert not alex.has_condition("condition.stunned") and any(
        x.kind == "condition_removed" for x in m
    )
    assert engine.stat(alex, "check.core").value == 2
    engine.advance(alex, 1010)
    assert engine.stat(alex, "check.core").value == 0 and not alex.temp_modifiers


def test_invalid_effects_are_rejected_before_any_mutation(engine: RulesEngine, builds):
    alex = builds["alex"]
    before = RulesEngine.state_hash(alex)
    with pytest.raises(EffectError, match="unknown effect primitive 'eval'"):
        engine.apply(alex, [{"type": "eval", "params": {"code": "1+1"}}])
    with pytest.raises(EffectError, match="unknown condition"):
        engine.apply(
            alex, [{"type": "apply_condition", "params": {"condition": "condition.dragonfire"}}]
        )
    with pytest.raises(EffectError, match="unknown resource"):
        engine.apply(
            alex,
            [{"type": "modify_resource", "params": {"resource": "resource.mana", "amount": 1}}],
        )
    with pytest.raises(EffectError, match="bad amount"):
        engine.apply(
            alex,
            [
                {
                    "type": "modify_resource",
                    "params": {"resource": "resource.stamina", "amount": "__import__('os')"},
                }
            ],
        )
    with pytest.raises(EffectError, match="bad op"):
        engine.apply(alex, [{"type": "modify_check", "params": {"op": "set", "amount": 99}}])
    assert RulesEngine.state_hash(alex) == before


def test_modify_attribute_temporary_and_permanent(engine: RulesEngine, builds):
    alex = builds["alex"]
    engine.apply(
        alex,
        [
            {
                "type": "modify_attribute",
                "params": {
                    "attribute": "attr.might",
                    "amount": 2,
                    "duration_seconds": 60,
                    "source": "potion",
                },
            }
        ],
        engine.context(tick=0),
    )
    assert (
        engine.stat(alex, "attr.might").value == 7
        and engine.stat(alex, "resource.health.max").value == 24
    )
    assert alex.attributes["attr.might"] == 5
    engine.advance(alex, 60)
    assert engine.stat(alex, "attr.might").value == 5
    engine.apply(
        alex,
        [
            {
                "type": "modify_attribute",
                "params": {"attribute": "attr.might", "amount": 1, "permanent": True},
            }
        ],
    )
    assert alex.attributes["attr.might"] == 6
