"""Triggers fire from conditions/traits and halt at the hard depth/effect budget."""

from __future__ import annotations

import pytest

from app.engine.core import RulesEngine
from app.engine.dice import DiceService, SeedStream
from app.engine.effects import MAX_EFFECTS_PER_CHAIN, MAX_TRIGGER_DEPTH
from app.engine.ruleset import load_ruleset
from tests.rules.conftest import write_package

pytestmark = [pytest.mark.unit, pytest.mark.rules]


def test_burning_deals_fire_damage_at_round_end(engine: RulesEngine, builds):
    elara = builds["elara"]
    engine.apply(elara, [{"type": "apply_condition", "params": {"condition": "condition.burning"}}])
    m = engine.fire(elara, "on_round_end")
    assert m and m[0].kind == "resource" and m[0].source == "condition.burning"
    assert m[0].detail["damage_type"] == "damage.fire" and 1 <= m[0].detail["damage"] <= 4
    assert engine.dice.history[-1].expression == "1d4"
    assert engine.fire(elara, "on_rest") == []


def test_poison_damage_scales_with_intensity(engine: RulesEngine, builds):
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
    m = engine.fire(tomas, "on_round_end")
    assert m[0].detail["damage"] == 3 and tomas.resources["resource.health"].current == 19


def test_mutually_recursive_runtime_triggers_halt_at_budget(tmp_path):
    """Definition-level cycle detection catches apply_condition loops; this models the
    damage-heals-damage runtime loop (testing-strategy §12) and proves the chain halts."""
    pkg = write_package(
        tmp_path,
        conditions={
            "conditions": [
                {"key": "condition.incapacitated", "name": "Incapacitated"},
                {"key": "condition.surrendered", "name": "Surrendered"},
                {"key": "condition.fleeing", "name": "Fleeing"},
                {
                    "key": "condition.in_cover",
                    "name": "In cover",
                    "stacking": "intensity",
                    "max_intensity": 2,
                },
                {
                    "key": "condition.feedback",
                    "name": "Feedback",
                    "triggers": [
                        {
                            "event": "on_damage",
                            "effects": [
                                {
                                    "type": "deal_damage",
                                    "params": {"amount": 1, "damage_type": "damage.mental"},
                                }
                            ],
                        },
                    ],
                },
            ]
        },
    )
    rs = load_ruleset(pkg)
    engine = RulesEngine(rs, DiceService(SeedStream(5)))
    actor = engine.actor("loop", {"attributes": {"attr.might": 10}})  # Health 30
    engine.apply(
        actor, [{"type": "apply_condition", "params": {"condition": "condition.feedback"}}]
    )
    ctx = engine.context()
    m = engine.apply(actor, [{"type": "deal_damage", "params": {"amount": 1}}], ctx)
    assert ctx.budget_exhausted
    damage_steps = [x for x in m if x.kind == "resource"]
    assert 1 < len(damage_steps) <= MAX_TRIGGER_DEPTH + 2
    assert actor.resources["resource.health"].current >= 30 - (MAX_TRIGGER_DEPTH + 2)
    assert any(x.kind == "noop" and "exhausted" in x.detail.get("reason", "") for x in m)
    assert ctx.effects_applied <= MAX_EFFECTS_PER_CHAIN
