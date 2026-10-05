"""Ruleset packages: loading, manifest validation, reference validation, cycle rejection."""

from __future__ import annotations

import pytest

from app.engine.ruleset import Ruleset, RulesetError, load_ruleset
from tests.rules.conftest import write_package

pytestmark = [pytest.mark.unit, pytest.mark.rules]


def test_core_adventure_loads_and_validates(core: Ruleset) -> None:
    assert core.key == "core_adventure" and core.manifest.version == "0.1.0"
    assert len(core.attributes) == 5 and len(core.skills) == 16 and len(core.resources) == 4
    assert {"condition.burning", "condition.hidden", "condition.incapacitated"} <= set(
        core.conditions
    )
    assert core.manifest.difficulty_scale["moderate"] == 14
    assert len(core.content_hash) == 64
    assert core.has("attr.might") and core.has("resource.health") and not core.has("attr.luck")
    assert core.get("skill.stealth").default_attribute == "attr.agility"


def test_margin_table_matches_spec(core: Ruleset) -> None:
    expect = {
        -15: "critical_failure",
        -10: "critical_failure",
        -9: "failure",
        -1: "failure",
        0: "success",
        4: "success",
        5: "strong_success",
        9: "strong_success",
        10: "exceptional_success",
        40: "exceptional_success",
    }
    for margin, degree in expect.items():
        band = core.degree_for_margin(margin)
        assert band.degree == degree and band.success == (margin >= 0)


def test_unknown_reference_in_formula_is_rejected(tmp_path) -> None:
    pkg = write_package(
        tmp_path,
        resources={
            "resources": [
                {"key": "resource.health", "name": "Health", "max_formula": "10 + attr.luck * 2"},
            ]
        },
    )
    with pytest.raises(RulesetError, match="unknown reference 'attr.luck'"):
        load_ruleset(pkg)


def test_unknown_skill_attribute_is_rejected(tmp_path) -> None:
    pkg = write_package(
        tmp_path,
        skills={
            "skills": [
                {"key": "skill.hacking", "name": "Hacking", "default_attribute": "attr.cyber"},
            ]
        },
    )
    with pytest.raises(RulesetError, match="default_attribute 'attr.cyber' unknown"):
        load_ruleset(pkg)


def test_unknown_effect_primitive_is_rejected(tmp_path) -> None:
    pkg = write_package(
        tmp_path,
        conditions={
            "conditions": [
                {
                    "key": "condition.cursed",
                    "name": "Cursed",
                    "triggers": [
                        {
                            "event": "on_round_end",
                            "effects": [{"type": "run_python", "params": {"code": "1"}}],
                        }
                    ],
                },
            ]
        },
    )
    with pytest.raises(RulesetError, match="unknown effect primitive 'run_python'"):
        load_ruleset(pkg)


def test_effect_referencing_unknown_condition_is_rejected(tmp_path) -> None:
    pkg = write_package(
        tmp_path,
        conditions={
            "conditions": [
                {
                    "key": "condition.a",
                    "name": "A",
                    "on_apply": [
                        {"type": "apply_condition", "params": {"condition": "condition.zzz"}}
                    ],
                },
            ]
        },
    )
    with pytest.raises(RulesetError, match="unknown condition 'condition.zzz'"):
        load_ruleset(pkg)


def test_condition_trigger_cycle_is_rejected(tmp_path) -> None:
    pkg = write_package(
        tmp_path,
        conditions={
            "conditions": [
                {
                    "key": "condition.a",
                    "name": "A",
                    "triggers": [
                        {
                            "event": "on_damage",
                            "effects": [
                                {"type": "apply_condition", "params": {"condition": "condition.b"}}
                            ],
                        }
                    ],
                },
                {
                    "key": "condition.b",
                    "name": "B",
                    "on_apply": [
                        {"type": "apply_condition", "params": {"condition": "condition.a"}}
                    ],
                },
            ]
        },
    )
    with pytest.raises(RulesetError, match="condition trigger cycle"):
        load_ruleset(pkg)


def test_bad_modifier_target_and_op_rejected(tmp_path) -> None:
    pkg = write_package(
        tmp_path,
        traits={
            "traits": [
                {
                    "key": "trait.x",
                    "name": "X",
                    "modifiers": [{"target": "resource.health", "op": "add", "value": 1}],
                },
                {
                    "key": "trait.y",
                    "name": "Y",
                    "modifiers": [{"target": "stat.defense", "op": "advantage"}],
                },
            ]
        },
    )
    with pytest.raises(RulesetError) as exc:
        load_ruleset(pkg)
    msg = str(exc.value)
    assert "must be resource.<key>.max" in msg and "advantage only applies to check.*" in msg


def test_margins_must_be_contiguous_and_open_ended(tmp_path) -> None:
    pkg = write_package(
        tmp_path,
        manifest={
            "margins": [
                {"degree": "failure", "max": -1, "success": False},
                {"degree": "success", "min": 1, "success": True},  # gap at 0
            ]
        },
    )
    with pytest.raises(RulesetError, match="contiguous"):
        load_ruleset(pkg)


def test_key_prefix_and_duplicates_enforced(tmp_path) -> None:
    pkg = write_package(
        tmp_path,
        attributes={
            "attributes": [
                {"key": "might", "name": "Might"},
            ]
        },
    )
    with pytest.raises(RulesetError, match="must start with 'attr.'"):
        load_ruleset(pkg)
    pkg2 = (
        write_package(
            tmp_path / "dup",
            attributes={
                "attributes": [
                    {"key": "attr.might", "name": "Might"},
                    {"key": "attr.might", "name": "Might again"},
                    {"key": "attr.agility", "name": "A"},
                    {"key": "attr.intellect", "name": "I"},
                    {"key": "attr.presence", "name": "P"},
                    {"key": "attr.resolve", "name": "R"},
                ]
            },
        )
        if (tmp_path / "dup").mkdir() is None
        else None
    )
    with pytest.raises(RulesetError, match="duplicate definition"):
        load_ruleset(pkg2)


def test_missing_manifest_file_entry(tmp_path) -> None:
    pkg = write_package(tmp_path, manifest={"files": ["attributes.yaml", "nope.yaml"]})
    with pytest.raises(RulesetError, match="missing file 'nope.yaml'"):
        load_ruleset(pkg)
