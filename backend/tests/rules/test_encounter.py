"""Encounters: initiative provider, turn order, budgets, departure, ending."""

from __future__ import annotations

import pytest

from app.engine.core import RulesEngine
from app.engine.dice import DiceService, SeedStream
from app.engine.encounter import Encounter, EncounterError, InitiativeEntry, TurnBudget

pytestmark = [pytest.mark.unit, pytest.mark.rules]


def make(engine, builds, seed=None):
    states = {k: builds[k] for k in ("elara", "tomas", "thief")}
    enc = Encounter("test", list(states), {"elara": "party", "tomas": "party", "thief": "thieves"})
    return enc, states


def test_default_initiative_is_descending_with_awareness_tiebreak(engine: RulesEngine, builds):
    enc, states = make(engine, builds)
    order = enc.start(engine, states)
    totals = [e.total for e in order]
    assert totals == sorted(totals, reverse=True)
    for a, b in zip(order, order[1:], strict=False):
        if a.total == b.total:
            assert a.tiebreak >= b.tiebreak
    assert enc.round == 1 and enc.current_actor == order[0].actor
    assert all(r.purpose in ("initiative", "initiative tie-break") for r in engine.dice.history)


def test_initiative_is_reproducible_from_master_seed(core, builds):
    from tests.rules.conftest import FROSTBRIDGE_BUILDS

    def run(seed):
        eng = RulesEngine(core, DiceService(SeedStream(seed)))
        states = {k: eng.actor(k, FROSTBRIDGE_BUILDS[k]) for k in ("elara", "tomas", "thief")}
        enc = Encounter("t", list(states), {"elara": "p", "tomas": "p", "thief": "t"})
        return [e.actor for e in enc.start(eng, states)]

    assert run(11) == run(11)


def test_custom_initiative_provider_is_pluggable(engine: RulesEngine, builds):
    enc, states = make(engine, builds)

    def side_initiative(eng, sts):  # party first, fixed order: a plugin mechanic
        return [InitiativeEntry(k, 0, 0) for k in ("tomas", "elara", "thief")]

    assert [e.actor for e in enc.start(engine, states, provider=side_initiative)] == [
        "tomas",
        "elara",
        "thief",
    ]


def test_turns_budgets_and_rounds(engine: RulesEngine, builds):
    enc, states = make(engine, builds)
    enc.start(engine, states)
    first = enc.current_actor
    b = enc.budget(first)
    assert b.to_dict() == {"major": 1, "movement": 1, "reaction": 1}
    assert b.can_pay({"major": True}) and b.can_pay({"free": True})
    b.pay({"major": True})
    assert not b.can_pay({"major": True}) and b.can_pay({"movement": True})
    seen = [first]
    for _ in range(2):
        actor, new_round = enc.advance_turn()
        seen.append(actor)
        assert not new_round
    actor, new_round = enc.advance_turn()
    assert new_round and enc.round == 2 and actor == first
    assert enc.budget(first).major == 1  # refreshed at the start of own turn
    assert len(set(seen)) == 3


def test_departed_actors_are_skipped_and_encounter_ends(engine: RulesEngine, builds):
    enc, states = make(engine, builds)
    enc.start(engine, states)
    enc.remove("thief", "fled")
    turns = set()
    for _ in range(4):
        actor, _ = enc.advance_turn()
        turns.add(actor)
    assert "thief" not in turns
    assert enc.maybe_end(states) and enc.status == "ended"
    with pytest.raises(EncounterError):
        enc.advance_turn()


def test_incapacitated_or_surrendered_side_ends_encounter(engine: RulesEngine, builds):
    enc, states = make(engine, builds)
    enc.start(engine, states)
    engine.apply(
        states["thief"],
        [{"type": "apply_condition", "params": {"condition": "condition.surrendered"}}],
    )
    assert enc.living_sides(states) == {"party"}
    assert enc.maybe_end(states)


def test_round_trips_through_dict(engine: RulesEngine, builds):
    enc, states = make(engine, builds)
    enc.start(engine, states)
    enc.advance_turn()
    again = Encounter.from_dict(enc.to_dict())
    assert again.to_dict() == enc.to_dict() and again.current_actor == enc.current_actor
    assert isinstance(again.budget(again.current_actor), TurnBudget)
