"""Derived stats for the Frostbridge builds, modifier provenance, clamping."""

from __future__ import annotations

import pytest

from app.engine.core import RulesEngine
from app.engine.stats import ActorState, StatError

pytestmark = [pytest.mark.unit, pytest.mark.rules]


@pytest.mark.parametrize(
    "who, health, stamina, resolve_points, defense",
    [
        ("alex", 20, 15, 8, 16),  # Might 5 Agi 6 Res 5
        ("elara", 20, 16, 9, 17),  # Might 5 Agi 7 Res 6
        ("tomas", 22, 17, 9, 15),  # Might 6 Agi 5 Res 6
        ("thief", 18, 13, 7, 16),  # Might 4 Agi 6 Res 4 — fixture says Health 18
    ],
)
def test_frostbridge_derived_stats(
    engine: RulesEngine, builds, who, health, stamina, resolve_points, defense
):
    s = builds[who]
    assert engine.stat(s, "resource.health.max").value == health
    assert engine.stat(s, "resource.stamina.max").value == stamina
    assert engine.stat(s, "resource.resolve_points.max").value == resolve_points
    assert engine.stat(s, "stat.defense").value == defense
    assert s.resources["resource.health"].current == health  # starts full


def test_trait_modifiers_carry_provenance(engine: RulesEngine, builds):
    elara = builds["elara"]
    r = engine.stat(elara, "skill.awareness")
    assert r.base == 2 and r.value == 3
    assert [(ln.source, ln.op, ln.value) for ln in r.lines] == [("trait.keen_observer", "add", 1)]
    assert "trait.keen_observer" in r.explanation
    assert engine.stat(elara, "skill.survival").value == 4  # 3 + Frontier Veteran
    assert "cold_resistant" in elara.capabilities
    tomas = builds["tomas"]
    assert engine.stat(tomas, "check.initiative").value == 1  # Guard Training


def test_condition_modifiers_apply_and_scale_with_intensity(engine: RulesEngine, builds):
    tomas = builds["tomas"]
    engine.apply(
        tomas,
        [
            {
                "type": "apply_condition",
                "params": {"condition": "condition.exhausted", "intensity": 2},
            }
        ],
    )
    r = engine.stat(tomas, "resource.stamina.max")
    assert r.base == 17 and r.value == 13  # -2 per intensity
    assert r.lines[0].source == "condition.exhausted" and r.lines[0].value == 4
    assert engine.stat(tomas, "check.core").value == -2  # check.* subtract intensity
    engine.apply(tomas, [{"type": "apply_condition", "params": {"condition": "condition.stunned"}}])
    assert engine.stat(tomas, "stat.defense").value == 13


def test_conditional_modifier_uses_ctx(engine: RulesEngine, builds):
    alex = builds["alex"]
    engine.apply(
        alex, [{"type": "apply_condition", "params": {"condition": "condition.frightened"}}]
    )
    assert engine.stat(alex, "check.core").value == 0
    assert engine.stat(alex, "check.core", {"confronting_source": True}).value == -2


def test_advantage_counts_on_checks(engine: RulesEngine, builds):
    alex = builds["alex"]
    engine.apply(alex, [{"type": "apply_condition", "params": {"condition": "condition.blinded"}}])
    assert engine.stat(alex, "check.melee_attack").advantage == -1
    engine.apply(
        alex,
        [
            {
                "type": "modify_check",
                "params": {"check": "check.melee_attack", "op": "advantage", "source": "flanking"},
            }
        ],
    )
    assert engine.stat(alex, "check.melee_attack").advantage == 0
    assert engine.stat(alex, "check.ranged_attack").advantage == -1


def test_set_modifier_models_heavy_armour_agility_cap(engine: RulesEngine, builds):
    elara = builds["elara"]  # Agility 7
    engine.apply(
        elara, [{"type": "modify_attribute", "params": {"attribute": "attr.agility", "amount": 0}}]
    )  # harmless temp mod
    from app.engine.expressions import compile_expr
    from app.engine.stats import Modifier

    elara.temp_modifiers.append(
        Modifier(
            target="stat.defense_agility",
            op="set",
            value=compile_expr("min(attr.agility, 5)"),
            source="heavy_armor",
        )
    )
    elara.temp_modifiers.append(
        Modifier(target="stat.defense", op="add", value=compile_expr(3), source="heavy_armor")
    )
    assert engine.stat(elara, "stat.defense").value == 18  # 10 + 5 + 3, not 10 + 7 + 3


def test_attribute_values_are_clamped(engine: RulesEngine, builds):
    thief = builds["thief"]
    engine.apply(
        thief, [{"type": "modify_attribute", "params": {"attribute": "attr.might", "amount": 20}}]
    )
    assert engine.stat(thief, "attr.might").value == 10
    engine.apply(
        thief,
        [
            {
                "type": "modify_attribute",
                "params": {"attribute": "attr.might", "amount": -5, "permanent": True},
            }
        ],
    )
    assert thief.attributes["attr.might"] == 1


def test_profile_validation(engine: RulesEngine):
    with pytest.raises(StatError, match="outside 1..10"):
        engine.actor("x", {"attributes": {"attr.might": 11}})
    with pytest.raises(StatError, match="unknown skill"):
        engine.actor("x", {"skills": {"skill.hacking": 1}})
    with pytest.raises(StatError, match="unknown trait"):
        engine.actor("x", {"traits": ["trait.dragonborn"]})
    s = engine.actor("y", {})  # defaults: every attribute 3
    assert s.attributes["attr.might"] == 3 and s.resources["resource.health"].current == 16


def test_profile_round_trips(engine: RulesEngine, builds):
    elara = builds["elara"]
    engine.apply(elara, [{"type": "deal_damage", "params": {"amount": 4}}])
    again = ActorState.from_profile(engine.ruleset, "elara", elara.to_profile())
    assert again.resources["resource.health"].current == 16
    assert sorted(again.traits) == sorted(elara.traits) and again.skills == elara.skills
    assert RulesEngine.state_hash(again) == RulesEngine.state_hash(elara)
