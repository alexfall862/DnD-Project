"""Milestone 02a acceptance: a scripted sequence of checks and effects on two actors
reproduces identical results from recorded seeds (deterministic replay, testing-strategy §8)."""

from __future__ import annotations

import pytest

from app.engine.core import RulesEngine
from app.engine.dice import DiceService, SeedStream
from app.engine.ruleset import Ruleset
from tests.rules.conftest import FROSTBRIDGE_BUILDS

pytestmark = [pytest.mark.unit, pytest.mark.rules, pytest.mark.replay]

SCRIPT = [
    ("check", "elara", "check.core", {"skill": "skill.awareness", "difficulty": "moderate"}),
    ("check", "thief", "check.core", {"skill": "skill.stealth", "difficulty": 14}),
    (
        "opposed",
        "elara",
        "thief",
        {"attacker_skill": "skill.awareness", "defender_skill": "skill.stealth"},
    ),
    ("attack", "thief", "elara", {"damage": "1d4+1"}),
    ("attack", "elara", "thief", {"damage": "1d8"}),
    ("effect", "thief", {"type": "apply_condition", "params": {"condition": "condition.burning"}}),
    ("fire", "thief", "on_round_end"),
    (
        "effect",
        "elara",
        {"type": "apply_condition", "params": {"condition": "condition.poisoned", "intensity": 2}},
    ),
    ("fire", "elara", "on_round_end"),
    ("attack", "thief", "elara", {"damage": "1d4+1"}),
    (
        "effect",
        "elara",
        {"type": "restore_resource", "params": {"resource": "resource.health", "amount": "1d6"}},
    ),
    ("advance", 12),
]


def run_script(engine: RulesEngine) -> tuple[str, list[int], list[str]]:
    actors = {k: engine.actor(k, FROSTBRIDGE_BUILDS[k]) for k in ("elara", "thief")}
    log: list[str] = []
    for step in SCRIPT:
        kind = step[0]
        if kind == "check":
            r = engine.check(actors[step[1]], step[2], **step[3])
            log.append(f"{step[1]} {r.summary}")
        elif kind == "opposed":
            o = engine.opposed(actors[step[1]], actors[step[2]], **step[3])
            log.append(f"opposed {o.a.total} vs {o.b.total} -> {o.winner}")
        elif kind == "attack":
            att, tgt = actors[step[1]], actors[step[2]]
            r = engine.check(att, "check.melee_attack", target_state=tgt)
            log.append(f"{step[1]} attacks: {r.summary}")
            if r.success:
                m = engine.apply(
                    tgt,
                    [{"type": "deal_damage", "params": {"amount": step[3]["damage"]}}],
                    engine.context(source=step[1]),
                )
                log.append(f"  hit for {m[0].detail['damage']} -> {m[0].after}")
        elif kind == "effect":
            m = engine.apply(actors[step[1]], [step[2]])
            log.append(f"{step[1]} {m[0].kind} {m[0].field} {m[0].before}->{m[0].after}")
        elif kind == "fire":
            m = engine.fire(actors[step[1]], step[2])
            log.append(f"{step[1]} {step[2]}: {[x.after for x in m]}")
        elif kind == "advance":
            for a in actors.values():
                engine.advance(a, step[1])
    seeds = [r.seed for r in engine.dice.history]
    return RulesEngine.state_hash(*actors.values()), seeds, log


def test_same_master_seed_replays_identically(core: Ruleset):
    h1, seeds1, log1 = run_script(RulesEngine(core, DiceService(SeedStream(2026))))
    h2, seeds2, log2 = run_script(RulesEngine(core, DiceService(SeedStream(2026))))
    assert h1 == h2 and seeds1 == seeds2 and log1 == log2
    assert len(seeds1) >= 8  # the script actually rolled
    h3, _, log3 = run_script(RulesEngine(core, DiceService(SeedStream(2027))))
    assert log3 != log1 or h3 != h1  # a different seed changes something


def test_recorded_rolls_replay_bit_for_bit(core: Ruleset):
    original = RulesEngine(core, DiceService(SeedStream(99)))
    run_script(original)
    fresh = DiceService()  # unrelated master seed
    for rec in original.dice.history:
        again = fresh.replay(rec)
        assert (again.raw, again.kept, again.total) == (rec.raw, rec.kept, rec.total)


def test_state_hash_ignores_instance_ids_but_not_state(engine: RulesEngine, builds):
    a = builds["alex"]
    b = engine.actor("alex", FROSTBRIDGE_BUILDS["alex"])
    engine.apply(a, [{"type": "apply_condition", "params": {"condition": "condition.hidden"}}])
    engine.apply(b, [{"type": "apply_condition", "params": {"condition": "condition.hidden"}}])
    assert a.conditions[0].instance_id != b.conditions[0].instance_id
    assert RulesEngine.state_hash(a) == RulesEngine.state_hash(b)
    engine.apply(b, [{"type": "deal_damage", "params": {"amount": 1}}])
    assert RulesEngine.state_hash(a) != RulesEngine.state_hash(b)
