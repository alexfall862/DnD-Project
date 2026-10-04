"""Dice parser and seeded reproducibility."""

from __future__ import annotations

import pytest

from app.engine.dice import DiceError, DiceService, SeedStream, parse_dice, roll_with_seed

pytestmark = [pytest.mark.unit, pytest.mark.rules]


@pytest.mark.parametrize(
    "text, count, sides, keep, keep_n, mod",
    [
        ("1d20", 1, 20, None, None, 0),
        ("d100", 1, 100, None, None, 0),
        ("2d6+3", 2, 6, None, None, 3),
        ("2d6 - 1", 2, 6, None, None, -1),
        ("4d6kh3", 4, 6, "kh", 3, 0),
        ("2d20kh1", 2, 20, "kh", 1, 0),
        ("2d20kl1+2", 2, 20, "kl", 1, 2),
        ("1D8", 1, 8, None, None, 0),
    ],
)
def test_parse(text, count, sides, keep, keep_n, mod):
    e = parse_dice(text)
    assert (e.count, e.sides, e.keep, e.keep_n, e.modifier) == (count, sides, keep, keep_n, mod)


@pytest.mark.parametrize(
    "text", ["", "20", "1d", "0d6", "1d1", "4d6kh5", "1d6+", "1d6*2", "101d6", "1d2000", "d6 d6"]
)
def test_parse_rejects(text):
    with pytest.raises(DiceError):
        parse_dice(text)


def test_same_seed_same_dice():
    e = parse_dice("4d6kh3")
    a = roll_with_seed(e, 12345)
    b = roll_with_seed(e, 12345)
    assert a == b
    raw, kept, total = a
    assert len(raw) == 4 and len(kept) == 3
    assert kept == tuple(sorted(raw, reverse=True)[:3]) and total == sum(kept)


def test_bounds_hold_over_many_rolls():
    svc = DiceService(SeedStream(1))
    for _ in range(500):
        r = svc.roll("2d6+3")
        assert 5 <= r.total <= 15 and all(1 <= d <= 6 for d in r.raw)
    for _ in range(200):
        r = svc.roll("2d20kl1")
        assert r.total == min(r.raw)


def test_master_seed_reproduces_whole_sequence():
    a = DiceService(SeedStream(2026))
    b = DiceService(SeedStream(2026))
    seq_a = [a.roll("1d20", purpose="attack").total for _ in range(20)] + [a.choose(5)]
    seq_b = [b.roll("1d20", purpose="attack").total for _ in range(20)] + [b.choose(5)]
    assert seq_a == seq_b
    assert [r.seed for r in a.history] == [r.seed for r in b.history]


def test_replay_from_record_is_identical():
    svc = DiceService(SeedStream(7))
    rec = svc.roll("3d8+2", purpose="damage", visibility="public", actor="elara")
    again = DiceService().replay(rec)
    assert (again.raw, again.kept, again.total, again.seed) == (
        rec.raw,
        rec.kept,
        rec.total,
        rec.seed,
    )
    assert again.extra == {"actor": "elara"} and again.purpose == "damage"


def test_record_captures_everything_for_audit():
    rec = DiceService(SeedStream(3)).roll("1d20+5", purpose="check", visibility="actor_only")
    assert rec.expression == "1d20+5" and rec.modifier == 5
    assert rec.total == rec.kept[0] + 5 and rec.natural == rec.kept[0]
    assert rec.visibility == "actor_only"


def test_choose_is_engine_owned_and_bounded():
    svc = DiceService(SeedStream(9))
    picks = {svc.choose(3) for _ in range(100)}
    assert picks <= {0, 1, 2} and len(picks) == 3
    with pytest.raises(DiceError):
        svc.choose(0)
