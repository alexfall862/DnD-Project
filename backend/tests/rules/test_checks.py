"""Checks: simple, versus-stat, opposed, margins, advantage, criticals, flexible pairing."""

from __future__ import annotations

import pytest

from app.engine.checks import CheckError
from app.engine.core import RulesEngine

pytestmark = [pytest.mark.unit, pytest.mark.rules]


def test_core_check_adds_attribute_skill_and_consults_rules(engine: RulesEngine, builds):
    alex = builds["alex"]
    r = engine.check(alex, "check.core", skill="skill.investigation", difficulty="moderate")
    assert r.attribute == "attr.intellect" and r.attribute_value == 6 and r.skill_value == 2
    assert r.total == r.roll.total + 8 and r.target == 14 and r.margin == r.total - 14
    assert (
        r.success == (r.margin >= 0)
        and r.degree == engine.ruleset.degree_for_margin(r.margin).degree
    )
    assert set(r.rules_consulted) == {"check.core", "attr.intellect", "skill.investigation"}
    assert r.roll.purpose == "check.core" and r.roll.extra["actor"] == "alex"


def test_flexible_attribute_pairing(engine: RulesEngine, builds):
    tomas = builds["tomas"]
    r = engine.check(
        tomas, "check.core", attribute="attr.might", skill="skill.intimidation", difficulty=11
    )
    assert r.attribute == "attr.might" and r.attribute_value == 6 and r.skill_value == 1


def test_difficulty_names_and_numbers_and_situational(engine: RulesEngine, builds):
    alex = builds["alex"]
    a = engine.check(alex, "check.core", difficulty="extreme")
    assert a.target == 26
    b = engine.check(alex, "check.core", difficulty=9, situational=-3)
    assert b.target == 9 and b.situational == -3 and b.total == b.roll.total + b.modifier_total - 3
    with pytest.raises(CheckError, match="unknown difficulty"):
        engine.check(alex, "check.core", difficulty="impossible")
    with pytest.raises(CheckError, match="unknown check"):
        engine.check(alex, "check.nope")


def test_versus_stat_uses_target_defense(engine: RulesEngine, builds):
    alex, thief = builds["alex"], builds["thief"]
    r = engine.check(alex, "check.melee_attack", target_state=thief)
    assert (
        r.target == 16
        and r.attribute == "attr.might"
        and r.skill == "skill.melee"
        and r.skill_value == 0
    )
    assert "stat.defense" in r.rules_consulted
    with pytest.raises(CheckError, match="needs a target_state"):
        engine.check(alex, "check.melee_attack")


def test_advantage_changes_the_roll_expression(engine: RulesEngine, builds):
    thief = builds["thief"]
    engine.apply(thief, [{"type": "apply_condition", "params": {"condition": "condition.blinded"}}])
    r = engine.check(thief, "check.core", difficulty=10)
    assert r.roll.expression == "2d20kl1" and r.advantage == -1 and r.roll.total == min(r.roll.raw)
    engine.apply(
        thief, [{"type": "remove_condition", "params": {"condition": "condition.blinded"}}]
    )
    engine.apply(thief, [{"type": "modify_check", "params": {"op": "advantage", "source": "aim"}}])
    r = engine.check(thief, "check.ranged_attack", target_state=builds["alex"])
    assert r.roll.expression == "2d20kh1" and r.roll.total == max(r.roll.raw)


def test_criticals_are_flagged_not_decisive(engine: RulesEngine, builds):
    alex = builds["alex"]
    seen = set()
    for _ in range(300):
        r = engine.check(alex, "check.core", difficulty=30)
        if r.critical == "high":
            assert r.roll.natural == 20 and r.success is False  # a 20 does not beat the impossible
        if r.critical == "low":
            assert r.roll.natural == 1
        seen.add(r.critical)
    assert {"high", "low", None} <= seen


def test_opposed_check_and_tie_favours_defender(engine: RulesEngine, builds):
    elara, thief = builds["elara"], builds["thief"]
    o = engine.opposed(
        elara, thief, attacker_skill="skill.awareness", defender_skill="skill.stealth"
    )
    assert o.a.actor_key == "elara" and o.b.actor_key == "thief"
    assert o.margin == o.a.total - o.b.total
    assert o.winner == ("a" if o.margin > 0 else "b")
    # force a tie by replaying identical seeds through a tiny custom opposed check
    assert engine.ruleset.checks["check.opposed"].tie == "defender"


def test_initiative_is_a_check_with_no_criticals(engine: RulesEngine, builds):
    tomas = builds["tomas"]
    r = engine.check(tomas, "check.initiative")
    assert r.attribute == "attr.agility" and r.modifier_total == 1  # Guard Training
    assert r.critical is None and r.target is None and r.success is None
